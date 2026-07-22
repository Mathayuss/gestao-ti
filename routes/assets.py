"""Rotas de ativos, perfil publico, QR Code, etiquetas e historico."""
import base64
import io
import os
import secrets

from flask import jsonify, render_template, request, send_file
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app import (
    PDF_OK,
    QR_OK,
    _get_setting,
    api_auth,
    app,
    asset_integrity_error_response,
    audit,
    check_public_token_rate_limit,
    clean_text,
    get_app_base_url,
    logger,
    new_id,
    parse_bool,
    proximo_patrimonio,
    requires,
    validate_asset_payload,
)
from extensions import db
from models import (
    Allocation,
    AllocationAsset,
    Asset,
    AuditLog,
    Incident,
    MaintenanceOrder,
    SupplyMovement,
)
from routes.blueprint import bp
from services.asset_service import normalize_asset_category_filter
from services.attachment_service import create_attachment_record

if PDF_OK:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas as rl_canvas

if QR_OK:
    import qrcode

@bp.route("/")
@login_required
def index():
    return render_template("index.html",
        build_version=app.config.get("BUILD_VERSION", "1.3.5"),
    )


def _public_assets_enabled():
    env = os.environ.get("PUBLIC_ASSETS_ENABLED")
    if env is not None:
        return parse_bool(env, default=False)
    return parse_bool(_get_setting("public_assets_enabled", False), default=False)


def _ensure_asset_public_token(asset):
    if not asset.public_token:
        asset.public_token = secrets.token_urlsafe(32)
        db.session.add(asset)
        db.session.commit()
    return asset.public_token


def _asset_public_url(asset):
    token = _ensure_asset_public_token(asset)
    return f"{get_app_base_url()}/public/asset/{token}"


@bp.route("/asset/<aid>")
@login_required
def asset_public(aid):
    a = db.session.get(Asset, aid)
    if not a: return "Ativo não encontrado", 404
    return render_template("asset_public.html", asset=a, public_card=_asset_public_card(a))


@bp.route("/public/asset/<token>")
def asset_public_by_token(token):
    if not check_public_token_rate_limit("asset_public", token):
        return "Muitas requisições. Aguarde um momento.", 429
    if not _public_assets_enabled():
        return "Consulta pública de ativos desativada.", 404
    a = db.session.execute(db.select(Asset).filter_by(public_token=clean_text(token, 100))).scalar_one_or_none()
    if not a:
        return "Ativo não encontrado", 404
    return render_template("asset_public.html", asset=a, public_card=_asset_public_card(a, public=True))


