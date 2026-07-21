#!/usr/bin/env python3
"""
Corre toda la cadena de actualizacion, sin necesidad de tener el servidor
ni el dashboard abiertos:

  1. actualizar_precios.py  — historial de precios (Yahoo/CoinGecko)
  2. actualizar_dolar.py    — cotizacion MEP para movimientos en pesos
  3. actualizar_valores.py  — recalcula el "Vale hoy" de cada tenencia
  4. guardar_snapshot.py    — guarda la foto de hoy para la Evolucion

Pensado para correr solo, una vez por dia, via el Programador de tareas de
Windows (no hace falta abrir el dashboard ni la terminal a mano).

Uso:
    python3 scripts/actualizar_todo.py
"""
import sys
import traceback
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
import actualizar_precios as ap  # noqa: E402
import actualizar_dolar as ad  # noqa: E402
import actualizar_valores as av  # noqa: E402
import guardar_snapshot as gs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = ROOT / "data" / "actualizacion.log"


def log(msg):
    line = f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}] {msg}"
    print(line)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def paso(nombre, fn):
    try:
        r = fn()
        log(f"OK  {nombre}: {r}")
        return r
    except Exception as e:
        log(f"ERROR {nombre}: {e}")
        log(traceback.format_exc())
        return None


def main():
    log("--- actualizar_todo: arrancando ---")
    paso("actualizar_precios", ap.actualizar_precios)
    paso("actualizar_dolar", ad.actualizar_dolar)
    paso("actualizar_valores", av.actualizar_valores)
    paso("guardar_snapshot", gs.guardar_snapshot)
    log("--- actualizar_todo: terminado ---")


if __name__ == "__main__":
    main()
