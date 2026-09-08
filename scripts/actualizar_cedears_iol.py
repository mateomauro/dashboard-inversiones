#!/usr/bin/env python3
"""
Baja el precio REAL (en pesos, tal como cotiza en BYMA) de tus CEDEARs via
la API oficial de IOL (invertironline.com), y lo guarda en
data/cedears_iol.json.

A diferencia del metodo por ratio (precio real de EE.UU. / ratio del
CEDEAR), esto es el precio exacto — captura la prima/descuento real del
mercado argentino.

No usa NUNCA ningun endpoint de operar/comprar/vender — solo consulta
cotizaciones (solo lectura en la practica, aunque el token tecnicamente
pueda operar).

Requiere las variables de entorno IOL_USER e IOL_PASSWORD (nunca las
escribas en este archivo ni en ningun otro). No toca data/inversiones.json
(ningun dato personal).

Uso local (PowerShell):
    $env:IOL_USER = "tu_usuario"
    $env:IOL_PASSWORD = "tu_contraseña"
    python scripts/actualizar_cedears_iol.py

En GitHub Actions, IOL_USER e IOL_PASSWORD se toman de los Secrets del repo.
"""
import json
import os
import sys
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
OUT_FILE = ROOT / "data" / "cedears_iol.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; inversiones-tracker/1.0)"}

# Mismos 8 tickers de CEDEAR que ya seguimos por ratio (ver actualizar_valores.py)
TICKERS = ["QQQ", "SPY", "AAPL", "MSFT", "GOOGL", "NVDA", "EFA", "EEM", "GLD", "XLV", "XLP"]
MERCADO = "bCBA"


def obtener_token(usuario, password):
    body = urllib.parse.urlencode({
        "username": usuario, "password": password, "grant_type": "password",
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.invertironline.com/token", data=body,
        headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["access_token"]


def obtener_cotizacion(token, simbolo):
    url = f"https://api.invertironline.com/api/v2/{MERCADO}/Titulos/{simbolo}/Cotizacion"
    req = urllib.request.Request(url, headers={**HEADERS, "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def actualizar_cedears_iol():
    usuario = os.environ.get("IOL_USER")
    password = os.environ.get("IOL_PASSWORD")
    if not usuario or not password:
        return {"ok": False, "error": "faltan las variables de entorno IOL_USER / IOL_PASSWORD"}

    try:
        token = obtener_token(usuario, password)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError, json.JSONDecodeError) as e:
        return {"ok": False, "error": f"no se pudo obtener el token ({type(e).__name__})"}

    precios = {}
    resultado = []
    for simbolo in TICKERS:
        try:
            cot = obtener_cotizacion(token, simbolo)
            precios[simbolo] = {
                "precioARS": cot["ultimoPrecio"],
                "fechaHora": cot.get("fechaHora"),
                "moneda": cot.get("moneda"),
            }
            resultado.append({"ticker": simbolo, "ok": True, "precioARS": cot["ultimoPrecio"]})
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError, json.JSONDecodeError) as e:
            resultado.append({"ticker": simbolo, "ok": False, "error": type(e).__name__})

    out = {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "precios": precios}
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    return {"ok": True, "tickers": resultado}


def main():
    print("Bajando cotizaciones exactas de CEDEARs via API de IOL...")
    r = actualizar_cedears_iol()
    if not r.get("ok"):
        print("  Error: " + r["error"])
        sys.exit(1)
    for t in r["tickers"]:
        if t["ok"]:
            print(f"  {t['ticker']}: ARS {t['precioARS']}")
        else:
            print(f"  {t['ticker']}: no se pudo obtener ({t['error']})")
    print(f"\nGuardado en: {OUT_FILE}")


if __name__ == "__main__":
    main()
