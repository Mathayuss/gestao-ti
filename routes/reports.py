"""Rotas Flask extraidas do app.py.

Este modulo usa uma ponte temporaria para acessar modelos, helpers e extensoes
definidos em app.py. Em uma proxima etapa, esses itens podem migrar para
pacotes dedicados como models, services e extensions.
"""
from app import _export_route_globals

globals().update(_export_route_globals())

@app.route("/api/audit-log")
@requires("Administrador","Técnico TI")
def get_audit_log():
    page = int(request.args.get("page",1))
    per  = int(request.args.get("per",50))
    total = db.session.execute(db.select(func.count()).select_from(AuditLog)).scalar()
    logs = db.session.execute(db.select(AuditLog).order_by(AuditLog.data.desc()).offset((page-1)*per).limit(per)).scalars().all()
    return jsonify({"total":total,"page":page,"items":[l.to_dict() for l in logs]})


@app.route("/api/alerts")
@api_auth
def get_alerts(): return jsonify(compute_alerts())


@app.route("/api/dashboard")
@api_auth
def get_dashboard():
    cats = dict(db.session.execute(
        db.select(Asset.categoria, func.count(Asset.id)).group_by(Asset.categoria)
    ).all())

    # Devoluções pendentes de ação (laudo ou RH)
    devs_pendentes = db.session.execute(
        db.select(Devolucao)
        .where(Devolucao.laudo_status.in_(["Aguardando Laudo", "Aguardando RH"]))
        .order_by(Devolucao.data_devolucao.desc())
        .limit(10)
    ).scalars().all()

    return jsonify({
        "totais": {
            "ativos":      db.session.execute(db.select(func.count()).select_from(Asset)).scalar(),
            "alocados":    db.session.execute(db.select(func.count()).select_from(Asset).filter_by(status="Alocado")).scalar(),
            "disponiveis": db.session.execute(db.select(func.count()).select_from(Asset).filter_by(status="Disponível")).scalar(),
            "manutencao":  db.session.execute(db.select(func.count()).select_from(Asset).filter_by(status="Manutenção")).scalar(),
        },
        "colaboradores": {
            "ativos":   db.session.execute(db.select(func.count()).select_from(Colaborador).filter_by(status="Ativo")).scalar(),
            "inativos": db.session.execute(db.select(func.count()).select_from(Colaborador).filter_by(status="Inativo")).scalar(),
        },
        "devolucoes": {
            "aguardandoLaudo": db.session.execute(
                db.select(func.count()).select_from(Devolucao)
                .where(Devolucao.laudo_status.in_(["Aguardando Laudo", None]))
            ).scalar(),
            "aguardandoRH": db.session.execute(
                db.select(func.count()).select_from(Devolucao).filter_by(laudo_status="Aguardando RH")
            ).scalar(),
            "pendentes": [d.to_dict() for d in devs_pendentes],
        },
        "categorias": cats,
        "alertas": compute_alerts(),
        "ultimasAlocacoes": [a.to_dict() for a in
                             db.session.execute(db.select(Allocation).order_by(Allocation.data_aloc.desc()).limit(6)).scalars().all()],
        "licencas": {
            "total":      db.session.query(func.sum(License.total)).scalar() or 0,
            "atribuidas": db.session.query(func.sum(License.atribuidas)).scalar() or 0,
            "custoMensal": round(sum(l.custo_mensal for l in db.session.execute(db.select(License)).scalars().all()), 2),
            "custoAnual": round(sum(l.custo_anual for l in db.session.execute(db.select(License)).scalars().all()), 2),
        },
    })


