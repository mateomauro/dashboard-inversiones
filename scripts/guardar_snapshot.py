#!/usr/bin/env python3
"""
Guarda la "foto de hoy" (snapshot) en data/inversiones.json — lo mismo que hace
el boton "+ Guardar foto de hoy" del dashboard, pero desde la terminal, para
poder automatizarlo (ej. con el Programador de tareas de Windows) y que la
pestaña Evolución tenga datos reales sin que tengas que acordarte de nada.

Pensado para correr despues de actualizar_precios.py + actualizar_valores.py,
asi la foto refleja valores frescos (no los que hayan quedado de la ultima vez
que abriste el dashboard).

Uso:
    python3 scripts/guardar_snapshot.py

Es seguro correrlo mas de una vez el mismo dia: si ya hay una foto de hoy,
la actualiza en vez de duplicarla (mismo comportamiento que el boton).
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
from actualizar_valores import instrument_matches_ticker, BUY_TYPES, SELL_TYPES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
INVEST_FILE = ROOT / "data" / "inversiones.json"
DOLAR_FILE = ROOT / "data" / "dolar_historico.json"


def ars_to_usd(amount_ars, date, dolar_rates):
    rate = dolar_rates.get(date)
    if not rate or not rate.get("venta"):
        return None
    return amount_ars / rate["venta"]


def movement_amount_usd(m, dolar_rates):
    if m.get("total") is None:
        return None
    if m.get("currency") == "USD":
        return abs(m["total"])
    if m.get("currency") == "ARS":
        return ars_to_usd(abs(m["total"]), m.get("date"), dolar_rates)
    return None


def analyze_holding(movements, ticker, dolar_rates):
    """Recorre el ledger en orden y calcula, con costo promedio, cuanto se
    invirtio realmente en USD (misma logica que analyzeHolding() en el
    dashboard). Devuelve (costo_usd_o_None, completo)."""
    relevant = [m for m in movements if instrument_matches_ticker(m.get("instrument"), ticker)]
    relevant.sort(key=lambda m: m.get("date") or "")
    qty = 0.0
    cost_usd = 0.0
    complete = True
    any_buy_cost = False
    for m in relevant:
        is_buy = m.get("type") in BUY_TYPES
        is_sell = m.get("type") in SELL_TYPES
        if not is_buy and not is_sell:
            continue
        amount_usd = movement_amount_usd(m, dolar_rates)
        if amount_usd is None and m.get("total") is not None:
            complete = False
        q = abs(m["quantity"]) if m.get("quantity") is not None else None
        if is_buy:
            if amount_usd is not None:
                cost_usd += amount_usd
                any_buy_cost = True
            if q is not None:
                qty += q
        elif is_sell:
            if q is not None and qty > 0:
                avg_cost = cost_usd / qty
                sold = min(q, qty)
                cost_usd -= avg_cost * sold
                qty -= sold
    return (cost_usd if any_buy_cost else None), complete


def effective_cost_basis(h, movements, dolar_rates):
    cost_usd, complete = analyze_holding(movements, h["instrument"], dolar_rates)
    if complete and cost_usd is not None:
        return cost_usd
    if (h.get("costBasisUSD") or 0) > 0:
        return h["costBasisUSD"]
    return 0.0


def guardar_snapshot():
    if not INVEST_FILE.exists():
        return {"ok": False, "error": "no existe data/inversiones.json"}

    with open(INVEST_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    dolar_rates = {}
    if DOLAR_FILE.exists():
        with open(DOLAR_FILE, "r", encoding="utf-8") as f:
            dolar_rates = json.load(f).get("rates", {})

    total_value = 0.0
    total_cost = 0.0
    for plat_key, holdings in data.get("holdings", {}).items():
        movements = data.get("platforms", {}).get(plat_key, {}).get("movements", [])
        for h in holdings:
            total_value += h.get("valueUSD") or 0
            total_cost += effective_cost_basis(h, movements, dolar_rates)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    snapshots = data.setdefault("snapshots", [])
    existing = next((s for s in snapshots if s["date"] == today), None)
    if existing:
        existing["investedUSD"] = round(total_cost, 2)
        existing["valueUSD"] = round(total_value, 2)
    else:
        snapshots.append({"date": today, "investedUSD": round(total_cost, 2), "valueUSD": round(total_value, 2)})

    with open(INVEST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return {"ok": True, "date": today, "valueUSD": round(total_value, 2), "investedUSD": round(total_cost, 2), "total_snapshots": len(snapshots)}


def main():
    r = guardar_snapshot()
    if not r.get("ok"):
        print("Error: " + r.get("error", "?"))
        return
    print(f"Foto guardada — {r['date']}: valor US$ {r['valueUSD']}, invertido US$ {r['investedUSD']}")
    print(f"Total de fotos guardadas: {r['total_snapshots']}")


if __name__ == "__main__":
    main()