def _asset_public_card(asset, public=False):
    """Monta um resumo seguro e legível para consulta pública via QR Code."""
    def _join(parts, sep=" "):
        return sep.join(str(p).strip() for p in parts if str(p or "").strip())

    def _date_label(value):
        if not value:
            return "Sem registro"
        if hasattr(value, "strftime"):
            return value.strftime("%d/%m/%Y")
        raw = str(value).strip()
        if len(raw) >= 10 and raw[4:5] == "-" and raw[7:8] == "-":
            return f"{raw[8:10]}/{raw[5:7]}/{raw[0:4]}"
        return raw

    def _date_key(value):
        if not value:
            return ""
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    title = asset.hostname or _join([asset.categoria or "Ativo de TI", asset.fabricante, asset.modelo])
    brand_model = _join([asset.fabricante, asset.modelo]) or "Não informado"
    location = _join([asset.unidade, asset.setor], " - ") or "Local não informado"

    status_raw = asset.status or "Indefinido"
    status_map = {
        "Ativo": ("Ativo", "green"),
        "Alocado": ("Ativo", "green"),
        "Disponível": ("Em estoque", "blue"),
        "Manutenção": ("Em manutenção", "amber"),
        "Baixado": ("Baixado", "red"),
        "Inativo": ("Inativo", "gray"),
        "Descartado": ("Baixado", "gray"),
        "Vendido": ("Baixado", "gray"),
        "Extraviado": ("Inativo", "red"),
    }
    status_label, status_class = status_map.get(status_raw, (status_raw, "gray"))

    events = []
    if not public:
        for al in db.session.execute(
            db.select(
                Allocation.colaborador,
                Allocation.setor,
                Allocation.unidade,
                Allocation.data_aloc,
                Allocation.data_encerramento,
            ).where(Allocation.ativo_id == asset.id)
        ).all():
            event_date = al.data_encerramento or al.data_aloc
            event_label = "Devolução registrada" if al.data_encerramento else "Alocação registrada"
            if event_date:
                events.append({
                    "date": event_date,
                    "kind": event_label,
                    "detail": _join([al.colaborador, al.setor or al.unidade], " - ") or "Movimentação do ativo",
                    "sort": _date_key(event_date),
                })

        for m in db.session.execute(
            db.select(
                MaintenanceOrder.tipo,
                MaintenanceOrder.status,
                MaintenanceOrder.data_abertura,
                MaintenanceOrder.data_conclusao,
            ).where(MaintenanceOrder.asset_id == asset.id)
        ).all():
            event_date = m.data_conclusao or m.data_abertura
            if event_date:
                events.append({
                    "date": event_date,
                    "kind": "Manutenção",
                    "detail": _join([m.tipo, m.status], " - ") or "Ordem de serviço",
                    "sort": _date_key(event_date),
                })

        for mov in db.session.execute(
            db.select(
                SupplyMovement.data,
                SupplyMovement.motivo,
                SupplyMovement.tipo,
            ).where(SupplyMovement.ativo_id == asset.id)
        ).all():
            if mov.data:
                events.append({
                    "date": mov.data,
                    "kind": "Movimentação",
                    "detail": mov.motivo or mov.tipo or "Movimento de insumo",
                    "sort": _date_key(mov.data),
                })

    events.sort(key=lambda item: item["sort"])
    last_event = events[-1] if events else {
        "date": asset.criado_em,
        "kind": "Cadastro do ativo",
        "detail": "Registro inicial no inventário",
        "sort": _date_key(asset.criado_em),
    }

    category = (asset.categoria or "").lower()
    if "note" in category or "laptop" in category:
        icon = "notebook"
    elif "servid" in category or "server" in category:
        icon = "server"
    elif "switch" in category or "firewall" in category or "roteador" in category:
        icon = "network"
    elif "impress" in category:
        icon = "printer"
    elif "monitor" in category:
        icon = "monitor"
    else:
        icon = "desktop"

    public_url = request.base_url if not public else _asset_public_url(asset)
    return {
        "title": title,
        "code": asset.patrimonio or asset.id,
        "type": asset.categoria or "Ativo de TI",
        "brand_model": brand_model,
        "serial": "Restrito" if public else (asset.service_tag or "Não informado"),
        "status_label": status_label,
        "status_class": status_class,
        "location": "Restrito" if public else location,
        "owner": "Restrito" if public else (asset.colaborador or "Sem responsável vinculado"),
        "last_event": "Consulta pública" if public else f"{last_event['kind']} - {_date_label(last_event['date'])}",
        "last_event_detail": "Dados operacionais disponíveis apenas para usuários autenticados." if public else last_event["detail"],
        "icon": icon,
        "public_url": public_url,
        "qr_data_uri": _asset_public_qr_data_uri(),
    }


def _asset_public_qr_data_uri():
    if not QR_OK:
        return ""
    try:
        img = qrcode.make(request.base_url)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as exc:
        logger.warning("Falha ao gerar QR público: %s", exc)
        return ""


@bp.route("/api/assets", methods=["GET"])
@api_auth
def get_assets():
    q   = request.args.get("q","").lower()
    cat = normalize_asset_category_filter(request.args.get("categoria",""))
    stmt = db.select(Asset)
    if q:
        stmt = stmt.where(db.or_(Asset.hostname.ilike(f"%{q}%"),
                                  Asset.colaborador.ilike(f"%{q}%"),
                                  Asset.service_tag.ilike(f"%{q}%"),
                                  Asset.fabricante.ilike(f"%{q}%")))
    if cat:
        stmt = stmt.where(Asset.categoria == cat)
    return jsonify([a.to_dict() for a in db.session.execute(stmt).scalars().all()])


