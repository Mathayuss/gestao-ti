"""Agente local para imprimir jobs ZPL do TI Control em impressora Windows USB.

Uso:
  set TICONTROL_API_URL=https://seusistema.com.br
  set TICONTROL_PRINTER_ID=L42PRO-ALMOXARIFADO
  set TICONTROL_AGENT_TOKEN=token-gerado-no-sistema
  set TICONTROL_WINDOWS_PRINTER=ELGIN L42Pro
  python tools/l42pro_print_agent.py

Para instalar como serviço do Windows, use uma ferramenta como NSSM apontando
para este script dentro de uma venv com pywin32 instalado.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request


def load_env_file(path: str = "agent.env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


load_env_file()


API_URL = os.environ.get("TICONTROL_API_URL", "http://127.0.0.1:5000").rstrip("/")
PRINTER_ID = os.environ.get("TICONTROL_PRINTER_ID", "L42PRO-ALMOXARIFADO")
TOKEN = os.environ.get("TICONTROL_AGENT_TOKEN", "")
WINDOWS_PRINTER = os.environ.get("TICONTROL_WINDOWS_PRINTER", "ELGIN L42Pro")
POLL_SECONDS = float(os.environ.get("TICONTROL_POLL_SECONDS", "3"))
DRY_RUN = os.environ.get("TICONTROL_DRY_RUN", "0") == "1"


def request_json(method: str, path: str, payload: dict | None = None) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{API_URL}{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def send_raw_to_windows_printer(zpl: str) -> None:
    if DRY_RUN:
        print(zpl)
        return
    try:
        import win32print  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Instale pywin32: pip install pywin32") from exc

    handle = win32print.OpenPrinter(WINDOWS_PRINTER)
    try:
        job = win32print.StartDocPrinter(handle, 1, ("TI Control Label", None, "RAW"))
        try:
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(handle, zpl.encode("utf-8"))
            win32print.EndPagePrinter(handle)
        finally:
            win32print.EndDocPrinter(handle)
    finally:
        win32print.ClosePrinter(handle)


def main() -> int:
    if not TOKEN:
        print("TICONTROL_AGENT_TOKEN não definido.", file=sys.stderr)
        return 2
    print(f"TI Control Print Agent: {PRINTER_ID} -> {WINDOWS_PRINTER}")
    while True:
        try:
            job = request_json("GET", f"/api/print-jobs/next?printer_id={PRINTER_ID}")
            if not job or job.get("job") is None:
                time.sleep(POLL_SECONDS)
                continue
            job_id = job["id"]
            try:
                send_raw_to_windows_printer(job["zpl"])
                request_json("POST", f"/api/print-jobs/{job_id}/status", {"status": "printed", "message": "Etiqueta impressa com sucesso"})
                print(f"Job {job_id} impresso")
            except Exception as exc:
                request_json("POST", f"/api/print-jobs/{job_id}/status", {"status": "error", "message": str(exc)})
                print(f"Job {job_id} falhou: {exc}", file=sys.stderr)
        except urllib.error.HTTPError as exc:
            print(f"HTTP {exc.code}: {exc.read().decode('utf-8', 'ignore')}", file=sys.stderr)
            time.sleep(POLL_SECONDS)
        except Exception as exc:
            print(f"Erro no agente: {exc}", file=sys.stderr)
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
