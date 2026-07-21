#!/usr/bin/env python3
"""
Baja precios historicos (en USD) para las acciones/CEDEARs y cripto que tenes cargadas,
y los guarda en data/precios_historicos.json.

Fuentes (gratis, sin API key):
- Acciones/ETFs de EE.UU. (SPY, QQQ, AAPL, etc.): Yahoo Finance (endpoint publico de graficos)
- Bitcoin: CoinGecko (coingecko.com) — plan gratis limitado a los ultimos 365 dias

El historial de precios de los fondos (Cocos Dolares Plus, Ualá, etc.) no se baja
aca: no hay fuente gratis para su historial completo. Su valor de HOY si se
actualiza solo, ver scripts/actualizar_valores.py (usa CAFCI via ArgentinaDatos).

Uso:
    python3 scripts/actualizar_precios.py

Es seguro correrlo de nuevo cuando quieras (por ejemplo, una vez por semana):
vuelve a bajar el historial completo y lo reemplaza, no duplica nada.
"""
import json
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
INVEST_FILE = ROOT / "data" / "inversiones.json"
PRICES_FILE = ROOT / "data" / "precios_historicos.json"

# Ticker -> simbolo (para acciones/ETFs de EE.UU. es el mismo ticker)
YAHOO_SYMBOLS = {
    "SPY": "SPY", "QQQ": "QQQ", "AAPL": "AAPL",
    "MSFT": "MSFT", "GOOGL": "GOOGL", "NVDA": "NVDA",
    "EFA": "EFA", "EEM": "EEM", "EWZ": "EWZ",
}
COINGECKO_IDS = {"BTC": "bitcoin"}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
START_DATE = "2025-08-01"  # un poco antes de la primera compra registrada
COINGECKO_MAX_DAYS = 365   # limite del plan gratis de CoinGecko


def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def fetch_yahoo(ticker, symbol):
    start_ts = int(datetime.strptime(START_DATE, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    end_ts = int(datetime.now(timezone.utc).timestamp())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?period1={start_ts}&period2={end_ts}&interval=1d"
    try:
        raw = fetch(url).decode("utf-8")
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"  {ticker}: error de red ({e})")
        return None
    try:
        data = json.loads(raw)
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        print(f"  {ticker}: Yahoo no devolvió datos utilizables (simbolo {symbol} incorrecto?)")
        return None
    out = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        date = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        out.append({"date": date, "priceUSD": round(close, 4)})
    return out


def fetch_coingecko(ticker, coin_id):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=usd&days={COINGECKO_MAX_DAYS}&interval=daily"
    try:
        raw = fetch(url).decode("utf-8")
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"  {ticker}: error de red ({e})")
        return None
    data = json.loads(raw)
    if "error" in data:
        print(f"  {ticker}: CoinGecko devolvió error ({data['error'].get('status',{}).get('error_message','?')})")
        return None
    prices = data.get("prices", [])
    out = []
    seen_dates = set()
    for ts_ms, price in prices:
        date = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        if date < START_DATE or date in seen_dates:
            continue
        seen_dates.add(date)
        out.append({"date": date, "priceUSD": round(price, 2)})
    return out


def tickers_to_fetch():
    """Lee holdings de inversiones.json para saber que tickers de Acciones/Cripto existen."""
    tickers = set()
    if INVEST_FILE.exists():
        with open(INVEST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for plat_holdings in data.get("holdings", {}).values():
            for h in plat_holdings:
                if h.get("group") in ("Acciones", "Cripto"):
                    tickers.add(h["instrument"])
    # siempre incluir los conocidos aunque todavia no esten en holdings
    tickers |= set(YAHOO_SYMBOLS.keys()) | set(COINGECKO_IDS.keys())
    return sorted(tickers)


def actualizar_precios():
    """Baja y guarda los precios. Devuelve un resumen (dict), lo usan tanto la
    linea de comandos como el boton 'Actualizar precios' del dashboard (via servidor.py)."""
    result = {}
    if PRICES_FILE.exists():
        with open(PRICES_FILE, "r", encoding="utf-8") as f:
            result = json.load(f).get("series", {})

    tickers_info = []
    for ticker in tickers_to_fetch():
        if ticker in YAHOO_SYMBOLS:
            series = fetch_yahoo(ticker, YAHOO_SYMBOLS[ticker])
            src = "yahoo"
        elif ticker in COINGECKO_IDS:
            series = fetch_coingecko(ticker, COINGECKO_IDS[ticker])
            src = "coingecko"
        else:
            continue
        if series:
            result[ticker] = series
            tickers_info.append({"ticker": ticker, "dias": len(series), "fuente": src, "ok": True})
        else:
            tickers_info.append({"ticker": ticker, "ok": False})

    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "series": result,
    }
    PRICES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PRICES_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return {"updated": out["updated"], "tickers": tickers_info}


def main():
    print("Bajando precios historicos...")
    resumen = actualizar_precios()
    for t in resumen["tickers"]:
        if t["ok"]:
            print(f"  {t['ticker']}: {t['dias']} dias ({t['fuente']})")
        else:
            print(f"  {t['ticker']}: no se pudo actualizar, se mantiene lo que habia")
    print(f"\nGuardado en: {PRICES_FILE}")


if __name__ == "__main__":
    main()