@app.route("/api/sre/status")
@api_auth
def sre_status():
    """Resumo operacional para análise de confiabilidade e gestão de SLO."""
    db_health = _database_health()
    total_requests = None
    if METRICS_OK:
        try:
            total_requests = sum(sample.value for sample in HTTP_REQUESTS_TOTAL.collect()[0].samples if sample.name.endswith("_total"))
        except Exception:
            total_requests = None
    open_incidents = db.session.execute(
        db.select(func.count()).select_from(Incident).where(Incident.status != "Resolvido")
    ).scalar()
    pending_terms = db.session.execute(
        db.select(func.count()).select_from(Allocation).filter_by(termo_status="Pendente")
    ).scalar()
    low_stock = db.session.execute(
        db.select(func.count()).select_from(Supply).where(Supply.estoque <= Supply.minimo)
    ).scalar()
    return jsonify({
        **_service_metadata(),
        "health": {"database": db_health},
        "sloTargets": {
            "availability": "99.5% mensal",
            "latencyP95": "<= 500ms para rotas principais",
            "errorRate": "< 1% de respostas 5xx",
            "backup": "1 backup lógico diário"
        },
        "businessIndicators": {
            "incidentsOpen": open_incidents,
            "termsPendingSignature": pending_terms,
            "suppliesAtOrBelowMinimum": low_stock,
            "activeAlerts": len(compute_alerts())
        },
        "observability": {
            "metricsEnabled": METRICS_OK,
            "requestsObserved": total_requests
        }
    })


@app.route("/api/movements")
@api_auth
def get_movements():
    movs = db.session.execute(db.select(SupplyMovement).order_by(SupplyMovement.data.desc()).limit(50)).scalars().all()
    return jsonify([m.to_dict() for m in movs])


@app.route("/api/export/assets.csv")
@requires("Administrador","Técnico TI","Gestor")
def export_assets_csv():
    rows = [a.to_dict() for a in db.session.execute(db.select(Asset).order_by(Asset.hostname)).scalars().all()]
    headers = ["id","hostname","ip","mac","serviceTag","os","fabricante","modelo","patrimonio","nf","categoria","status","colaborador","setor","unidade","garantia"]
    audit("EXPORTAR", "ativos", "", "Exportação CSV de ativos")
    db.session.commit()
    return csv_response("ativos_ti.csv", rows, headers)


@app.route("/api/export/colaboradores.csv")
@requires("Administrador","Técnico TI","Gestor")
def export_colaboradores_csv():
    rows = [c.to_dict() for c in db.session.execute(db.select(Colaborador).order_by(Colaborador.nome)).scalars().all()]
    headers = ["id","nome","email","telefone","cargo","setor","unidade","status","matricula","dataAdmissao","dataCadastro","dataDesligamento","observacao"]
    audit("EXPORTAR", "colaboradores", "", "Exportação CSV de colaboradores")
    db.session.commit()
    return csv_response("colaboradores_ti.csv", rows, headers)


@app.route("/api/export/alocacoes.csv")
@requires("Administrador","Técnico TI","Gestor")
def export_alocacoes_csv():
    rows = [a.to_dict(include_items=False) for a in db.session.execute(db.select(Allocation).order_by(Allocation.data_aloc.desc())).scalars().all()]
    headers = ["id","ativo","ativoNome","colaborador","setor","unidade","email","dataAloc","motivo","dataEncerramento","status","termo","termoStatus","dataAssinatura"]
    audit("EXPORTAR", "alocacoes", "", "Exportação CSV de alocações")
    db.session.commit()
    return csv_response("alocacoes_ti.csv", rows, headers)


@app.route("/api/backup.json")
@requires("Administrador")
def backup_json():
    raw, checksum = _backup_bytes(generated_by=current_user.username, include_audit=_get_backup_config()["include_audit"])
    audit("BACKUP", "sistema", "", "Backup JSON baixado")
    db.session.commit()
    data = io.BytesIO(raw)
    resp = send_file(data, mimetype="application/json", as_attachment=True,
                     download_name=f"backup_ticontrol_{date.today()}.json")
    resp.headers["X-Content-SHA256"] = checksum
    return resp


@app.route("/api/backups")
@requires("Administrador")
def list_backups():
    return jsonify({"config": _get_backup_config(), "files": _list_backup_files()})


@app.route("/api/backups/run", methods=["POST"])
@requires("Administrador")
def run_backup():
    try:
        result = _write_backup_file("manual", generated_by=current_user.username)
        audit("BACKUP", "sistema", "", f"Backup armazenado: {result['filename']}")
        db.session.commit()
        return jsonify(result), 201
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": f"Falha ao gerar backup: {exc}"}), 500


