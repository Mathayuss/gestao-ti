"""Fila de impressão RAW/ZPL para agentes locais de impressoras USB."""
import base64
import hashlib
import io
import logging
import os
import secrets
import zipfile
from datetime import datetime

import qrcode
from flask import jsonify, request, send_file
from flask_login import current_user
from sqlalchemy import func

from app import (
    _get_setting,
    api_auth,
    audit,
    clean_text,
    get_app_base_url,
    json_payload,
    parse_int,
    requires,
    safe_filename,
)
from extensions import db
from models import Asset, PrintJob, PrintPrinter
from routes.blueprint import bp

logger = logging.getLogger(__name__)


PRINT_JOB_STATUSES = {"pending", "processing", "printed", "error", "canceled", "retry"}


def _printer_token_hash(token):
    return hashlib.sha256(clean_text(token).encode("utf-8")).hexdigest()


def _agent_printer_from_request(printer_id):
    """
    Valida o agente da impressora usando Bearer token.
    Retorna PrintPrinter se autenticado, None se não autorizado.
    """
    # Extração robusta do token Bearer
    auth = request.headers.get("Authorization", "").strip()
    token = ""
    
    if auth:
        # Split em whitespace, máximo 2 partes: ["Bearer", "token"]
        parts = auth.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
    
    # Valida printer_id
    printer_id_clean = clean_text(printer_id, 60)
    if not printer_id_clean:
        return None
    
    # Busca impressora
    printer = db.session.get(PrintPrinter, printer_id_clean)
    if not printer:
        return None
    
    # Valida token (sem modificação antes do hash)
    if not token or printer.token_hash != _printer_token_hash(token):
        return None
    
    # Atualiza status
    printer.status = "Online"
    printer.last_seen = datetime.now()
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    
    return printer


def _zpl_text(value, max_len=80):
    text = clean_text(value, max_len)
    return text.replace("^", " ").replace("~", " ")


def _asset_public_url_for_print(asset):
    if not asset.public_token:
        asset.public_token = secrets.token_urlsafe(32)
        db.session.add(asset)
        db.session.flush()
    return f"{get_app_base_url()}/public/asset/{asset.public_token}"


def _label_size_from_cfg(cfg):
    def clamp_number(value, default, min_value, max_value):
        try:
            number = float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            number = default
        return round(max(min_value, min(max_value, number)), 1)

    size_key = clean_text((cfg or {}).get("size"), 20) or "media"
    sizes = {
        "pequena": {"w": 58, "h": 38, "qr": 18, "font": 28},
        "media": {"w": 88, "h": 38, "qr": 22, "font": 30},
        "grande": {"w": 100, "h": 70, "qr": 30, "font": 34},
    }
    if size_key == "personalizada":
        w = clamp_number((cfg or {}).get("customW"), 88, 25, 150)
        h = clamp_number((cfg or {}).get("customH"), 38, 15, 100)
        base = min(w, h)
        return {"w": w, "h": h, "qr": min(max(10, round(base * 0.58)), max(10, min(w - 14, h - 10))), "font": min(34, max(22, round(w / 3)))}
    return sizes.get(size_key, sizes["media"])


