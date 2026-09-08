#!/usr/bin/env python3
"""
Reconstruye el historial de snapshots hacia atras (una foto por semana, desde
tu primer movimiento hasta hoy), usando los mismos datos publicos que
actualizar_valores.py — pero calculando "cuanto tenias invertido y cuanto
valia" en cada fecha pasada, no solo hoy.

Para cada fecha de corte:
  - Cantidad y costo invertido: se recalculan caminando el ledger real hasta
    esa fecha (igual que analyzeHolding() en el dashboard).
  - Valor de CEDEARs/BTC: precio historico real (Yahoo/CoinGecko), ya
    cacheado en data/precios_historicos.json.
  - Valor de los 3 fondos: valor de cuotaparte historico real, via CAFCI
    (api.argentinadatos.com), consultado por fecha.

Es una reconstruccion, no magia: para CEDEARs sigue siendo la aproximacion
por ratio (~95%), igual que en tiempo real.

Uso:
    python3 scripts/reconstruir_historial.py            (una foto por semana)
    python3 scripts/reconstruir_historial.py --dias 3    (cada 3 dias, mas fino)

Es seguro correrlo de nuevo: las fechas que ya existan como snapshot se
actualizan, no se duplican.
"""
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
from actualizar_valores import (  # noqa: E402
    instrument_matches_ticker, BUY_TYPES, SELL_TYPES,
    CEDEAR_RATIOS, SPY_RATIO_AFTER, SPY_RATIO_BEFORE, COINGECKO_TICKERS, FCI_FUNDS, HEADERS,
)

ROOT = Path(__file__).resolve().parent.parent
INVEST_FILE = ROOT / "data" / "inversiones.json"
PRICES_FILE = ROOT / "data" / "precios_historicos.json"
SPY_SPLIT_DATE = "2026-06-01"


def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d")


def price_on_or_before(series, date_str):
    """series: lista ordenada [{date, priceUSD}]. Devuelve el ultimo precio
    con date <= date_str (o el primero disponible si no hay ninguno antes)."""
    found = None
    for p in series:
        if p["date"] <= date_str:
            found = p
        else:
            break
    return found["priceUSD"] if found else (series[0]["priceUSD"] if series else None)


def quantity_and_cost_as_of(movements, ticker, date_str, dolar_rate_fn, ratio_for_qty=1):
    """Camina el ledger hasta date_str (inclusive) y devuelve (cantidad, costo_usd)."""
    relevant = sorted(
        (m for m in movements if instrument_matches_ticker(m.get("instrument"), ticker) and (m.get("date") or "") <= date_str),
        key=lambda m: m.get("date") or "",
    )
    qty = 0.0
    cost_usd = 0.0
    for m in relevant:
        is_buy = m.get("type") in BUY_TYPES
        is_sell = m.get("type") in SELL_TYPES
        if not is_buy and not is_sell:
            continue
        total = m.get("total")
        amount_usd = None
        if total is not None:
            if m.get("currency") == "USD":
                amount_usd = abs(total)
            elif m.get("currency") == "ARS":
                rate = dolar_rate_fn(m.get("date"))
                if rate:
                    amount_usd = abs(total) / rate
        q = abs(m["quantity"]) if m.get("quantity") is not None else None
        if is_buy:
            if amount_usd is not None:
                cost_usd += amount_usd
            if q is not None:
                qty += q
        elif is_sell:
            if q is not None and qty > 0:
                avg = cost_usd / qty
                sold = min(q, qty)
                cost_usd -= avg * sold
                qty -= sold
    return qty, cost_usd


def ratio_for(ticker, date_str):
    if ticker == "SPY":
        # El ratio del CEDEAR de SPY cambio de 20:1 a 60:1 el 01/06/2026. Para
        # fechas anteriores hay que usar el ratio viejo, si no se subvalua la
        # posicion 3 veces (el ajuste de cantidad del split tampoco existia aun).
        return SPY_RATIO_AFTER if date_str >= SPY_SPLIT_DATE else SPY_RATIO_BEFORE
    return CEDEAR_RATIOS.get(ticker)