@app.route("/api/backups/files/<filename>")
@requires("Administrador")
def download_backup_file(filename):
    path = _backup_file_path(filename)
    if not path or not os.path.exists(path):
        return jsonify({"error": "Backup não encontrado."}), 404
    audit("BACKUP_DOWNLOAD", "sistema", filename, "Backup salvo baixado")
    db.session.commit()
    return send_file(path, mimetype="application/json", as_attachment=True, download_name=os.path.basename(path))


@app.route("/api/backups/files/<filename>", methods=["DELETE"])
@requires("Administrador")
def delete_backup_file(filename):
    path = _backup_file_path(filename)
    if not path or not os.path.exists(path):
        return jsonify({"error": "Backup não encontrado."}), 404
    os.remove(path)
    audit("BACKUP_DELETE", "sistema", filename, "Backup salvo removido")
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/backups/validate", methods=["POST"])
@requires("Administrador")
def validate_backup():
    sha256_actual = None
    if request.files.get("file"):
        data = request.files["file"].read()
        if len(data) > BACKUP_UPLOAD_MAX_BYTES:
            return jsonify({"error": "Arquivo excede 20 MB."}), 400
    else:
        d = json_payload() or {}
        filename = clean_text(d.get("filename"), 200)
        if not filename:
            return jsonify({"error": "Parâmetro 'filename' ou upload obrigatório."}), 400
        path = _backup_file_path(filename)
        if not path or not os.path.exists(path):
            return jsonify({"error": "Backup não encontrado."}), 404
        with open(path, "rb") as fh:
            data = fh.read()
    sha256_actual = hashlib.sha256(data).hexdigest()
    try:
        payload = json.loads(data.decode("utf-8"))
    except Exception:
        return jsonify({"error": "Arquivo não é um JSON válido.", "valid": False}), 400
    result = _validate_backup_payload(payload)
    result["sha256"] = sha256_actual
    return jsonify(result)


@app.route("/api/backups/restore/<filename>", methods=["POST"])
@requires("Administrador")
def restore_backup_stored(filename):
    path = _backup_file_path(filename)
    if not path or not os.path.exists(path):
        return jsonify({"error": "Backup não encontrado."}), 404
    with open(path, "rb") as fh:
        data = fh.read()
    try:
        payload = json.loads(data.decode("utf-8"))
    except Exception:
        return jsonify({"error": "Arquivo corrompido — JSON inválido."}), 400
    validation = _validate_backup_payload(payload)
    if not validation["valid"]:
        return jsonify({"error": "Backup inválido.", "details": validation["errors"]}), 422
    try:
        stats = _restore_from_payload(payload, restored_by=current_user.username)
        audit("RESTORE", "sistema", filename, f"Banco restaurado de {filename}")
        db.session.commit()
        return jsonify({"ok": True, "stats": stats, "source": filename})
    except Exception as exc:
        db.session.rollback()
        logger.exception("Falha na restauração de backup")
        return jsonify({"error": f"Falha na restauração: {exc}"}), 500


@app.route("/api/backups/restore", methods=["POST"])
@requires("Administrador")
def restore_backup_upload():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "Arquivo obrigatório."}), 400
    data = file.read()
    if not data:
        return jsonify({"error": "Arquivo vazio."}), 400
    if len(data) > BACKUP_UPLOAD_MAX_BYTES:
        return jsonify({"error": "Arquivo excede 20 MB."}), 400
    try:
        payload = json.loads(data.decode("utf-8"))
    except Exception:
        return jsonify({"error": "Arquivo não é um JSON válido."}), 400
    validation = _validate_backup_payload(payload)
    if not validation["valid"]:
        return jsonify({"error": "Backup inválido.", "details": validation["errors"]}), 422
    try:
        stats = _restore_from_payload(payload, restored_by=current_user.username)
        audit("RESTORE", "sistema", file.filename or "upload", f"Banco restaurado via upload")
        db.session.commit()
        return jsonify({"ok": True, "stats": stats, "source": file.filename or "upload"})
    except Exception as exc:
        db.session.rollback()
        logger.exception("Falha na restauração de backup via upload")
        return jsonify({"error": f"Falha na restauração: {exc}"}), 500

