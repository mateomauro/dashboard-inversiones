#!/usr/bin/env python3
"""
Calcula el "Vale hoy" (valueUSD) de tus tenencias a partir de datos publicos
gratuitos (sin login, sin credenciales de ningun broker), y lo actualiza
directo en data/inversiones.json:

- BTC: cantidad real (de tus movimientos) x precio actual (CoinGecko). Exacto.
- Fondos (Cocos Dólares Plus, Cocos Pesos Plus, Ualintec Renta Dólares):
  cantidad real x valor de cuotaparte oficial (CAFCI, via api.argentinadatos.com).
  Exacto — es el mismo dato regulatorio que el propio Ualá linkea como fuente
  ("Conocé el valor cuotaparte").
- CEDEARs con ratio oficial conocido (QQQ, SPY, AAPL, MSFT, GOOGL, NVDA, EFA, EEM):
  cantidad real x precio de la accion/ETF real (Yahoo) / ratio del CEDEAR.
  Es una aproximacion muy cercana (~95%+), no exacta: el CEDEAR en pesos cotiza
  con una prima/descuento propio del mercado argentino que no esta en ningun
  dato publico gratuito.

Requiere haber corrido antes actualizar_precios.py (usa data/precios_historicos.json)
y tener data/dolar_historico.json con al menos una cotizacion (la usa para
convertir el fondo en pesos a USD).

Uso:
    python3 scripts/actualizar_valores.py
"""
import json
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
INVEST_FILE = ROOT / "data" / "inversiones.json"
PRICES_FILE = ROOT / "data" / "precios_historicos.json"
DOLAR_FILE = ROOT / "data" / "dolar_historico.json"
IOL_FILE = ROOT / "data" / "cedears_iol.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; inversiones-tracker/1.0)"}
MAX_DIAS_PRECIO_IOL = 5  # si es mas viejo que esto, se prefiere el ratio en vez de confiar en el dato

BUY_TYPES = {"compra", "suscripcion_fci"}
SELL_TYPES = {"venta", "rescate_fci"}

# Ratio oficial de CEDEAR (cuantos CEDEARs = 1 accion/ETF real), verificado
# contra compras reales y la tabla de BYMA (rankia.com.ar, junio 2026).
CEDEAR_RATIOS = {
    "QQQ": 20, "AAPL": 20, "MSFT": 30, "GOOGL": 58, "NVDA": 24,
    "EFA": 18, "EEM": 5,
}
# SPY tuvo un split de ratio (20:1 -> 60:1) el 01/06/2026 anunciado por BYMA/Cocos.
# No aparece como movimiento en el extracto (es un ajuste automatico del custodio);
# la cantidad ya viene corregida en tus movimientos via el ajuste manual
# "Split CEDEAR SPY" agregado una vez.
SPY_RATIO_AFTER = 60

COINGECKO_TICKERS = {"BTC"}

# Fondos propios de Cocos/Ualá: nombre exacto como figura en CAFCI, para
# buscarlos en api.argentinadatos.com/v1/finanzas/fci/{categoria}/ultimo
FCI_FUNDS = {
    "COCOUSDPA": {"categoria": "rentaFija", "nombre": "Cocos Dólares Plus - Clase A", "currency": "USD"},
    "COCOSPPA": {"categoria": "retornoTotal", "nombre": "Cocos Pesos Plus - Clase A", "currency": "ARS"},
    "FONDO_UALA": {"categoria": "rentaFija", "nombre": "Ualintec Renta Dólares - Clase A", "currency": "USD"},
}


def instrument_matches_ticker(instrument, ticker):
    if not instrument:
        return False
    i, t = instrument.upper(), ticker.upper()
    if i == t:
        return True
    return f"({t})" in i or i.startswith(t + " ") or i.endswith(" " + t) or f" {t} " in i


def quantity_held(movements, ticker):
    qty = 0.0
    for m in movements:
        if not instrument_matches_ticker(m.get("instrument"), ticker):
            continue
        t = m.get("type")
        q = m.get("quantity")
        if q is None:
            continue
        if t in BUY_TYPES:
            qty += abs(q)
        elif t in SELL_TYPES:
            qty -= abs(q)
    return qty


def latest_price(series_by_ticker, ticker):
    series = series_by_ticker.get(ticker)
    if not series:
        return None, None
    last = series[-1]
    return last.get("priceUSD"), last.get("date")


def ratio_for(ticker):
    if ticker == "SPY":
        return SPY_RATIO_AFTER
    return CEDEAR_RATIOS.get(ticker)


def fetch_fci_ultimo(categoria):
    url = f"https://api.argentinadatos.com/v1/finanzas/fci/{categoria}/ultimo"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def latest_dolar_rate():
    if not DOLAR_FILE.exists():
        return None, None
    with open(DOLAR_FILE, "r", encoding="utf-8") as f:
        rates = json.load(f).get("rates", {})
    if not rates:
        return None, None
    latest_date = max(rates.keys())
    return rates[latest_date].get("venta"), latest_date