class DolarRates:
    """Cache de cotizaciones de dolar por fecha, pidiendo a ArgentinaDatos las
    que falten (ya sea para convertir movimientos en pesos o el fondo COCOSPPA)."""

    def __init__(self, path):
        self.path = path
        self.rates = {}
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                self.rates = json.load(f).get("rates", {})
        self._dirty = False

    def get(self, date_str, _profundidad=0):
        if not date_str:
            return None
        if date_str in self.rates:
            return self.rates[date_str].get("venta")
        y, m, d = date_str.split("-")
        url = f"https://api.argentinadatos.com/v1/cotizaciones/dolares/bolsa/{y}/{m}/{d}"
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if "compra" in data and "venta" in data:
                self.rates[date_str] = {"compra": data["compra"], "venta": data["venta"]}
                self._dirty = True
                return data["venta"]
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
            pass
        # fin de semana/feriado sin cotizacion: probar el dia anterior (hasta 8 veces)
        if _profundidad < 8:
            prev = (parse_date(date_str) - timedelta(days=1)).strftime("%Y-%m-%d")
            return self.get(prev, _profundidad + 1)
        return None

    def save(self):
        if self._dirty:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"rates": self.rates}, f, ensure_ascii=False, indent=2)


class FciHistory:
    """Cache de valor de cuotaparte por (categoria, fecha). Los fondos no
    publican valor los fines de semana/feriados, asi que si un dia puntual
    no tiene dato, camina hacia atras hasta encontrar el ultimo publicado.
    Si el hueco es mas largo (el agregador gratuito no tiene SLA, a veces
    faltan semanas enteras de un fondo puntual), usa el ultimo vcp real
    conocido para ESE fondo como aproximacion — para un fondo de renta fija
    de baja volatilidad es mucho mejor supuesto que "no existia"."""

    def __init__(self):
        self.cache = {}
        self.ultimo_conocido = {}  # nombre_fondo -> (fecha, vcp) mas reciente ya visto

    def _fetch(self, categoria, date_str):
        key = (categoria, date_str)
        if key not in self.cache:
            y, m, d = date_str.split("-")
            url = f"https://api.argentinadatos.com/v1/finanzas/fci/{categoria}/{y}/{m}/{d}"
            entries = []
            try:
                req = urllib.request.Request(url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=20) as resp:
                    parsed = json.loads(resp.read().decode("utf-8"))
                if isinstance(parsed, list):
                    entries = parsed
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
                pass
            self.cache[key] = entries
        return self.cache[key]

    def vcp(self, categoria, nombre_fondo, date_str):
        d = parse_date(date_str)
        for _ in range(8):  # hasta 8 dias hacia atras (cubre fines de semana largos)
            ds = d.strftime("%Y-%m-%d")
            entries = self._fetch(categoria, ds)
            match = next((e for e in entries if e.get("fondo") == nombre_fondo), None)
            if match:
                self.ultimo_conocido[nombre_fondo] = (ds, match["vcp"])
                return match["vcp"]
            d -= timedelta(days=1)
        # hueco mas largo: usar el ultimo vcp real que hayamos visto para este fondo
        if nombre_fondo in self.ultimo_conocido:
            return self.ultimo_conocido[nombre_fondo][1]
        return None


