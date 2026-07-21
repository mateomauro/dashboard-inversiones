#!/usr/bin/env python3
"""
Servidor local para el dashboard de inversiones.

Corre un mini servidor en tu compu (nunca en la nube) para que dashboard.html cargue
los datos automaticamente al abrir, y pueda "Guardar cambios" escribiendo directo en
data/inversiones.json — sin descargar archivos ni moverlos a mano.

Escucha en tu red WiFi de casa (no en internet), asi que tambien podes abrirlo desde
el celular si esta conectado al mismo WiFi que la compu.

Uso:
    python3 scripts/servidor.py
    (o doble clic en Iniciar.bat, en la carpeta principal del proyecto)

Se abre solo en el navegador. Para cerrarlo: Ctrl+C en esta ventana, o cerrarla.
"""
import http.server
import json
import shutil
import socket
import sys
import webbrowser
import threading
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import actualizar_precios as ap
import actualizar_dolar as ad
import actualizar_valores as av
import guardar_snapshot as gs

ROOT = Path(__file__).resolve().parent.parent
PORT = 8420
DATA_FILE = ROOT / "data" / "inversiones.json"
BACKUP_DIR = ROOT / "data" / "backups"
MAX_BACKUPS = 30


def hacer_backup():
    """Guarda una copia con fecha antes de sobreescribir, y deja como maximo
    MAX_BACKUPS copias (borra las mas viejas)."""
    if not DATA_FILE.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(DATA_FILE, BACKUP_DIR / f"inversiones-{stamp}.json")
    backups = sorted(BACKUP_DIR.glob("inversiones-*.json"))
    for old in backups[:-MAX_BACKUPS]:
        old.unlink()


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_POST(self):
        if self.path == "/guardar":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"JSON invalido")
                return
            hacer_backup()
            DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            print(f"  Guardado: {DATA_FILE}")
        elif self.path == "/actualizar-precios":
            try:
                resumen = ap.actualizar_precios()
                try:
                    resumen["dolar"] = ad.actualizar_dolar()
                except Exception as e:
                    resumen["dolar"] = {"error": str(e)}
                try:
                    hacer_backup()  # actualizar_valores() sobreescribe inversiones.json
                    resumen["valores"] = av.actualizar_valores()
                except Exception as e:
                    resumen["valores"] = {"error": str(e)}
                try:
                    resumen["snapshot"] = gs.guardar_snapshot()
                except Exception as e:
                    resumen["snapshot"] = {"ok": False, "error": str(e)}
                body = json.dumps(resumen).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
                ok = sum(1 for t in resumen["tickers"] if t["ok"])
                n_val = len(resumen.get("valores", {}).get("actualizados", []))
                print(f"  Precios actualizados: {ok}/{len(resumen['tickers'])} · dolar: {resumen['dolar']} · valores recalculados: {n_val}")
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode("utf-8"))
                print(f"  Error actualizando precios: {e}")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass  # no llenar la consola con cada pedido


def obtener_ip_local():
    """IP de la compu en la red WiFi de casa (para abrir desde el celular)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def main():
    local_url = f"http://localhost:{PORT}/dashboard.html"
    server = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    ip = obtener_ip_local()
    print(f"Dashboard corriendo en {local_url}")
    if ip:
        print(f"Desde el celular (mismo WiFi que esta compu): http://{ip}:{PORT}/dashboard.html")
    print("Dejá esta ventana abierta mientras lo usás. Ctrl+C (o cerrar la ventana) para salir.")
    threading.Timer(0.6, lambda: webbrowser.open(local_url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrado.")


if __name__ == "__main__":
    main()