def iol_price_ars(ticker):
    """Precio real del CEDEAR en pesos (API oficial de IOL), si esta cargado
    y no tiene mas de MAX_DIAS_PRECIO_IOL dias. None si no hay dato fresco."""
    if not IOL_FILE.exists():
        return None, None
    with open(IOL_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    entry = data.get("precios", {}).get(ticker)
    if not entry or not entry.get("fechaHora"):
        return None, None
    try:
        fecha = datetime.fromisoformat(entry["fechaHora"])
        if fecha.tzinfo:
            fecha = fecha.astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None, None
    dias = (datetime.now(timezone.utc).replace(tzinfo=None) - fecha).days
    if dias > MAX_DIAS_PRECIO_IOL:
        return None, None
    return entry["precioARS"], entry["fechaHora"]


def actualizar_valores():
    if not INVEST_FILE.exists():
        return {"actualizados": [], "error": "no existe data/inversiones.json"}
    if not PRICES_FILE.exists():
        return {"actualizados": [], "error": "no existe data/precios_historicos.json, corre antes actualizar_precios.py"}

    with open(INVEST_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    with open(PRICES_FILE, "r", encoding="utf-8") as f:
        series_by_ticker = json.load(f).get("series", {})

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    actualizados = []
    fci_cache = {}

    for plat_key, holdings in data.get("holdings", {}).items():
        movements = data.get("platforms", {}).get(plat_key, {}).get("movements", [])
        for h in holdings:
            ticker = h["instrument"]
            qty = quantity_held(movements, ticker)
            if qty <= 0:
                continue

            if ticker in FCI_FUNDS:
                info = FCI_FUNDS[ticker]
                cat = info["categoria"]
                if cat not in fci_cache:
                    fci_cache[cat] = fetch_fci_ultimo(cat)
                entries = fci_cache[cat] or []
                match = next((e for e in entries if e.get("fondo") == info["nombre"]), None)
                if not match:
                    actualizados.append({"ticker": ticker, "ok": False, "error": "fondo no encontrado en CAFCI/ArgentinaDatos"})
                    continue
                vcp = match["vcp"]
                # Cocos reporta la "cantidad" de cuotapartes de FCI escalada x1000
                # respecto de la convencion de CAFCI (verificado: cantidad*precio/1000
                # = total real de cada movimiento). Hay que corregirlo aca.
                qty_cuotapartes = qty / 1000
                if info["currency"] == "USD":
                    new_value = round(qty_cuotapartes * vcp, 2)
                    metodo = "exacto (CAFCI via ArgentinaDatos)"
                else:
                    rate, rate_date = latest_dolar_rate()
                    if not rate:
                        actualizados.append({"ticker": ticker, "ok": False, "error": "sin cotizacion de dolar para convertir"})
                        continue
                    new_value = round(qty_cuotapartes * vcp / rate, 2)
                    metodo = f"exacto (CAFCI, convertido con dolar del {rate_date})"
                h["valueUSD"] = new_value
                h["asOf"] = today
                actualizados.append({"ticker": ticker, "valueUSD": new_value, "metodo": metodo, "precioFuente": match["fecha"], "ok": True})
                continue

            if ticker in COINGECKO_TICKERS:
                price, price_date = latest_price(series_by_ticker, ticker)
                if price is None:
                    continue
                new_value = round(qty * price, 2)
                h["valueUSD"] = new_value
                h["asOf"] = today
                actualizados.append({"ticker": ticker, "valueUSD": new_value, "metodo": "exacto (precio real)", "precioFuente": price_date, "ok": True})
                continue

            ratio = ratio_for(ticker)
            if ratio:
                precio_ars, fecha_iol = iol_price_ars(ticker)
                rate, rate_date = latest_dolar_rate()
                if precio_ars is not None and rate:
                    new_value = round(qty * precio_ars / rate, 2)
                    h["valueUSD"] = new_value
                    h["asOf"] = today
                    actualizados.append({"ticker": ticker, "valueUSD": new_value, "metodo": "exacto (API IOL, precio real BYMA)", "precioFuente": fecha_iol, "ok": True})
                    continue
                price, price_date = latest_price(series_by_ticker, ticker)
                if price is None:
                    continue
                new_value = round(qty / ratio * price, 2)
                h["valueUSD"] = new_value
                h["asOf"] = today
                actualizados.append({"ticker": ticker, "valueUSD": new_value, "metodo": f"aproximado (ratio {ratio}:1)", "precioFuente": price_date, "ok": True})

    with open(INVEST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return {"actualizados": actualizados}


def main():
    print("Calculando valores actuales (BTC y fondos exactos, CEDEARs aproximado)...")
    r = actualizar_valores()
    if r.get("error"):
        print("  " + r["error"])
        return
    for a in r["actualizados"]:
        if a.get("ok"):
            print(f"  {a['ticker']}: US$ {a['valueUSD']} — {a['metodo']} (dato del {a['precioFuente']})")
        else:
            print(f"  {a['ticker']}: no se pudo actualizar ({a.get('error','?')})")
    if not r["actualizados"]:
        print("  Nada para actualizar (sin cantidades cargadas o sin precios disponibles).")
    print(f"\nGuardado en: {INVEST_FILE}")


if __name__ == "__main__":
    main()
