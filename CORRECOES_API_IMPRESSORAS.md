# Correções Recomendadas para API de Impressoras

## Implementação das Correções

### 1. Corrigir a Função `_agent_printer_from_request()`

**Arquivo:** `routes/print_jobs.py` (linhas 18-27)

**Problema:** Extração frágil do token Bearer, sem proteção adicional

**Solução:**

```python
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
```

### 2. Melhorar Logs da API

**Arquivo:** `routes/print_jobs.py` (linhas 300-325)

**Adicionar após as validações:**

```python
import logging

logger = logging.getLogger(__name__)

@app.route("/api/print-jobs/next", methods=["GET"])
def next_print_job():
    printer_id = clean_text(request.args.get("printer_id") or request.args.get("printerId"), 60)
    printer = _agent_printer_from_request(printer_id)
    
    if not printer:
        # Log detalhado do erro
        auth = request.headers.get("Authorization", "")
        has_auth = bool(auth)
        logger.warning(f"Acesso não autorizado a print jobs: printer_id={printer_id}, has_auth={has_auth}, ip={request.remote_addr}")
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
    logger.info(f"Job {job.id} enviado para impressora {printer_id}")
    return jsonify(job.to_dict(include_zpl=True))


@app.route("/api/print-jobs/<int:job_id>/status", methods=["POST"])
def update_print_job_status(job_id):
    job = db.get_or_404(PrintJob, job_id)
    printer = _agent_printer_from_request(job.printer_id)
    
    if not printer:
        logger.warning(f"Atualização de status não autorizada: job_id={job_id}, printer_id={job.printer_id}")
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
    
    log_level = logging.INFO if status == "printed" else logging.WARNING
    logger.log(log_level, f"Job {job_id}: {old_status} → {status}, mensagem={job.message[:50]}")
    
    return jsonify(job.to_dict())
```

### 3. Melhorar Agente Local

**Arquivo:** `tools/l42pro_print_agent.py` (linhas 91-107)

**Melhorar tratamento de erros:**

```python
def main() -> int:
    if not TOKEN:
        print("TICONTROL_AGENT_TOKEN não definido.", file=sys.stderr)
        return 2
    
    if not API_URL or "://" not in API_URL:
        print(f"TICONTROL_API_URL inválida: {API_URL}", file=sys.stderr)
        return 2
    
    print(f"TI Control Print Agent: {PRINTER_ID} -> {WINDOWS_PRINTER}")
    print(f"  API: {API_URL}")
    print(f"  Status: Iniciado")
    
    consecutive_errors = 0
    max_consecutive_errors = 10
    
    while True:
        try:
            # Busca próximo job
            job = request_json("GET", f"/api/print-jobs/next?printer_id={PRINTER_ID}")
            
            consecutive_errors = 0  # Reset contador de erros
            
            if not job or job.get("job") is None:
                time.sleep(POLL_SECONDS)
                continue
            
            job_id = job["id"]
            
            try:
                # Imprime
                send_raw_to_windows_printer(job["zpl"])
                
                # Relata sucesso
                request_json("POST", f"/api/print-jobs/{job_id}/status", {
                    "status": "printed",
                    "message": "Etiqueta impressa com sucesso"
                })
                print(f"✓ Job {job_id} impresso com sucesso")
                
            except Exception as exc:
                # Relata erro de impressão
                try:
                    request_json("POST", f"/api/print-jobs/{job_id}/status", {
                        "status": "error",
                        "message": f"Erro de impressão: {str(exc)[:500]}"
                    })
                except Exception:
                    pass  # Já reportado no stderr
                
                print(f"✗ Job {job_id} falhou: {exc}", file=sys.stderr)
                consecutive_errors += 1
        
        except urllib.error.HTTPError as exc:
            response_body = exc.read().decode('utf-8', 'ignore')
            consecutive_errors += 1
            
            if exc.code == 401:
                print(f"✗ ERRO 401 - Autenticação falhou", file=sys.stderr)
                print(f"   Verifique: TICONTROL_AGENT_TOKEN, TICONTROL_PRINTER_ID, TICONTROL_API_URL", file=sys.stderr)
                print(f"   Resposta: {response_body[:200]}", file=sys.stderr)
            elif exc.code == 404:
                print(f"✗ ERRO 404 - Printer não encontrado: {response_body[:200]}", file=sys.stderr)
            elif exc.code == 500:
                print(f"✗ ERRO 500 - Erro interno do servidor", file=sys.stderr)
            else:
                print(f"✗ HTTP {exc.code}: {response_body[:200]}", file=sys.stderr)
            
            # Pausa progressiva após múltiplos erros
            if consecutive_errors >= max_consecutive_errors:
                print(f"✗ {consecutive_errors} erros consecutivos. Aguardando 30s antes de novo ciclo.", file=sys.stderr)
                time.sleep(30)
            else:
                time.sleep(POLL_SECONDS)
        
        except urllib.error.URLError as exc:
            consecutive_errors += 1
            print(f"✗ Erro de conexão: {exc.reason}", file=sys.stderr)
            time.sleep(min(POLL_SECONDS * consecutive_errors, 60))  # Backoff
        
        except Exception as exc:
            consecutive_errors += 1
            print(f"✗ Erro no agente: {exc}", file=sys.stderr)
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
```