def reconstruir(paso_dias=7):
    if not INVEST_FILE.exists() or not PRICES_FILE.exists():
        return {"ok": False, "error": "faltan data/inversiones.json o data/precios_historicos.json"}

    with open(INVEST_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    with open(PRICES_FILE, "r", encoding="utf-8") as f:
        series_by_ticker = json.load(f).get("series", {})

    dolar_file = ROOT / "data" / "dolar_historico.json"
    dolar = DolarRates(dolar_file)
    fci = FciHistory()

    all_dates = []
    for plat in data.get("platforms", {}).values():
        for m in plat.get("movements", []):
            if m.get("date"):
                all_dates.append(m["date"])
    if not all_dates:
        return {"ok": False, "error": "no hay movimientos"}
    start = parse_date(min(all_dates))
    today = datetime.now(timezone.utc).replace(tzinfo=None)

    fechas = []
    cur = start
    while cur <= today:
        fechas.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=paso_dias)
    if fechas[-1] != today.strftime("%Y-%m-%d"):
        fechas.append(today.strftime("%Y-%m-%d"))

    snapshots = data.setdefault("snapshots", [])
    resultados = []

    for date_str in fechas:
        total_value = 0.0
        total_cost = 0.0
        for plat_key, holdings in data.get("holdings", {}).items():
            movements = data.get("platforms", {}).get(plat_key, {}).get("movements", [])
            for h in holdings:
                ticker = h["instrument"]

                if ticker in FCI_FUNDS:
                    info = FCI_FUNDS[ticker]
                    qty_raw, cost = quantity_and_cost_as_of(movements, ticker, date_str, dolar.get)
                    if qty_raw <= 0:
                        continue
                    vcp = fci.vcp(info["categoria"], info["nombre"], date_str)
                    if vcp is None:
                        continue
                    qty = qty_raw / 1000
                    if info["currency"] == "USD":
                        total_value += qty * vcp
                    else:
                        rate = dolar.get(date_str)
                        if not rate:
                            continue
                        total_value += qty * vcp / rate
                    total_cost += cost
                    continue

                if ticker in COINGECKO_TICKERS:
                    qty, cost = quantity_and_cost_as_of(movements, ticker, date_str, dolar.get)
                    if qty <= 0:
                        continue
                    price = price_on_or_before(series_by_ticker.get(ticker, []), date_str)
                    if price is None:
                        continue
                    total_value += qty * price
                    total_cost += cost
                    continue

                ratio = ratio_for(ticker, date_str)
                if ratio:
                    qty, cost = quantity_and_cost_as_of(movements, ticker, date_str, dolar.get)
                    if qty <= 0:
                        continue
                    price = price_on_or_before(series_by_ticker.get(ticker, []), date_str)
                    if price is None:
                        continue
                    total_value += qty / ratio * price
                    total_cost += cost
                    continue

                # sin ratio/fuente conocida (ej. holdings manuales sin ticker publico):
                # no se puede reconstruir su valor pasado, se omite de este calculo.

        if total_value <= 0 and total_cost <= 0:
            continue
        existing = next((s for s in snapshots if s["date"] == date_str), None)
        if existing:
            existing["investedUSD"] = round(total_cost, 2)
            existing["valueUSD"] = round(total_value, 2)
        else:
            snapshots.append({"date": date_str, "investedUSD": round(total_cost, 2), "valueUSD": round(total_value, 2)})
        resultados.append({"date": date_str, "valueUSD": round(total_value, 2), "investedUSD": round(total_cost, 2)})

    snapshots.sort(key=lambda s: s["date"])
    with open(INVEST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    dolar.save()

    return {"ok": True, "fotos_generadas": len(resultados), "total_snapshots": len(snapshots), "detalle": resultados}


def main():
    paso = 7
    if "--dias" in sys.argv:
        idx = sys.argv.index("--dias")
        if idx + 1 < len(sys.argv):
            paso = int(sys.argv[idx + 1])
    print(f"Reconstruyendo historial cada {paso} dias (puede tardar un rato, pide datos historicos por fecha)...")
    r = reconstruir(paso)
    if not r.get("ok"):
        print("Error: " + r.get("error", "?"))
        return
    for d in r["detalle"]:
        print(f"  {d['date']}: valor US$ {d['valueUSD']} · invertido US$ {d['investedUSD']}")
    print(f"\n{r['fotos_generadas']} fotos generadas/actualizadas. Total de fotos: {r['total_snapshots']}")


if __name__ == "__main__":
    main()
