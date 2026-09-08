#!/usr/bin/env python3
"""
Baja el valor de cuotaparte (VCP) de hoy para los fondos conocidos (Cocos
Dolares Plus, Cocos Pesos Plus, Ualintec Renta Dolares) via CAFCI
(api.argentinadatos.com), y lo guarda en data/fondos_historico.json.

A diferencia de actualizar_valores.py, este script NO necesita
data/inversiones.json (no toca cantidades ni costos personales) — solo
guarda el dato publico del dia, para que se pueda correr en la nube
(GitHub Actions) sin acceso a ningun dato tuyo.

Uso:
    python3 scripts/actualizar_fondos.py

Es seguro correrlo de nuevo: agrega el dia que falte, no duplica.
"""
import json
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parent.parent
FONDOS_FILE = ROOT / "data" / "fondos_historico.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; inversiones-tracker/1.0)"}

# ticker -> {categoria CAFCI, nombre exacto del fondo, moneda}
FCI_FUNDS = {
    "COCOUSDPA": {"categoria": "rentaFija", "nombre": "Cocos Dólares Plus - Clase A", "currency": "USD"},
    # CAFCI reclasifico este fondo de "retornoTotal" a "mercadoDinero" (detectado 04/09/2026,
    # habia quedado sin actualizar desde el 21/07). Si algun dia deja de encontrarse, revisar
    # en que categoria quedo: curl api.argentinadatos.com/v1/finanzas/fci/<categoria>/ultimo
    "COCOSPPA": {"categoria": "mercadoDinero", "nombre": "Cocos Pesos Plus - Clase A", "currency": "ARS"},
    "FONDO_UALA": {"categoria": "rentaFija", "nombre": "Ualintec Renta Dólares - Clase A", "currency": "USD"},
}


def fetch_fci_dia(categoria, date_str):
    y, m, d = date_str.split("-")
    url = f"https://api.argentinadatos.com/v1/finanzas/fci/{categoria}/{y}/{m}/{d}"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=20) as resp:
            parsed = json.loads(resp.read().decode("utf-8"))
        return parsed if isinstance(parsed, list) else []
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return []


def buscar_vcp(categoria, nombre_fondo, fecha_inicial):
    """Busca el vcp en fecha_inicial, y si no hay (fin de semana/feriado),
    camina hacia atras hasta 8 dias."""
    d = datetime.strptime(fecha_inicial, "%Y-%m-%d")
    for _ in range(8):
        ds = d.strftime("%Y-%m-%d")
        entries = fetch_fci_dia(categoria, ds)
        match = next((e for e in entries if e.get("fondo") == nombre_fondo), None)
        if match:
            return ds, match["vcp"]
        d -= timedelta(days=1)
    return None, None


def actualizar_fondos():
    series = {}
    if FONDOS_FILE.exists():
        with open(FONDOS_FILE, "r", encoding="utf-8") as f:
            series = json.load(f).get("series", {})

    hoy = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    resultado = []
    for ticker, info in FCI_FUNDS.items():
        fecha_real, vcp = buscar_vcp(info["categoria"], info["nombre"], hoy)
        if vcp is None:
            resultado.append({"ticker": ticker, "ok": False})
            continue
        serie = series.setdefault(ticker, [])
        if not any(p["date"] == fecha_real for p in serie):
            serie.append({"date": fecha_real, "vcp": vcp, "currency": info["currency"]})
            serie.sort(key=lambda p: p["date"])
        resultado.append({"ticker": ticker, "ok": True, "date": fecha_real, "vcp": vcp})

    out = {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "series": series}
    FONDOS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(FONDOS_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    return {"updated": out["updated"], "fondos": resultado}


def main():
    print("Bajando valor de cuotaparte de los fondos...")
    r = actualizar_fondos()
    for f in r["fondos"]:
        if f["ok"]:
            print(f"  {f['ticker']}: {f['vcp']} ({f['date']})")
        else:
            print(f"  {f['ticker']}: no se pudo obtener")
    print(f"\nGuardado en: {FONDOS_FILE}")


if __name__ == "__main__":
    main()