def _label_render_plan(size, cfg):
    qr_delta = 5 if (cfg or {}).get("qr") == "grande" else (-5 if (cfg or {}).get("qr") == "compacto" else 0)
    layout_mode = clean_text((cfg or {}).get("layout"), 20) or "auto"
    width = float(size["w"])
    height = float(size["h"])
    tiny = width < 34 or height < 18
    compact = not tiny and (width < 52 or height < 28)
    pad = 1 if tiny else (1.25 if compact else 3)
    gap = 1.4 if compact else 3
    available_w = max(8, width - (pad * 2))
    available_h = max(8, height - (pad * 2))
    compact_qr_target = max(13, size["qr"] + qr_delta)
    if layout_mode == "qr-only" or tiny:
        qr = max(10, min(available_w, available_h))
        return {"mode": "qr-only", "qr": qr, "pad": pad, "gap": gap, "max_lines": 0}
    if layout_mode == "compact" or compact:
        qr = max(10, min(available_h, available_w * 0.48, compact_qr_target))
        text_w = available_w - qr - gap
        if text_w < 12:
            qr = max(10, min(available_w, available_h))
            return {"mode": "qr-only", "qr": qr, "pad": pad, "gap": gap, "max_lines": 0}
        max_lines = max(2, min(4, int(available_h // 4.8)))
        return {"mode": "compact", "qr": qr, "pad": pad, "gap": gap, "text_w": text_w, "max_lines": max_lines}
    qr = max(12, min(height - 7, width * 0.36, size["qr"] + qr_delta))
    text_w = max(20, width - (pad * 2) - qr - gap)
    return {"mode": "full", "qr": qr, "pad": pad, "gap": gap, "text_w": text_w, "max_lines": 5}


def _printer_dpi(value):
    try:
        dpi = int(value)
    except (TypeError, ValueError):
        dpi = 203
    return max(150, min(600, dpi))


def _mm_to_dots(value, dpi=203):
    return int(round(float(value) * _printer_dpi(dpi) / 25.4))


def _qr_module_count(data):
    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=1,
            border=0,
        )
        qr.add_data(data)
        qr.make(fit=True)
        return int(qr.modules_count or 33)
    except Exception:
        return 33


def _zpl_qr_magnification(qr_dots, data):
    modules = max(21, _qr_module_count(data))
    return max(2, min(10, int(qr_dots // modules)))


def _zpl_qr_graphic(data, target_dots, logo_b64):
    try:
        from PIL import Image, ImageDraw

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=1,
            border=2,
        )
        qr.add_data(data)
        qr.make(fit=True)
        modules = int(qr.modules_count or 33) + 4
        scale = max(1, int(target_dots // modules))
        actual_size = modules * scale
        image = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
        image = image.resize((actual_size, actual_size), Image.Resampling.NEAREST)

        raw_b64 = logo_b64.split(",", 1)[1] if "," in logo_b64 else logo_b64
        logo = Image.open(io.BytesIO(base64.b64decode(raw_b64))).convert("RGBA")
        logo_size = max(8, int(actual_size * 0.22))
        logo.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)
        plate_size = max(logo.width, logo.height) + max(4, int(actual_size * 0.04))
        plate_x = (actual_size - plate_size) // 2
        plate_y = (actual_size - plate_size) // 2
        ImageDraw.Draw(image).rounded_rectangle(
            (plate_x, plate_y, plate_x + plate_size, plate_y + plate_size),
            radius=max(2, int(actual_size * 0.025)),
            fill="white",
        )
        logo_x = (actual_size - logo.width) // 2
        logo_y = (actual_size - logo.height) // 2
        image.alpha_composite(logo, (logo_x, logo_y))

        monochrome = image.convert("L").point(lambda value: 0 if value < 160 else 255, mode="1")
        bytes_per_row = (actual_size + 7) // 8
        payload = bytearray()
        pixels = monochrome.load()
        for y in range(actual_size):
            for byte_index in range(bytes_per_row):
                value = 0
                for bit in range(8):
                    x = byte_index * 8 + bit
                    if x < actual_size and pixels[x, y] == 0:
                        value |= 1 << (7 - bit)
                payload.append(value)
        return actual_size, bytes_per_row, payload.hex().upper()
    except Exception:
        logger.exception("Falha ao compor logo no QR Code ZPL")
        return None


def _zpl_qr_field(data, x, y, target_dots, cfg):
    if (cfg or {}).get("logoNoQr") is True:
        empresa_cfg = _get_setting("empresa", {}) or {}
        logo_b64 = empresa_cfg.get("logo_base64", "") if isinstance(empresa_cfg, dict) else ""
        if logo_b64:
            graphic = _zpl_qr_graphic(data, target_dots, logo_b64)
            if graphic:
                actual_size, bytes_per_row, hex_data = graphic
                graphic_x = max(0, int(x + (target_dots - actual_size) / 2))
                graphic_y = max(0, int(y + (target_dots - actual_size) / 2))
                total_bytes = bytes_per_row * actual_size
                return f"^FO{graphic_x},{graphic_y}^GFA,{total_bytes},{total_bytes},{bytes_per_row},{hex_data}^FS"
    magnification = _zpl_qr_magnification(target_dots, data)
    return f"^FO{x},{y}^BQN,2,{magnification}^FDLA,{_zpl_text(data, 180)}^FS"


def _zpl_for_asset_label(asset, cfg=None, copies=1, dpi=203):
    cfg = cfg or {}
    default_campos = {"hostname": True, "patrimonio": True, "serviceTag": True, "setor": True,
                      "colaborador": False, "ip": False, "garantia": False}
    campos = {**default_campos, **(cfg.get("campos") if isinstance(cfg.get("campos"), dict) else {})}
    mostrar_sistema = cfg.get("mostrarSistema", True) is not False
    empresa = clean_text(cfg.get("empresa"), 80)
    borda = clean_text(cfg.get("borda"), 20) or "preta"
    dpi = _printer_dpi(dpi)
    size = _label_size_from_cfg(cfg)
    plan = _label_render_plan(size, cfg)
    width = _mm_to_dots(size["w"], dpi)
    height = _mm_to_dots(size["h"], dpi)
    qr_size_mm = plan["qr"]
    pad = _mm_to_dots(plan["pad"], dpi)
    gap = _mm_to_dots(plan["gap"], dpi)
    qr_dots = _mm_to_dots(qr_size_mm, dpi)
    qr_x = max(pad, width - qr_dots - pad)
    qr_y = pad
    font = max(18, int(round(size["font"] * dpi / 203)))
    small = max(18, int(font * 0.72))
    line_gap = max(24, int(small * 1.25))
    y = pad
    x = pad
    text_width = max(_mm_to_dots(12 if plan["mode"] == "compact" else 22, dpi), qr_x - x - gap)
    footer_font = max(16, int(round(18 * dpi / 203)))
    footer_y = max(pad, height - _mm_to_dots(4.5, dpi))
    qr_link = _asset_public_url_for_print(asset)

    def label_primary_code():
        if campos.get("patrimonio") and asset.patrimonio:
            return asset.patrimonio
        if campos.get("serviceTag") and asset.service_tag:
            return asset.service_tag
        return asset.id

    def compact_lines():
        primary = label_primary_code()
        name = asset.hostname or asset.id
        lines = [(primary, True)]
        def add(text, bold=False):
            clean = clean_text(text, 80)
            if clean and clean not in [line[0] for line in lines]:
                lines.append((clean, bold))
        if campos.get("hostname") and name != primary:
            add(name)
        if campos.get("serviceTag") and asset.service_tag:
            add(f"ST {asset.service_tag}")
        if campos.get("setor") and asset.setor:
            add(f"Setor {asset.setor}")
        if campos.get("colaborador") and asset.colaborador:
            add(asset.colaborador)
        if campos.get("ip") and asset.ip:
            add(f"IP {asset.ip}")
        if campos.get("garantia") and getattr(asset, "garantia", None):
            add(f"Gar {asset.garantia}")
        return lines

    def border_cmd():
        if borda == "sem":
            return None
        thickness = max(2, int(round(dpi / 203 * 2)))
        return f"^FO0,0^GB{width},{height},{thickness}^FS"

    def base_zpl():
        zpl = [
            "^XA",
            "^CI28",
            "^LH0,0",
            "^LT0",
            f"^PW{width}",
            f"^LL{height}",
        ]
        border = border_cmd()
        if border:
            zpl.append(border)
        return zpl

    if plan["mode"] == "qr-only":
        qr_x = max(0, int((width - qr_dots) / 2))
        qr_y = max(0, int((height - qr_dots) / 2))
        zpl = base_zpl()
        zpl.extend([
            _zpl_qr_field(qr_link, qr_x, qr_y, qr_dots, cfg),
            f"^PQ{max(1, min(20, int(copies or 1)))}",
            "^XZ",
        ])
        return "\n".join(zpl)

    if plan["mode"] == "compact":
        qr_x = pad
        qr_y = max(0, int((height - qr_dots) / 2))
        text_x = qr_x + qr_dots + gap
        text_width = max(_mm_to_dots(10, dpi), width - text_x - pad)
        zpl = base_zpl()
        zpl.extend([
            _zpl_qr_field(qr_link, qr_x, qr_y, qr_dots, cfg),
        ])
        line_specs = []
        for text, bold in compact_lines()[:plan.get("max_lines", 2)]:
            max_font = font if bold else small
            min_font = max(12, int(round((16 if bold else 13) * dpi / 203)))
            factor = 0.62 if bold else 0.68
            line_font = max(min_font, min(max_font, int(text_width / max(1, len(str(text)) * factor))))
            line_specs.append((text, bold, line_font))
        total_h = sum(line_font + 4 for _, _, line_font in line_specs) - 4
        text_y = max(pad, int((height - total_h) / 2))
        for text, bold, line_font in line_specs:
            zpl.append(f"^FO{text_x},{text_y}^A0N,{line_font},{line_font}^FB{text_width},1,0,L,0^FD{_zpl_text(text, 44)}^FS")
            text_y += line_font + 4
        zpl.extend([
            f"^PQ{max(1, min(20, int(copies or 1)))}",
            "^XZ",
        ])
        return "\n".join(zpl)

    zpl = base_zpl()
    if empresa:
        company_font = max(14, int(round(18 * dpi / 203)))
        zpl.append(f"^FO{x},{y}^A0N,{company_font},{company_font}^FB{text_width},1,0,L,0^FD{_zpl_text(empresa.upper(), 50)}^FS")
        y += max(20, int(company_font * 1.25))
    if campos.get("hostname", True):
        zpl.append(f"^FO{x},{y}^A0N,{font},{font}^FB{text_width},1,0,L,0^FD{_zpl_text(asset.hostname or asset.id, 36)}^FS")
        y += line_gap + 8
    fields = []
    if campos.get("patrimonio") and asset.patrimonio:
        fields.append(("Pat:", asset.patrimonio))
    if campos.get("serviceTag") and asset.service_tag:
        fields.append(("ST:", asset.service_tag))
    if campos.get("setor") and asset.setor:
        fields.append(("Setor:", asset.setor))
    if campos.get("colaborador") and asset.colaborador:
        fields.append(("Usuario:", asset.colaborador))
    if campos.get("ip") and asset.ip:
        fields.append(("IP:", asset.ip))
    if campos.get("garantia") and getattr(asset, "garantia", None):
        fields.append(("Gar:", asset.garantia))
    for label, value in fields:
        if value and y < footer_y - line_gap:
            zpl.append(f"^FO{x},{y}^A0N,{small},{small}^FB{text_width},1,0,L,0^FD{_zpl_text(label + ' ' + str(value), 44)}^FS")
            y += line_gap
    zpl.append(_zpl_qr_field(qr_link, qr_x, qr_y, qr_dots, cfg))
    if mostrar_sistema:
        zpl.append(f"^FO{x},{footer_y}^A0N,{footer_font},{footer_font}^FDTI Control^FS")
    zpl.extend([
        f"^PQ{max(1, min(20, int(copies or 1)))}",
        "^XZ",
    ])
    return "\n".join(zpl)


@bp.route("/api/print-printers", methods=["GET"])
@api_auth
def list_print_printers():
    printers = db.session.execute(db.select(PrintPrinter).order_by(PrintPrinter.id)).scalars().all()
    now = datetime.now()
    result = []
    for printer in printers:
        data = printer.to_dict()
        if not printer.last_seen or (now - printer.last_seen).total_seconds() > 30:
            data["status"] = "Offline"
        result.append(data)
    return jsonify(result)


def _apply_printer_fields(printer, data):
    printer.name = clean_text(data.get("name") or printer.name or printer.id, 120)
    printer.location = clean_text(data.get("location"), 120)
    printer.printer_type = clean_text(data.get("type") or printer.printer_type or "USB/ZPL", 40)
    printer.windows_name = clean_text(
        data.get("windowsName") or data.get("windows_name") or printer.windows_name,
        120,
    )
    printer.dpi = _printer_dpi(data.get("dpi") or printer.dpi or 203)


@bp.route("/api/print-printers", methods=["POST"])
@requires("Administrador", "Técnico TI")
def create_print_printer():
    d = json_payload()
    printer_id = safe_filename(clean_text(d.get("id") or d.get("printerId"), 60)).upper()
    if not printer_id:
        return jsonify({"error": "Informe o ID da impressora/agente."}), 400
    if db.session.get(PrintPrinter, printer_id):
        return jsonify({"error": "Já existe um agente com este ID. Edite o cadastro existente."}), 409
    token = secrets.token_urlsafe(32)
    printer = PrintPrinter(id=printer_id)
    _apply_printer_fields(printer, d)
    printer.token_hash = _printer_token_hash(token)
    printer.status = "Offline"
    db.session.add(printer)
    audit("CRIAR_IMPRESSORA", "impressao", printer_id, f"Agente {printer.name} cadastrado/atualizado")
    db.session.commit()
    data = printer.to_dict()
    data["token"] = token
    return jsonify(data), 201


@bp.route("/api/print-printers/<printer_id>", methods=["PUT"])
@requires("Administrador", "Técnico TI")
def update_print_printer(printer_id):
    printer = db.session.get(PrintPrinter, clean_text(printer_id, 60))
    if not printer:
        return jsonify({"error": "Impressora/agente não encontrado."}), 404
    _apply_printer_fields(printer, json_payload())
    audit("EDITAR_IMPRESSORA", "impressao", printer.id, f"Agente {printer.name} atualizado")
    db.session.commit()
    return jsonify(printer.to_dict())


@bp.route("/api/print-printers/<printer_id>/token", methods=["POST"])
@requires("Administrador", "Técnico TI")
def renew_print_printer_token(printer_id):
    printer = db.session.get(PrintPrinter, clean_text(printer_id, 60))
    if not printer:
        return jsonify({"error": "Impressora/agente não encontrado."}), 404
    token = secrets.token_urlsafe(32)
    printer.token_hash = _printer_token_hash(token)
    printer.status = "Offline"
    audit("RENOVAR_TOKEN_IMPRESSORA", "impressao", printer.id, f"Token do agente {printer.name} renovado")
    db.session.commit()
    data = printer.to_dict()
    data["token"] = token
    return jsonify(data)


@bp.route("/api/print-printers/<printer_id>", methods=["DELETE"])
@requires("Administrador", "Técnico TI")
def delete_print_printer(printer_id):
    printer = db.session.get(PrintPrinter, clean_text(printer_id, 60))
    if not printer:
        return jsonify({"error": "Impressora/agente não encontrado."}), 404
    active_jobs = db.session.execute(
        db.select(func.count(PrintJob.id)).where(
            PrintJob.printer_id == printer.id,
            PrintJob.status.in_(["pending", "processing", "retry"]),
        )
    ).scalar_one()
    if active_jobs:
        return jsonify({"error": "Este agente possui trabalhos pendentes. Conclua ou cancele a fila antes de removê-lo."}), 409
    printer_name = printer.name or printer.id
    db.session.delete(printer)
    audit("EXCLUIR_IMPRESSORA", "impressao", printer_id, f"Agente {printer_name} removido")
    db.session.commit()
    return jsonify({"ok": True})


@bp.route("/api/print-agent/download", methods=["GET"])
@requires("Administrador", "Técnico TI")
def download_print_agent():
    printer_id = clean_text(request.args.get("printer_id") or request.args.get("printerId") or "L42PRO-ALMOXARIFADO", 60)
    windows_printer = clean_text(request.args.get("windows_printer") or "ELGIN L42Pro", 120)
    agent_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tools", "l42pro_print_agent.py")
    try:
        with open(agent_path, "r", encoding="utf-8") as fh:
            agent_source = fh.read()
    except OSError:
        return jsonify({"error": "Arquivo do agente local não encontrado no servidor."}), 500

    env_example = "\n".join([
        f"TICONTROL_API_URL={get_app_base_url()}",
        f"TICONTROL_PRINTER_ID={printer_id}",
        "TICONTROL_AGENT_TOKEN=COLE_AQUI_O_TOKEN_GERADO_NO_SISTEMA",
        f"TICONTROL_WINDOWS_PRINTER={windows_printer}",
        "TICONTROL_POLL_SECONDS=3",
        "TICONTROL_DRY_RUN=0",
        "",
    ])
    run_bat = """@echo off
setlocal
if exist agent.env (
  for /f "usebackq tokens=1,* delims==" %%A in ("agent.env") do set "%%A=%%B"
)
python l42pro_print_agent.py
pause
"""
    install_ps1 = """Write-Host "TI Control Print Agent"
Write-Host "1. Instale Python 3.11+"
Write-Host "2. Execute: pip install -r requirements.txt"
Write-Host "3. Renomeie agent.env.example para agent.env e cole o token"
Write-Host "4. Teste com: .\\run-agent.bat"
Write-Host ""
Write-Host "Para serviço do Windows, use NSSM apontando para run-agent.bat."
"""
    readme = f"""# TI Control Print Agent - Elgin L42Pro USB

Este pacote instala o agente local que busca jobs de impressão no TI Control e envia ZPL RAW para a impressora Windows.

## Instalação rápida

1. Instale o driver da Elgin L42Pro no Windows.
2. Renomeie a impressora no Windows para: `{windows_printer}`.
3. Instale Python 3.11+.
4. Na pasta deste pacote, execute:

```bat
pip install -r requirements.txt
copy agent.env.example agent.env
notepad agent.env
run-agent.bat
```

5. No arquivo `agent.env`, cole o token exibido pelo TI Control no campo `TICONTROL_AGENT_TOKEN`.

## Configuração esperada

- API: `{get_app_base_url()}`
- Printer ID: `{printer_id}`
- Impressora Windows: `{windows_printer}`
- DPI: configure no cadastro do agente dentro do TI Control conforme a resolução real da impressora.

## Serviço Windows

Para produção, instale como serviço usando NSSM:

```bat
nssm install EtiquetaPrintAgent C:\\caminho\\do\\pacote\\run-agent.bat
nssm start EtiquetaPrintAgent
```

O agente nunca recebe senha de usuário. Ele usa apenas o token do agente cadastrado no sistema.
"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("l42pro_print_agent.py", agent_source)
        zf.writestr("requirements.txt", "pywin32>=306\n")
        zf.writestr("agent.env.example", env_example)
        zf.writestr("run-agent.bat", run_bat)
        zf.writestr("install-help.ps1", install_ps1)
        zf.writestr("README.md", readme)
    buf.seek(0)
    audit("DOWNLOAD_PRINT_AGENT", "impressao", printer_id, "Pacote do agente local baixado")
    db.session.commit()
    return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=f"ti-control-print-agent-{safe_filename(printer_id)}.zip")


@bp.route("/api/print-jobs", methods=["GET"])
@api_auth
def list_print_jobs():
    printer_id = clean_text(request.args.get("printer_id") or request.args.get("printerId"), 60)
    status = clean_text(request.args.get("status"), 20)
    stmt = db.select(PrintJob).order_by(PrintJob.created_at.desc()).limit(100)
    if printer_id:
        stmt = stmt.where(PrintJob.printer_id == printer_id)
    if status:
        stmt = stmt.where(PrintJob.status == status)
    return jsonify([j.to_dict() for j in db.session.execute(stmt).scalars().all()])


@bp.route("/api/print-jobs", methods=["POST"])
@requires("Administrador", "Técnico TI")
def create_print_job():
    d = json_payload()
    printer_id = clean_text(d.get("printer_id") or d.get("printerId"), 60)
    printer = db.session.get(PrintPrinter, printer_id)
    if not printer:
        return jsonify({"error": "Impressora/agente não encontrado."}), 404
    copies = parse_int(d.get("copies") or d.get("copias"), default=1, minimum=1)
    copies = min(copies, 20)
    template = clean_text(d.get("template") or "ETQ_PATRIMONIO_ZPL", 80)
    cfg = d.get("config") if isinstance(d.get("config"), dict) else {}
    dpi = _printer_dpi(printer.dpi or 203)
    ids = d.get("ids") or []
    if isinstance(ids, str):
        ids = [ids]
    jobs = []

    if ids:
        clean_ids = list(dict.fromkeys([clean_text(aid, 40) for aid in ids if clean_text(aid, 40)]))[:200]
        assets = db.session.execute(db.select(Asset).where(Asset.id.in_(clean_ids))).scalars().all()
        by_id = {a.id: a for a in assets}
        for asset in [by_id[aid] for aid in clean_ids if aid in by_id]:
            data = {
                "assetId": asset.id,
                "patrimonio": asset.patrimonio,
                "descricao": " ".join([asset.hostname or "", asset.fabricante or "", asset.modelo or ""]).strip(),
                "serial": asset.service_tag,
                "setor": asset.setor,
                "qrcode": _asset_public_url_for_print(asset),
            }
            jobs.append(PrintJob(
                printer_id=printer_id,
                template=template,
                status="pending",
                copies=copies,
                data=data,
                zpl=_zpl_for_asset_label(asset, cfg, copies, dpi),
                created_by=current_user.username,
            ))
    else:
        data = d.get("data") if isinstance(d.get("data"), dict) else {}
        zpl = clean_text(d.get("zpl"), 20000)
        if not zpl:
            fake = type("LabelData", (), {
                "id": data.get("assetId") or data.get("patrimonio") or "manual",
                "hostname": data.get("descricao") or data.get("patrimonio"),
                "categoria": "",
                "fabricante": "",
                "modelo": "",
                "patrimonio": data.get("patrimonio"),
                "service_tag": data.get("serial"),
                "setor": data.get("setor"),
                "colaborador": data.get("colaborador"),
                "ip": data.get("ip"),
            })()
            zpl = _zpl_for_asset_label(fake, cfg, copies, dpi)
        jobs.append(PrintJob(
            printer_id=printer_id,
            template=template,
            status="pending",
            copies=copies,
            data=data,
            zpl=zpl,
            created_by=current_user.username,
        ))

    if not jobs:
        return jsonify({"error": "Nenhum ativo válido para impressão."}), 400
    for job in jobs:
        db.session.add(job)
    audit("CRIAR_PRINT_JOB", "impressao", printer_id, f"{len(jobs)} job(s) enviados para fila")
    db.session.commit()
    return jsonify({"ok": True, "jobs": [j.to_dict() for j in jobs]}), 201


@bp.route("/api/print-jobs/next", methods=["GET"])
def next_print_job():
    printer_id = clean_text(request.args.get("printer_id") or request.args.get("printerId"), 60)
    printer = _agent_printer_from_request(printer_id)
    if not printer:
        # Log detalhado do erro
        auth = request.headers.get("Authorization", "")
        has_auth = bool(auth)
        logger.warning(f"[PRINTER] Acesso não autorizado a print jobs: printer_id={printer_id}, has_auth={has_auth}, ip={request.remote_addr}")
        return jsonify({"error": "Agente não autorizado."}), 401
    job = db.session.execute(
        db.select(PrintJob)
        .where(PrintJob.printer_id == printer_id, PrintJob.status.in_(["pending", "retry"]))
        .order_by(PrintJob.created_at.asc())
    ).scalars().first()
    if not job:
        db.session.commit()
        return jsonify({"job": None})
    job.status = "processing"
    job.picked_at = datetime.now()
    db.session.commit()
    logger.info(f"[PRINTER] Job {job.id} enviado para impressora {printer_id}")
    return jsonify(job.to_dict(include_zpl=True))


@bp.route("/api/print-jobs/<int:job_id>/status", methods=["POST"])
def update_print_job_status(job_id):
    job = db.get_or_404(PrintJob, job_id)
    printer = _agent_printer_from_request(job.printer_id)
    if not printer:
        logger.warning(f"[PRINTER] Atualização de status não autorizada: job_id={job_id}, printer_id={job.printer_id}, ip={request.remote_addr}")
        return jsonify({"error": "Agente não autorizado."}), 401
    d = json_payload()
    status = clean_text(d.get("status"), 20)
    if status not in PRINT_JOB_STATUSES:
        return jsonify({"error": "Status de impressão inválido."}), 400
    old_status = job.status
    job.status = status
    job.message = clean_text(d.get("message"), 2000)
    if status in {"printed", "error", "canceled"}:
        job.finished_at = datetime.now()
    db.session.commit()
    
    # Log com nível apropriado
    log_level = logging.INFO if status == "printed" else logging.WARNING
    logger.log(log_level, f"[PRINTER] Job {job_id}: {old_status} → {status}, printer={job.printer_id}, msg={job.message[:50]}")
    
    return jsonify(job.to_dict())


@bp.route("/api/print-printers/<printer_id>/test", methods=["POST"])
@requires("Administrador", "Técnico TI")
def test_printer_auth(printer_id):
    """
    Endpoint para testar a autenticação de uma impressora.
    Útil para troubleshooting.
    
    POST body: {"token": "TOKEN_DO_AGENTE"}
    
    Resposta:
    {
        "printer_id": "L42PRO-ALMOXARIFADO",
        "printer_name": "Impressora L42Pro",
        "printer_status": "Online",
        "printer_last_seen": "2026-06-25T10:30:45",
        "auth_ok": true,
        "token_provided": true,
        "token_hash_match": true,
        "message": "Autenticação bem-sucedida"
    }
    """
    printer_id_clean = clean_text(printer_id, 60)
    printer = db.session.get(PrintPrinter, printer_id_clean)
    
    if not printer:
        return jsonify({"error": "Impressora não encontrada"}), 404
    
    d = json_payload()
    test_token = d.get("token", "")
    
    if not test_token:
        return jsonify({"error": "Forneça um 'token' no corpo da requisição"}), 400
    
    # Testa autenticação
    token_hash = _printer_token_hash(test_token)
    auth_ok = printer.token_hash == token_hash
    
    response = {
        "printer_id": printer.id,
        "printer_name": printer.name,
        "printer_status": printer.status,
        "printer_last_seen": printer.last_seen.isoformat() if printer.last_seen else None,
        "auth_ok": auth_ok,
        "token_provided": bool(test_token),
        "token_hash_match": auth_ok,
        "message": "Autenticação bem-sucedida" if auth_ok else "Token incorreto - não corresponde ao registrado no sistema"
    }
    
    logger.info(f"[PRINTER] Teste de autenticação: printer_id={printer_id}, auth_ok={auth_ok}, user={current_user.username}")
    
    return jsonify(response), 200
