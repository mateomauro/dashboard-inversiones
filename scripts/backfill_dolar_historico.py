#!/usr/bin/env python3
"""
Relleno UNICO hacia atras de data/dolar_historico.json, dia por dia, desde
el inicio de tu historial (2025-08-01) hasta hoy — necesario para que la
reconstruccion en vivo de Evolucion pueda convertir a USD el fondo en pesos
(Cocos Pesos Plus) en cualquier fecha pasada, no solo en las fechas puntuales
de tus movimientos.

Es seguro cortarlo y volver a correrlo: no vuelve a pedir fechas que ya
tiene guardadas. No toca data/inversiones.json (ningun dato personal).

Uso:
    python3 scripts/backfill_dolar_historico.py
"""
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from actualizar_dolar import fetch_rate  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DOLAR_FILE = ROOT / "data" / "dolar_historico.json"
START_DATE = "2025-08-01"


def main():
    cache = {}
    if DOLAR_FILE.exists():
        with open(DOLAR_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f).get("rates", {})

    d = datetime.strptime(START_DATE, "%Y-%m-%d")
    hoy = datetime.now(timezone.utc).replace(tzinfo=None)
    total_dias = (hoy - d).days + 1
    nuevos = 0
    dia_n = 0

    while d <= hoy:
        ds = d.strftime("%Y-%m-%d")
        dia_n += 1
        if ds not in cache:
            rate = fetch_rate(ds)
            if rate:
                cache[ds] = rate
                nuevos += 1
        if dia_n % 30 == 0:
            print(f"  {ds} — {dia_n}/{total_dias} dias, {nuevos} nuevas hasta ahora")
        d += timedelta(days=1)

    with open(DOLAR_FILE, "w", encoding="utf-8") as f:
        json.dump({"rates": cache}, f, ensure_ascii=False, indent=2)

    print(f"\nListo: {nuevos} cotizaciones nuevas. Total en cache: {len(cache)}")
    print(f"Guardado en: {DOLAR_FILE}")


if __name__ == "__main__":
    main()
