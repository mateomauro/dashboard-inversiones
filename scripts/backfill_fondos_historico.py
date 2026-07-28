#!/usr/bin/env python3
"""
Relleno UNICO hacia atras de data/fondos_historico.json, dia por dia, desde
el inicio de tu historial (2025-08-01) hasta hoy — para que el dashboard
pueda reconstruir el grafico de Evolucion completo en vivo, en el navegador,
sin depender de fotos guardadas a mano.

No hay endpoint de rango en la API (solo por dia exacto), asi que esto pide
un dia a la vez; agrupa los 3 fondos en solo 2 pedidos por dia (comparten
categoria CAFCI). Tarda varios minutos. Es seguro cortarlo y volver a
correrlo: no vuelve a pedir fechas que ya tiene guardadas.

No toca data/inversiones.json (ningun dato personal).

Uso:
    python3 scripts/backfill_fondos_historico.py
"""
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
from actualizar_fondos import FCI_FUNDS, HEADERS, fetch_fci_dia  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FONDOS_FILE = ROOT / "data" / "fondos_historico.json"
START_DATE = "2025-08-01"


def main():
    series = {}
    if FONDOS_FILE.exists():
        with open(FONDOS_FILE, "r", encoding="utf-8") as f:
            series = json.load(f).get("series", {})

    existentes = {t: {p["date"] for p in series.get(t, [])} for t in FCI_FUNDS}
    categorias = sorted({info["categoria"] for info in FCI_FUNDS.values()})

    d = datetime.strptime(START_DATE, "%Y-%m-%d")
    hoy = datetime.now(timezone.utc).replace(tzinfo=None)
    total_dias = (hoy - d).days + 1
    nuevos_total = 0
    dia_n = 0

    while d <= hoy:
        ds = d.strftime("%Y-%m-%d")
        dia_n += 1
        for categoria in categorias:
            tickers_de_esta_categoria = [t for t, info in FCI_FUNDS.items() if info["categoria"] == categoria]
            # si los 3 fondos de esta categoria ya tienen este dia, no hace falta pedirlo
            if all(ds in existentes[t] for t in tickers_de_esta_categoria):
                continue
            entries = fetch_fci_dia(categoria, ds)
            if not entries:
                continue
            for ticker in tickers_de_esta_categoria:
                if ds in existentes[ticker]:
                    continue
                info = FCI_FUNDS[ticker]
                match = next((e for e in entries if e.get("fondo") == info["nombre"]), None)
                if not match:
                    continue
                series.setdefault(ticker, []).append({"date": ds, "vcp": match["vcp"], "currency": info["currency"]})
                existentes[ticker].add(ds)
                nuevos_total += 1
        if dia_n % 30 == 0:
            print(f"  {ds} — {dia_n}/{total_dias} dias, {nuevos_total} puntos nuevos hasta ahora")
        d += timedelta(days=1)

    for ticker in series:
        series[ticker].sort(key=lambda p: p["date"])

    out = {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "series": series}
    with open(FONDOS_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\nListo: {nuevos_total} puntos nuevos agregados.")
    for ticker in FCI_FUNDS:
        print(f"  {ticker}: {len(series.get(ticker, []))} dias en total")
    print(f"\nGuardado en: {FONDOS_FILE}")


if __name__ == "__main__":
    main()
