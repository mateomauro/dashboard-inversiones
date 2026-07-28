#!/usr/bin/env python3
"""
Baja la cotizacion historica del dolar MEP ("bolsa") para cada fecha en que
tengas un movimiento en pesos, y la guarda en data/dolar_historico.json.

Con esto el dashboard puede calcular automaticamente "cuanto invertiste en
USD" a partir de tus movimientos reales, en vez de que lo cargues a mano.

Fuente: ArgentinaDatos API (api.argentinadatos.com), gratis, sin API key.

Uso:
    python3 scripts/actualizar_dolar.py

Es seguro correrlo de nuevo: solo pide las fechas que todavia no tiene.
"""
import json
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
INVEST_FILE = ROOT / "data" / "inversiones.json"
DOLAR_FILE = ROOT / "data" / "dolar_historico.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; inversiones-tracker/1.0)"}


def fechas_necesarias():
    """Fechas (AAAA-MM-DD) de movimientos en ARS que necesitan conversion,
    mas la fecha de hoy (para mantener la cotizacion mas reciente al dia).

    Siempre incluye "hoy" aunque no exista data/inversiones.json, para que
    esto funcione tambien en la nube (GitHub Actions), donde ese archivo
    -por ser personal- nunca se sube al repo."""
    fechas = {datetime.now(timezone.utc).strftime("%Y-%m-%d")}
    if not INVEST_FILE.exists():
        return fechas
    with open(INVEST_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    tipos_relevantes = {"compra", "venta", "suscripcion_fci", "rescate_fci"}
    for plat in data.get("platforms", {}).values():
        for m in plat.get("movements", []):
            if m.get("currency") == "ARS" and m.get("type") in tipos_relevantes and m.get("date"):
                fechas.add(m["date"])
    return fechas


def fetch_rate(date_str):
    """date_str: 'AAAA-MM-DD'. Devuelve {'compra':..,'venta':..} o None."""
    y, m, d = date_str.split("-")
    url = f"https://api.argentinadatos.com/v1/cotizaciones/dolares/bolsa/{y}/{m}/{d}"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if "compra" in data and "venta" in data:
                return {"compra": data["compra"], "venta": data["venta"]}
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None
    return None


def actualizar_dolar():
    """Baja y guarda las cotizaciones que falten. Devuelve un resumen (dict)."""
    cache = {}
    if DOLAR_FILE.exists():
        with open(DOLAR_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f).get("rates", {})

    faltantes = sorted(d for d in fechas_necesarias() if d not in cache)
    nuevos, sin_datos = 0, 0
    for date_str in faltantes:
        rate = fetch_rate(date_str)
        if rate:
            cache[date_str] = rate
            nuevos += 1
        else:
            sin_datos += 1

    with open(DOLAR_FILE, "w", encoding="utf-8") as f:
        json.dump({"rates": cache}, f, ensure_ascii=False, indent=2)

    return {"pedidas": len(faltantes), "nuevas": nuevos, "sin_datos": sin_datos, "total_cache": len(cache)}


def main():
    print("Bajando cotizaciones historicas del dolar MEP...")
    r = actualizar_dolar()
    print(f"  Fechas pedidas: {r['pedidas']} · nuevas: {r['nuevas']} · sin datos: {r['sin_datos']}")
    print(f"  Total en cache: {r['total_cache']}")
    print(f"\nGuardado en: {DOLAR_FILE}")


if __name__ == "__main__":
    main()
