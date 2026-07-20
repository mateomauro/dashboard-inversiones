#!/usr/bin/env python3
"""
Importa extractos CSV de Cocos Capital ("movimientos_cuenta*.csv") a data/inversiones.json.
Idempotente: identifica cada movimiento por nroTicket, así podés correrlo de nuevo
con un CSV mas reciente y solo agrega lo nuevo (no duplica).

Uso:
    python3 scripts/importar_cocos.py "Cocos Capital/movimientos_cuenta.csv" ["otro.csv" ...]

Si no pasás archivos, busca automaticamente todos los "movimientos_cuenta*.csv"
dentro de "Cocos Capital/".
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "inversiones.json"

# Mapeo de tipoOperacion (texto de Cocos) -> categoria normalizada
TYPE_MAP = {
    "Compra": "compra",
    "Compra Dolar Mep": "compra",
    "Compra bono Operatoria dolar MEP ARS": "mep_bono",
    "Compra bono Operatoria dolar MEP USD": "mep_bono",
    "Venta bono Operatoria dolar MEP ARS": "mep_bono",
    "Venta bono Operatoria dolar MEP USD": "mep_bono",
    "Compra Registracion USD": "mep_bono",
    "Venta Registracion ARS": "mep_bono",
    "Liq Suscripcion Fci Usd": "suscripcion_fci",
    "Liq Rescate Fci Usd": "rescate_fci",
    "Liquidacion Suscripcion Fci": "suscripcion_fci",
    "Liquidacion Rescate Fci": "rescate_fci",
    "Recibo De Cobro Dolares": "deposito",
    "Recibo De Cobro": "deposito",
    "Orden De Pago": "retiro",
    "Orden De Pago Usd": "retiro",
    "DIVIDENDOS EN ESPECIE": "dividendo",
    "Nota De Credito Conversion": "ajuste",
}


def parse_num(s):
    if s is None:
        return None
    s = s.strip()
    if s == "":
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_date(s):
    if not s or not s.strip():
        return None
    d, m, y = s.strip().split("-")
    return f"{y}-{m}-{d}"


def load_data():
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "version": 1,
        "platforms": {},
        "holdings": {},
        "snapshots": [],
    }


def save_data(data):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def import_csv(path, data):
    platform = data["platforms"].setdefault(
        "cocos", {"name": "Cocos Capital", "movements": []}
    )
    existing_ids = {m["id"] for m in platform["movements"]}
    added = 0
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            mid = row.get("nroTicket", "").strip()
            if not mid or mid in existing_ids:
                continue
            type_raw = row.get("tipoOperacion", "").strip()
            mov = {
                "id": mid,
                "comprobante": row.get("nroComprobante", "").strip(),
                "date": parse_date(row.get("fechaEjecucion")),
                "settleDate": parse_date(row.get("fechaLiquidacion")),
                "type": TYPE_MAP.get(type_raw, "otro"),
                "typeRaw": type_raw,
                "instrument": row.get("instrumento", "").strip() or None,
                "currency": row.get("moneda", "").strip() or None,
                "market": row.get("mercado", "").strip() or None,
                "quantity": parse_num(row.get("cantidad")),
                "price": parse_num(row.get("precio")),
                "gross": parse_num(row.get("montoBruto")),
                "commission": parse_num(row.get("comision")) or 0,
                "marketFee": parse_num(row.get("ddmm")) or 0,
                "iva": parse_num(row.get("iva")) or 0,
                "other": parse_num(row.get("otros")) or 0,
                "total": parse_num(row.get("total")),
            }
            platform["movements"].append(mov)
            existing_ids.add(mid)
            added += 1
    platform["movements"].sort(key=lambda m: (m["date"] or "", m["id"]))
    return added


def main():
    args = sys.argv[1:]
    if args:
        files = [Path(a) for a in args]
    else:
        files = sorted((ROOT / "Cocos Capital").glob("movimientos_cuenta*.csv"))

    if not files:
        print("No se encontraron archivos CSV para importar.")
        return

    data = load_data()
    total_added = 0
    for f in files:
        if not f.exists():
            print(f"  (no existe, salteado: {f})")
            continue
        n = import_csv(f, data)
        print(f"  {f.name}: {n} movimientos nuevos")
        total_added += n

    save_data(data)
    total = len(data["platforms"]["cocos"]["movements"])
    print(f"\nListo. {total_added} nuevos agregados. Total en Cocos: {total} movimientos.")
    print(f"Guardado en: {DATA_FILE}")


if __name__ == "__main__":
    main()