@bp.route("/api/assets/labels.pdf", methods=["POST"])
@api_auth
def asset_labels_pdf():
    if not PDF_OK:
        return jsonify({"error": "Geracao de PDF indisponivel. Instale reportlab."}), 503
    if not QR_OK:
        return jsonify({"error": "Geracao de QR Code indisponivel. Instale qrcode[pil]."}), 503

    from reportlab.lib.utils import ImageReader

    payload = request.get_json(silent=True) or {}
    ids = payload.get("ids") or []
    if not isinstance(ids, list):
        return jsonify({"error": "Lista de ativos invalida."}), 400

    ids = [clean_text(str(aid), 40) for aid in ids if clean_text(str(aid), 40)]
    ids = list(dict.fromkeys(ids))[:200]
    if not ids:
        return jsonify({"error": "Selecione ao menos um ativo para gerar etiquetas."}), 400

    cfg = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    def _clamped_int(value, default, min_value, max_value):
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = default
        return max(min_value, min(max_value, number))

    def _clamped_number(value, default, min_value, max_value):
        try:
            number = float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            number = default
        return round(max(min_value, min(max_value, number)), 1)

    size_key = clean_text(cfg.get("size"), 20) or "media"
    base_sizes = {
        "pequena": {"w": 58, "h": 38, "qr": 18, "font": 8.5},
        "media": {"w": 88, "h": 38, "qr": 22, "font": 9.5},
        "grande": {"w": 100, "h": 70, "qr": 30, "font": 11},
    }
    if size_key == "personalizada":
        custom_w = _clamped_number(cfg.get("customW"), 88, 25, 150)
        custom_h = _clamped_number(cfg.get("customH"), 38, 15, 100)
        base = min(custom_w, custom_h)
        max_qr = max(10, min(custom_w - 14, custom_h - 10))
        size_cfg = {
            "w": custom_w,
            "h": custom_h,
            "qr": min(max(10, round(base * 0.58)), max_qr),
            "font": min(12, max(7, round(custom_w / 9))),
        }
    else:
        size_cfg = base_sizes.get(size_key, base_sizes["media"])

    mm = cm / 10
    label_w = size_cfg["w"] * mm
    label_h = size_cfg["h"] * mm
    qr_delta = 5 if cfg.get("qr") == "grande" else (-5 if cfg.get("qr") == "compacto" else 0)
    layout_mode = clean_text(cfg.get("layout"), 20) or "auto"
    def _label_render_plan():
        width = size_cfg["w"]
        height = size_cfg["h"]
        tiny = width < 34 or height < 18
        compact = not tiny and (width < 52 or height < 28)
        pad_mm = 1 if tiny else (1.25 if compact else 2.3)
        gap_mm = 1.4 if compact else 2
        available_w = max(8, width - (pad_mm * 2))
        available_h = max(8, height - (pad_mm * 2))
        compact_qr_target = max(13, size_cfg["qr"] + qr_delta)
        if layout_mode == "qr-only" or tiny:
            qr_mm = max(10, min(available_w, available_h))
            return {"mode": "qr-only", "qr": qr_mm, "pad": pad_mm, "gap": gap_mm, "max_lines": 0}
        if layout_mode == "compact" or compact:
            qr_mm = max(10, min(available_h, available_w * 0.48, compact_qr_target))
            text_w = available_w - qr_mm - gap_mm
            if text_w < 12:
                qr_mm = max(10, min(available_w, available_h))
                return {"mode": "qr-only", "qr": qr_mm, "pad": pad_mm, "gap": gap_mm, "max_lines": 0}
            max_lines = max(2, min(4, int(available_h // 4.8)))
            return {"mode": "compact", "qr": qr_mm, "pad": pad_mm, "gap": gap_mm, "text_w": text_w, "max_lines": max_lines}
        qr_mm = max(12, min(height - 7, width * 0.36, size_cfg["qr"] + qr_delta))
        text_w = max(20, width - (pad_mm * 2) - qr_mm - gap_mm)
        return {"mode": "full", "qr": qr_mm, "pad": pad_mm, "gap": gap_mm, "text_w": text_w, "max_lines": 5}

    render_plan = _label_render_plan()
    qr_size = render_plan["qr"] * mm
    page_mode = "unitaria" if cfg.get("papel") == "unitaria" else "a4"
    page_size = (label_w, label_h) if page_mode == "unitaria" else A4
    margin = 0 if page_mode == "unitaria" else _clamped_int(cfg.get("margem"), 6, 0, 20) * mm
    gap = _clamped_int(cfg.get("gap"), 3, 0, 10) * mm
    copies = _clamped_int(cfg.get("copias"), 1, 1, 20)
    default_campos = {"hostname": True, "patrimonio": True, "serviceTag": True, "setor": True,
                      "colaborador": False, "ip": False, "garantia": False}
    campos = {**default_campos, **(cfg.get("campos") if isinstance(cfg.get("campos"), dict) else {})}
    empresa = clean_text(cfg.get("empresa"), 80)
    mostrar_sistema = cfg.get("mostrarSistema", True) is not False
    mostrar_logo = cfg.get("logoEmpresa") is True
    logo_no_qr = cfg.get("logoNoQr") is True
    empresa_cfg = _get_setting("empresa", {}) or {}
    logo_b64 = empresa_cfg.get("logo_base64", "") if isinstance(empresa_cfg, dict) else ""
    border_color = {"azul": (0.15, 0.39, 0.92), "cinza": (0.58, 0.64, 0.72), "sem": None}.get(
        clean_text(cfg.get("borda"), 20), (0.07, 0.09, 0.15)
    )

    def _logo_reader():
        if not logo_b64:
            return None
        try:
            raw_b64 = logo_b64.split(",", 1)[1] if "," in logo_b64 else logo_b64
            return ImageReader(io.BytesIO(base64.b64decode(raw_b64)))
        except Exception:
            return None

    logo_reader = _logo_reader()

    assets = db.session.execute(db.select(Asset).where(Asset.id.in_(ids))).scalars().all()
    by_id = {a.id: a for a in assets}
    ordered_assets = [by_id[aid] for aid in ids if aid in by_id]
    if not ordered_assets:
        return jsonify({"error": "Nenhum ativo encontrado para gerar etiquetas."}), 404

    def _qr_reader(asset):
        url = _asset_public_url(asset)
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=8,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        raw = io.BytesIO()
        img.save(raw, format="PNG")
        raw.seek(0)
        return ImageReader(raw)

    def _draw_qr(cv, asset, qr_x, qr_y, size):
        cv.drawImage(_qr_reader(asset), qr_x, qr_y, width=size, height=size, mask="auto")
        if not (logo_no_qr and logo_reader):
            return
        overlay = max(3 * mm, size * 0.24)
        overlay_x = qr_x + (size - overlay) / 2
        overlay_y = qr_y + (size - overlay) / 2
        cv.setFillColorRGB(1, 1, 1)
        cv.roundRect(
            overlay_x - 0.45 * mm,
            overlay_y - 0.45 * mm,
            overlay + 0.9 * mm,
            overlay + 0.9 * mm,
            0.7 * mm,
            stroke=0,
            fill=1,
        )
        cv.drawImage(
            logo_reader,
            overlay_x,
            overlay_y,
            width=overlay,
            height=overlay,
            preserveAspectRatio=True,
            mask="auto",
        )
        cv.setFillColorRGB(0, 0, 0)

    def _label_primary_code(asset):
        if campos.get("patrimonio") and asset.patrimonio:
            return asset.patrimonio
        if campos.get("serviceTag") and asset.service_tag:
            return asset.service_tag
        return asset.id

    def _compact_lines(asset):
        primary = _label_primary_code(asset)
        name = asset.hostname or asset.id
        lines = [(primary, True)]
        def add(text, bold=False):
            clean = str(text or "").strip()
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
        if campos.get("garantia") and asset.garantia:
            add(f"Gar {asset.garantia}")
        return lines

    def _draw_line(cv, text, x, y, size=7, bold=False, max_chars=34):
        if not text:
            return y
        cv.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        cv.drawString(x, y, str(text)[:max_chars])
        return y - (size + 2)

    def _draw_label(cv, asset, x, y):
        pad = render_plan["pad"] * mm
        gap_size = render_plan["gap"] * mm
        if border_color:
            cv.setStrokeColorRGB(*border_color)
            radius = (1.2 if render_plan["mode"] == "full" else 0.8) * mm
            cv.roundRect(x, y - label_h, label_w, label_h, radius, stroke=1, fill=0)

        text_x = x + pad
        text_top = y - pad - 7
        qr_x = x + label_w - pad - qr_size
        qr_y = y - pad - qr_size

        if render_plan["mode"] == "qr-only":
            qr_x = x + (label_w - qr_size) / 2
            qr_y = y - label_h + (label_h - qr_size) / 2
            _draw_qr(cv, asset, qr_x, qr_y, qr_size)
            return

        if render_plan["mode"] == "compact":
            qr_x = x + pad
            qr_y = y - label_h + (label_h - qr_size) / 2
            text_x = qr_x + qr_size + gap_size
            text_w = max(8 * mm, label_w - (text_x - x) - pad)
            _draw_qr(cv, asset, qr_x, qr_y, qr_size)
            cv.setFillColorRGB(0, 0, 0)
            lines = _compact_lines(asset)[:render_plan.get("max_lines", 2)]
            specs = []
            for text, bold in lines:
                max_size = 6.8 if bold else 5.2
                min_size = 4.1 if bold else 3.4
                factor = 0.42 if bold else 0.5
                size = max(min_size, min(max_size, (text_w / mm) / max(1, len(text) * factor)))
                specs.append((text, bold, size))
            total_h = sum(size + 1 for _, _, size in specs) - 1
            baseline = y - (label_h / 2) + (total_h / 2) - (specs[0][2] if specs else 0)
            for text, bold, size in specs:
                _draw_line(cv, text, text_x, baseline, size, bold, max(10, int((text_w / mm) * 1.8)))
                baseline -= size + 1
            return

        if mostrar_logo and logo_reader:
            logo_w = min(20 * mm, max(0, label_w - qr_size - 10 * mm))
            logo_h = 5 * mm
            if logo_w > 4 * mm:
                cv.drawImage(logo_reader, text_x, text_top - logo_h + 2, width=logo_w, height=logo_h,
                             preserveAspectRatio=True, mask="auto")
                text_top -= logo_h + 2

        if empresa:
            text_top = _draw_line(cv, empresa.upper(), text_x, text_top, 5.8, True, 36)

        if campos.get("hostname", True):
            name = asset.hostname or asset.id
            text_width = render_plan.get("text_w", 20) * mm
            font_size = max(6.5, min(size_cfg["font"], text_width / max(1, len(name)) * 1.7))
            text_top = _draw_line(cv, name, text_x, text_top, font_size, True, 30)

        lines = []
        if campos.get("patrimonio", True) and asset.patrimonio:
            lines.append(f"Pat: {asset.patrimonio}")
        if campos.get("serviceTag", True) and asset.service_tag:
            lines.append(f"ST: {asset.service_tag}")
        if campos.get("setor") and asset.setor:
            lines.append(f"Setor: {asset.setor}")
        if campos.get("colaborador") and asset.colaborador:
            lines.append(f"Usuario: {asset.colaborador}")
        if campos.get("ip") and asset.ip:
            lines.append(f"IP: {asset.ip}")
        if campos.get("garantia") and asset.garantia:
            lines.append(f"Gar: {asset.garantia}")
        for line in lines[:render_plan["max_lines"]]:
            text_top = _draw_line(cv, line, text_x, text_top, 6.8, False, 30)

        _draw_qr(cv, asset, qr_x, qr_y, qr_size)

        if mostrar_sistema:
            cv.setFillColorRGB(0, 0, 0)
            cv.roundRect(text_x, y - label_h + pad, 18 * mm, 4 * mm, 0.7 * mm, stroke=0, fill=1)
            cv.setFillColorRGB(1, 1, 1)
            cv.setFont("Helvetica-Bold", 5.5)
            cv.drawString(text_x + 1.2 * mm, y - label_h + pad + 1.2 * mm, "TI Control")
            cv.setFillColorRGB(0, 0, 0)

    buf = io.BytesIO()
    cv = rl_canvas.Canvas(buf, pagesize=page_size)
    page_w, page_h = page_size
    x = margin
    y = page_h - margin

    for asset in ordered_assets:
        for _ in range(copies):
            if page_mode == "a4":
                if x + label_w > page_w - margin + 0.1:
                    x = margin
                    y -= label_h + gap
                if y - label_h < margin - 0.1:
                    cv.showPage()
                    x = margin
                    y = page_h - margin
            else:
                x = 0
                y = page_h
            _draw_label(cv, asset, x, y)
            if page_mode == "unitaria":
                cv.showPage()
            else:
                x += label_w + gap

    cv.save()
    buf.seek(0)
    return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name="etiquetas_ativos.pdf")


@bp.route("/api/assets/proximo-patrimonio", methods=["GET"])
@api_auth
def get_proximo_patrimonio():
    return jsonify({"patrimonio": proximo_patrimonio()})


@bp.route("/api/assets/lote", methods=["POST"])
@requires("Administrador","Técnico TI")
def create_asset_lote():
    d = request.get_json() or {}
    try:
        quantidade = int(d.get("quantidade", 1))
    except (TypeError, ValueError):
        return jsonify({"error": "Quantidade inválida para entrada em lote."}), 400
    if quantidade < 1 or quantidade > 100:
        return jsonify({"error": "Quantidade deve estar entre 1 e 100."}), 400
    criados = []
    for _ in range(quantidade):
        pat = proximo_patrimonio()
        payload = dict(d)
        payload["patrimonio"] = pat
        if not clean_text(payload.get("hostname")):
            payload["hostname"] = f"{clean_text(payload.get('categoria'), 20) or 'ATIVO'}-{pat}"
        errors = validate_asset_payload(payload)
        if errors:
            db.session.rollback()
            return jsonify({"error": "Validação falhou", "details": errors}), 400
        a = Asset(
            id=new_id("A"),
            public_token=secrets.token_urlsafe(32),
            hostname=clean_text(payload.get("hostname"), 80),
            ip=clean_text(d.get("ip", "DHCP"), 40) or "DHCP",
            mac=clean_text(d.get("mac"), 20),
            service_tag=clean_text(d.get("serviceTag"), 40),
            os=clean_text(d.get("os"), 80),
            fabricante=clean_text(d.get("fabricante"), 60),
            modelo=clean_text(d.get("modelo"), 80),
            patrimonio=pat,
            nf=clean_text(d.get("nf"), 40),
            categoria=clean_text(d.get("categoria"), 40),
            status="Disponível",
            garantia=clean_text(d.get("garantia"), 10) or None,
        )
        db.session.add(a)
        audit("CRIAR", "ativos", a.id, f"Ativo {a.fabricante} {a.modelo} cadastrado em lote — {pat}")
        criados.append(a)
    try:
        db.session.commit()
    except IntegrityError as exc:
        return asset_integrity_error_response(exc)
    return jsonify([a.to_dict() for a in criados]), 201


@bp.route("/api/assets", methods=["POST"])
@requires("Administrador","Técnico TI")
def create_asset():
    d = request.get_json() or {}
    # Auto-gera patrimônio se não informado
    if not clean_text(d.get("patrimonio")):
        d = dict(d)
        d["patrimonio"] = proximo_patrimonio()
    if not clean_text(d.get("hostname")):
        d = dict(d)
        d["hostname"] = f"{clean_text(d.get('categoria'), 20) or 'ATIVO'}-{d['patrimonio']}"
    errors = validate_asset_payload(d)
    if errors:
        return jsonify({"error":"Validação do ativo falhou", "details": errors}), 400
    a = Asset(id=new_id("A"),
              public_token=secrets.token_urlsafe(32),
              hostname=clean_text(d.get("hostname"), 80), ip=clean_text(d.get("ip","DHCP"), 40) or "DHCP",
              mac=clean_text(d.get("mac"), 20), service_tag=clean_text(d.get("serviceTag"), 40),
              os=clean_text(d.get("os"), 80), fabricante=clean_text(d.get("fabricante"), 60),
              modelo=clean_text(d.get("modelo"), 80), patrimonio=clean_text(d.get("patrimonio"), 40),
              nf=clean_text(d.get("nf"), 40), categoria=clean_text(d.get("categoria"), 40),
              status=clean_text(d.get("status","Disponível"), 30) or "Disponível",
              colaborador=clean_text(d.get("colaborador"), 120),
              setor=clean_text(d.get("setor"), 80), unidade=clean_text(d.get("unidade"), 80),
              garantia=clean_text(d.get("garantia"), 10) or None)
    db.session.add(a)
    audit("CRIAR", "ativos", a.id, f"Ativo {a.hostname} cadastrado — patrimônio {a.patrimonio}")
    try:
        db.session.commit()
    except IntegrityError as exc:
        return asset_integrity_error_response(exc)
    return jsonify(a.to_dict()), 201


@bp.route("/api/assets/<aid>", methods=["GET"])
@api_auth
def get_asset(aid):
    a = db.get_or_404(Asset, aid)
    d = a.to_dict()
    d["incidentes"]    = [i.to_dict() for i in db.session.execute(db.select(Incident).filter_by(ref_id=aid)).scalars().all()]
    alocs = db.session.execute(
        db.select(Allocation)
        .outerjoin(AllocationAsset, AllocationAsset.allocation_id == Allocation.id)
        .where(db.or_(Allocation.ativo_id == aid, AllocationAsset.asset_id == aid))
        .distinct()
    ).scalars().all()
    d["alocacoes"]     = [al.to_dict(include_items=True) for al in alocs]
    d["auditLogs"]     = [l.to_dict() for l in db.session.execute(db.select(AuditLog).filter_by(ref_id=aid).order_by(AuditLog.data.desc()).limit(20)).scalars().all()]
    return jsonify(d)


@bp.route("/api/assets/<aid>", methods=["PUT"])
@requires("Administrador","Técnico TI")
def update_asset(aid):
    a = db.get_or_404(Asset, aid)
    d = request.get_json() or {}
    errors = validate_asset_payload(d, partial=True, exclude_id=aid)
    if errors:
        return jsonify({"error":"Validação do ativo falhou", "details": errors}), 400
    for k, v, max_len in [("hostname","hostname",80),("ip","ip",40),("mac","mac",20),("serviceTag","service_tag",40),
                  ("os","os",80),("fabricante","fabricante",60),("modelo","modelo",80),
                  ("patrimonio","patrimonio",40),("nf","nf",40),("categoria","categoria",40),
                  ("status","status",30),("colaborador","colaborador",120),
                  ("setor","setor",80),("unidade","unidade",80),("garantia","garantia",10)]:
        if k in d: setattr(a, v, clean_text(d[k], max_len))
    audit("EDITAR", "ativos", aid, f"Ativo {a.hostname} editado")
    try:
        db.session.commit()
    except IntegrityError as exc:
        return asset_integrity_error_response(exc)
    return jsonify(a.to_dict())


@bp.route("/api/assets/<aid>/upload", methods=["POST"])
@requires("Administrador","Técnico TI")
def upload_asset_attachment(aid):
    a = db.get_or_404(Asset, aid)
    att, error = create_attachment_record(
        "asset",
        aid,
        request.files.get("file"),
        request.form.get("category") or "Documento",
        request.form.get("description") or "",
    )
    if error:
        message, status = error
        return jsonify({"error": message}), status
    audit("ANEXO_UPLOAD", "ativos", aid, f"Anexo {att.original_name} adicionado ao ativo {a.hostname}")
    db.session.commit()
    return jsonify({"ok": True, "filename": att.original_name, "attachment": att.to_dict()}), 201


@bp.route("/api/assets/<aid>", methods=["DELETE"])
@requires("Administrador")
def delete_asset(aid):
    """Baixa lógica — não remove fisicamente se houver histórico."""
    a = db.get_or_404(Asset, aid)
    has_allocs  = db.session.execute(
        db.select(Allocation)
        .outerjoin(AllocationAsset, AllocationAsset.allocation_id == Allocation.id)
        .where(db.or_(Allocation.ativo_id == aid, AllocationAsset.asset_id == aid))
    ).scalar_one_or_none()
    has_inc     = db.session.execute(db.select(Incident).filter_by(ref_id=aid)).scalar_one_or_none()
    if has_allocs or has_inc:
        a.status = "Baixado"
        audit("BAIXA", "ativos", aid, f"Ativo {a.hostname} marcado como Baixado (histórico preservado)")
        db.session.commit()
        return jsonify({"ok":True, "msg":"Ativo marcado como Baixado (histórico preservado)."})
    db.session.delete(a)
    audit("EXCLUIR", "ativos", aid, f"Ativo {a.hostname} excluído")
    db.session.commit()
    return jsonify({"ok":True, "msg":"Ativo excluído."})


@bp.route("/api/assets/<aid>/history")
@api_auth
def get_asset_history(aid):
    """Linha do tempo unificada do ativo: cadastro, edições, alocações,
    manutenções, incidentes, auditorias QR e movimentos de insumo."""
    a = db.get_or_404(Asset, aid)
    events = []

    # ── Mapa auxiliar ───────────────────────────────────────────────────
    _ICONE = {
        "CRIAR":"plus","EDITAR":"edit","BAIXA":"download","EXCLUIR":"trash",
        "AUDITORIA":"mapPin","AUDITORIA_QR_PUBLICA":"smartphone",
        "ALOCAR":"link","ENCERRAR_ALOCACAO":"undo","ASSINAR_TERMO":"check",
        "MANUTENCAO_ABERTA":"wrench","MANUTENCAO_ENCERRADA":"flag",
        "MANUTENCAO_PECA":"package","MANUTENCAO_ATUALIZADA":"clipboard",
        "INCIDENTE":"warning","SAIDA":"package","DEVOLUCAO":"package",
        "DEFEITO":"warning","TROCA_PERIFERICO":"package",
    }
    _COR = {
        "CRIAR":"green","EDITAR":"blue","BAIXA":"red","EXCLUIR":"red",
        "AUDITORIA":"purple","AUDITORIA_QR_PUBLICA":"purple",
        "ALOCAR":"blue","ENCERRAR_ALOCACAO":"green","ASSINAR_TERMO":"green",
        "MANUTENCAO_ABERTA":"amber","MANUTENCAO_ENCERRADA":"green",
        "MANUTENCAO_PECA":"gray","MANUTENCAO_ATUALIZADA":"gray",
        "INCIDENTE":"red","SAIDA":"gray","DEVOLUCAO":"gray",
        "DEFEITO":"red","TROCA_PERIFERICO":"amber",
    }

    def _ev(tipo, acao, descricao, usuario, data_iso, extra=None):
        return {"tipo":tipo,"acao":acao,"descricao":descricao,"usuario":usuario or "sistema",
                "data":data_iso,"icone":_ICONE.get(acao,"clipboard"),"cor":_COR.get(acao,"gray"),
                "extra":extra or {}}

    # 1. Audit logs diretos do ativo (exclui os que já vêm de dados estruturados)
    _skip_acoes = {"ALOCAR","MANUTENCAO_ABERTA","MANUTENCAO_ENCERRADA","INCIDENTE",
                   "MANUTENCAO_PECA","MANUTENCAO_PECA_REMOVIDA","MANUTENCAO_ATUALIZADA"}
    for log in db.session.execute(
            db.select(AuditLog).where(AuditLog.ref_id == aid)
            .order_by(AuditLog.data)).scalars().all():
        if log.acao in _skip_acoes:
            continue
        events.append(_ev("auditoria", log.acao, log.detalhe or log.acao,
                          log.usuario, log.data.isoformat() if log.data else None))

    # 2. Alocações (estruturado — tem dados de termo e status)
    for al in db.session.execute(
            db.select(Allocation)
            .outerjoin(AllocationAsset, AllocationAsset.allocation_id == Allocation.id)
            .where(db.or_(Allocation.ativo_id == aid, AllocationAsset.asset_id == aid))
            .distinct()).scalars().all():
        events.append(_ev("alocacao","ALOCAR",
                          f"Alocado para {al.colaborador} — {al.setor} / {al.unidade}",
                          al.colaborador,
                          (al.data_aloc or "") + "T08:00:00" if al.data_aloc else None,
                          {"alocacaoId":al.id,"termo":al.termo,"termoStatus":al.termo_status,
                           "motivo":al.motivo,"email":al.email}))
        if al.termo_status == "Assinado" and al.data_assinatura:
            events.append(_ev("alocacao","ASSINAR_TERMO",
                              f"Termo {al.termo} assinado digitalmente",
                              al.colaborador,
                              al.data_assinatura.isoformat()))
        if al.data_encerramento:
            events.append(_ev("devolucao","ENCERRAR_ALOCACAO",
                              f"Devolução de {al.colaborador}",
                              al.colaborador,
                              al.data_encerramento + "T17:00:00"))

    # 3. Ordens de manutenção (aberta + encerramento + peças)
    for m in db.session.execute(
            db.select(MaintenanceOrder).where(MaintenanceOrder.asset_id == aid)).scalars().all():
        events.append(_ev("manutencao","MANUTENCAO_ABERTA",
                          f"OS {m.id}: {m.tipo} — {(m.descricao_defeito or '')[:80]}",
                          m.tecnico,
                          (m.data_abertura or "") + "T08:00:00" if m.data_abertura else None,
                          {"osId":m.id,"tipo":m.tipo,"status":m.status}))
        for p in m.parts:
            events.append(_ev("manutencao","MANUTENCAO_PECA",
                              f"Peça: {p.supply_nome} × {p.quantidade} — {p.custo_unitario:.2f}/un",
                              m.tecnico,
                              (m.data_abertura or "") + "T09:00:00" if m.data_abertura else None))
        if m.data_conclusao:
            cor_enc = "green" if m.status == "Concluída" else ("red" if m.status == "Sem reparo" else "gray")
            ic_enc  = "check" if m.status == "Concluída" else ("x" if m.status == "Sem reparo" else "square")
            events.append(_ev("manutencao","MANUTENCAO_ENCERRADA",
                              f"OS {m.id} encerrada: {m.status}"
                              + (f" · custo {m.custo_total:.2f}" if m.custo_total else ""),
                              m.tecnico,
                              m.data_conclusao + "T17:00:00",
                              {"osId":m.id,"status":m.status,"custoTotal":m.custo_total,
                               "icone":ic_enc,"cor":cor_enc}))

    # 4. Incidentes
    for inc in db.session.execute(
            db.select(Incident).where(Incident.ref_id == aid)).scalars().all():
        events.append(_ev("incidente","INCIDENTE",
                          f"{inc.tipo}: {(inc.descricao or '')[:80]}",
                          "sistema",
                          inc.data.isoformat() if inc.data else None,
                          {"incidenteId":inc.id,"status":inc.status}))

    # 5. Movimentos de insumo vinculados a este ativo
    for mov in db.session.execute(
            db.select(SupplyMovement).where(SupplyMovement.ativo_id == aid)).scalars().all():
        events.append(_ev("insumo", mov.tipo,
                          mov.descricao or f"{mov.tipo}: {mov.supply_nome}",
                          mov.colaborador,
                          mov.data.isoformat() if mov.data else None))

    events.sort(key=lambda e: e.get("data") or "")
    return jsonify({"asset": a.to_dict(), "totalEventos": len(events), "eventos": events})


@bp.route("/api/assets/<aid>/qrcode")
@api_auth
def asset_qrcode(aid):
    a = db.get_or_404(Asset, aid)
    url = _asset_public_url(a)
    if QR_OK:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
        return send_file(buf, mimetype="image/png")
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120"><rect width="120" height="120" fill="white"/><text x="60" y="60" text-anchor="middle" font-size="10" fill="#333">QR:{aid}</text></svg>'
    return svg, 200, {"Content-Type":"image/svg+xml"}


@bp.route("/api/public/assets/<aid>/audit", methods=["POST"])
def public_asset_audit(aid):
    return jsonify({"error": "Confirmacao publica removida. Use uma campanha autenticada de auditoria."}), 410


@bp.route("/api/audit-asset", methods=["POST"])
@requires("Administrador","Técnico TI")
def audit_asset_route():
    d = request.get_json()
    a = db.session.get(Asset, d.get("assetId",""))
    if not a: return jsonify({"error":"Ativo não encontrado"}), 404
    audit("AUDITORIA","ativos",a.id,f"Auditado em {d.get('local',a.unidade)} por {current_user.username}")
    db.session.commit()
    return jsonify({"ok":True,"hostname":a.hostname,"status":a.status,"colaborador":a.colaborador})
