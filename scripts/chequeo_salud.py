#!/usr/bin/env python3
"""
Chequea que los datos de mercado (precios, dolar, fondos) esten razonablemente
al dia. Si alguno esta demasiado viejo, termina con error (exit code 1) para
que el workflow de GitHub Actions quede en rojo y te llegue el aviso por mail
de GitHub — en vez de que un problema de una fuente (Yahoo, CoinGecko,
ArgentinaDatos caidos o con la API cambiada) pase desapercibido para siempre.

No mira data/inversiones.json (ningun dato personal).

Uso:
    python3 scripts/chequeo_salud.py
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
PRICES_FILE = ROOT / "data" / "precios_historicos.json"
DOLAR_FILE = ROOT / "data" / "dolar_historico.json"
FONDOS_FILE = ROOT / "data" / "fondos_historico.json"
IOL_FILE = ROOT / "data" / "cedears_iol.json"

# Cuantos dias de atraso se toleran antes de considerarlo un problema real
# (no solo un fin de semana largo o un feriado).
MAX_DIAS_PRECIOS = 5
MAX_DIAS_DOLAR = 6
MAX_DIAS_FONDOS = 12
MAX_DIAS_IOL = 10
MIN_PROPORCION_TICKERS_OK = 0.7  # al menos 70% de los tickers deben estar frescos


def dias_desde(date_str, hoy):
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return 999999
    return (hoy - d).days


def chequear_precios(hoy):
    problemas = []
    if not PRICES_FILE.exists():
        return ["data/precios_historicos.json no existe"]
    with open(PRICES_FILE, "r", encoding="utf-8") as f:
        series = json.load(f).get("series", {})
    if not series:
        return ["data/precios_historicos.json no tiene ningun ticker"]
    frescos, total = 0, 0
    detalle = []
    for ticker, puntos in series.items():
        total += 1
        if not puntos:
            detalle.append(f"{ticker}: sin datos")
            continue
        atraso = dias_desde(puntos[-1].get("date"), hoy)
        if atraso <= MAX_DIAS_PRECIOS:
            frescos += 1
        else:
            detalle.append(f"{ticker}: ultimo dato hace {atraso} dias")
    if total and (frescos / total) < MIN_PROPORCION_TICKERS_OK:
        problemas.append(
            f"precios: solo {frescos}/{total} tickers actualizados en los ultimos {MAX_DIAS_PRECIOS} dias — "
            + "; ".join(detalle)
        )
    return problemas


def chequear_dolar(hoy):
    if not DOLAR_FILE.exists():
        return ["data/dolar_historico.json no existe"]
    with open(DOLAR_FILE, "r", encoding="utf-8") as f:
        rates = json.load(f).get("rates", {})
    if not rates:
        return ["data/dolar_historico.json no tiene ninguna cotizacion"]
    ultima = max(rates.keys())
    atraso = dias_desde(ultima, hoy)
    if atraso > MAX_DIAS_DOLAR:
        return [f"dolar: la cotizacion mas reciente es de hace {atraso} dias ({ultima})"]
    return []


def chequear_fondos(hoy):
    if not FONDOS_FILE.exists():
        return ["data/fondos_historico.json no existe"]
    with open(FONDOS_FILE, "r", encoding="utf-8") as f:
        series = json.load(f).get("series", {})
    if not series:
        return ["data/fondos_historico.json no tiene ningun fondo"]
    problemas = []
    for ticker, puntos in series.items():
        if not puntos:
            problemas.append(f"{ticker}: sin datos")
            continue
        atraso = dias_desde(puntos[-1].get("date"), hoy)
        if atraso > MAX_DIAS_FONDOS:
            problemas.append(f"{ticker}: ultimo VCP hace {atraso} dias")
    return problemas


def chequear_iol(hoy):
    """Precio exacto de CEDEARs via API de IOL. Si esta viejo o falta, la app
    cae sola al metodo por ratio (~95%) — no es critico, asi que esto es un
    aviso, no hace fallar el workflow."""
    if not IOL_FILE.exists():
        return ["data/cedears_iol.json no existe todavia (usando ratio como respaldo)"]
    with open(IOL_FILE, "r", encoding="utf-8") as f:
        precios = json.load(f).get("precios", {})
    if not precios:
        return ["data/cedears_iol.json no tiene ningun precio (usando ratio como respaldo)"]
    avisos = []
    for ticker, entry in precios.items():
        fecha_hora = entry.get("fechaHora")
        if not fecha_hora:
            continue
        atraso = dias_desde(fecha_hora[:10], hoy)
        if atraso > MAX_DIAS_IOL:
            avisos.append(f"{ticker}: ultimo precio de IOL hace {atraso} dias (usando ratio como respaldo)")
    return avisos


def main():
    hoy = datetime.now(timezone.utc).replace(tzinfo=None)
    problemas = chequear_precios(hoy) + chequear_dolar(hoy) + chequear_fondos(hoy)
    avisos = chequear_iol(hoy)
    if avisos:
        print("Chequeo de salud: avisos (no criticos, hay respaldo automatico)")
        for a in avisos:
            print("  - " + a)
    if problemas:
        print("Chequeo de salud: ENCONTRE PROBLEMAS")
        for p in problemas:
            print("  - " + p)
        sys.exit(1)
    print("Chequeo de salud: todo al dia.")


if __name__ == "__main__":
    main()