### 4. Adicionar Endpoint de Teste/Diagnóstico

**Arquivo:** `routes/print_jobs.py` (novo endpoint)

```python
@app.route("/api/print-printers/<printer_id>/test", methods=["POST"])
@requires("Administrador", "Técnico TI")
def test_printer_auth(printer_id):
    """
    Endpoint para testar a autenticação de uma impressora.
    Útil para troubleshooting.
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
    
    return jsonify({
        "printer_id": printer.id,
        "printer_name": printer.name,
        "printer_status": printer.status,
        "printer_last_seen": printer.last_seen.isoformat() if printer.last_seen else None,
        "auth_ok": auth_ok,
        "token_provided": bool(test_token),
        "token_hash_match": auth_ok,
        "message": "Autenticação bem-sucedida" if auth_ok else "Token incorreto - não corresponde ao registrado no sistema"
    }), 200
```

## Checklist de Implementação

- [ ] Atualizar `_agent_printer_from_request()` em `routes/print_jobs.py`
- [ ] Adicionar logging em `/api/print-jobs/next` e `/api/print-jobs/{id}/status`
- [ ] Melhorar tratamento de erros em `tools/l42pro_print_agent.py`
- [ ] Adicionar endpoint de teste `/api/print-printers/{id}/test`
- [ ] Adicionar método de logging para impressoras em `app.py`
- [ ] Atualizar documentação do agente com instruções de troubleshooting
- [ ] Criar testes unitários para novos casos de falha
- [ ] Testar com token contendo caracteres especiais
- [ ] Testar com URL da API incorreta
- [ ] Testar com printer_id incorreto

## Como Usar o Script de Diagnóstico

```bash
# Dentro da pasta do projeto
python test_print_api_diagnostic.py \
  --api-url http://localhost:5000 \
  --printer-id L42PRO-ALMOXARIFADO \
  --token "COLE_O_TOKEN_AQUI"
```

Exemplo de saída esperada:
```
ℹ️   Teste de Conectividade da API
✓ API acessível em http://localhost:5000 (HTTP 200)

ℹ️   Teste de Formato do Token Bearer
✓ Token extraído corretamente: 'abc123def456ghi...'

ℹ️   Teste de Consistência do clean_text()
✓ Token não foi modificado por clean_text()

ℹ️   Teste de Existência da Impressora
✓ Impressora 'L42PRO-ALMOXARIFADO' encontrada
  Status: Online
  Tipo: USB/ZPL
  Última visto: 2026-06-25T10:30:45

ℹ️   Teste de Busca do Próximo Job
✓ Autenticação bem-sucedida, mas nenhum job na fila

ℹ️   Teste de Token com Espaços Extras
✓ Token com espaços foi aceito
```

