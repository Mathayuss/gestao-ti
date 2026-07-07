# Diagnóstico: Problemas na Comunicação com API da Impressora

## Problemas Identificados

### 1. **PROBLEMA CRÍTICO: Processamento de Token Inconsistente**

**Localização:** `routes/print_jobs.py`, linhas 14-22

**Código problemático:**
```python
def _printer_token_hash(token):
    return hashlib.sha256(clean_text(token).encode("utf-8")).hexdigest()

def _agent_printer_from_request(printer_id):
    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    printer = db.session.get(PrintPrinter, clean_text(printer_id, 60))
    if not printer or not token or printer.token_hash != _printer_token_hash(token):
        return None
```

**Problema:**
- O token é gerado com `secrets.token_urlsafe(32)` (URL-safe base64)
- Ao criar a impressora, o hash é guardado como: `_printer_token_hash(token)` → `hashlib.sha256(clean_text(token)...)`
- `clean_text()` aplica `.strip()` e truncamento
- Na autenticação, o token é comparado novamente através de `_printer_token_hash(token)`

**Risco:**
Se o token contiver caracteres que `clean_text()` modifique (como espaços nas extremidades), o hash não corresponderá.

---

### 2. **PROBLEMA: Endpoints de Impressora Sem Proteção Adicional**

**Localização:** `routes/print_jobs.py`, linhas 300-320

```python
@app.route("/api/print-jobs/next", methods=["GET"])
def next_print_job():  # ❌ Sem @api_auth
    printer_id = clean_text(request.args.get("printer_id") or request.args.get("printerId"), 60)
    printer = _agent_printer_from_request(printer_id)
    if not printer:
        return jsonify({"error": "Agente não autorizado."}), 401

@app.route("/api/print-jobs/<int:job_id>/status", methods=["POST"])
def update_print_job_status(job_id):  # ❌ Sem @api_auth
    job = db.get_or_404(PrintJob, job_id)
    printer = _agent_printer_from_request(job.printer_id)
```

**Problema:**
- Estes endpoints não têm decorador `@api_auth` ou `@requires()`
- Dependem APENAS da validação em `_agent_printer_from_request()`
- Se essa função tiver um bug (ex: comparação de token incorreta), qualquer pessoa pode acessar

---

### 3. **POSSÍVEL PROBLEMA: Extração Incorreta do Token Bearer**

**Localização:** `routes/print_jobs.py`, linha 20

```python
token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
```

**Análise:**
- Se header for `Authorization: Bearer TOKEN`, extração funciona
- Se header for `Authorization:Bearer TOKEN` (sem espaço após `:`) ou outro formato, falha
- Se houver espaços extras: `Authorization: Bearer  TOKEN` (dois espaços), o token terá espaço extra

**Melhor prática:**
```python
# Usar regex ou split mais robusto
parts = auth.split() if auth else []
token = parts[1] if len(parts) == 2 and parts[0].lower() == 'bearer' else ""
```

---

### 4. **PROBLEMA: Falta de Validação de URL Base**

**Localização:** `tools/l42pro_print_agent.py`, linha 38

```python
API_URL = os.environ.get("TICONTROL_API_URL", "http://127.0.0.1:5000").rstrip("/")
```

**Problemas:**
- Se a URL estiver errada, o agente continua tentando
- Nenhuma validação de SSL/TLS
- Timeout é fixo em 20 segundos

---

### 5. **PROBLEMA: Sem Retry Inteligente no Agente**

**Localização:** `tools/l42pro_print_agent.py`, linhas 91-107

```python
try:
    job = request_json("GET", f"/api/print-jobs/next?printer_id={PRINTER_ID}")
    if not job or job.get("job") is None:
        time.sleep(POLL_SECONDS)
        continue
except urllib.error.HTTPError as exc:
    print(f"HTTP {exc.code}: {exc.read().decode('utf-8', 'ignore')}", file=sys.stderr)
    time.sleep(POLL_SECONDS)
```

**Problema:**
- Erro 401 (Unauthorized) é tratado igual a erro 503 (Service Unavailable)
- Não há diferenciação entre erro temporário e erro de configuração
- Agente continuará tentando indefinidamente se o token estiver errado

---

## Cenários de Falha Provável

### ❌ Cenário 1: Token com Caracteres Especiais
```
1. Admin cria impressora, token gerado: "abc-def_123+456=="
2. clean_text() no hash: "abc-def_123+456==" (OK, sem alteração)
3. Agente envia: Authorization: Bearer abc-def_123+456==
4. clean_text() na comparação: "abc-def_123+456==" (OK, sem alteração)
✓ Funciona...

PORÉM, se houver espaço na extremidade durante copy-paste:
1. Token armazenado no agent.env: " abc-def_123+456== " (com espaços)
2. Agente envia: Authorization: Bearer  abc-def_123+456==  
3. Token extraído: "abc-def_123+456=="
4. clean_text() aplica .strip(): "abc-def_123+456==" 
✓ Ainda funciona...

MAS: Outro cenário...
```

### ❌ Cenário 2: Erro de Autenticação Silencioso
```
1. Impressora registrada como "L42PRO-ALMOXARIFADO"
2. Agente tenta com "L42PRO-ALMOXARIFADO " (com espaço)
3. clean_text() converte para "L42PRO-ALMOXARIFADO"
4. Printer encontrada, mas token_hash não bate
5. Retorna 401: "Agente não autorizado"
6. Agente não registra qual é o problema (token vs printer_id vs URL)
```

### ❌ Cenário 3: URL da API Incorreta
```
Agente configurado com: TICONTROL_API_URL=http://localhost:5000
Sistema rodando em: http://192.168.1.100:5000

Resultado: Timeout ou Connection Refused
Mensagem: "Erro no agente: urlopen error" (genérica, não ajuda a debugar)
```

---

## Testes Realizados

### ✓ Teste 1: Lifecycle Básico
```python
# tests/test_print_jobs.py - test_agent_print_job_lifecycle
# ✓ PASSA: Agente consegue buscar e imprimir quando token está correto
```

---

## Recomendações de Correção

### 1️⃣ **Melhorar Extração do Token** (Prioridade: ALTA)

```python
def _agent_printer_from_request(printer_id):
    auth = request.headers.get("Authorization", "").strip()
    token = ""
    
    # Extração mais robusta
    if auth.lower().startswith("bearer "):
        parts = auth.split(None, 1)  # Split em whitespace, máx 2 partes
        token = parts[1] if len(parts) == 2 else ""
    
    printer = db.session.get(PrintPrinter, clean_text(printer_id, 60))
    if not printer or not token:
        return None
    
    # Comparação segura: não modifique o token antes de hashear
    if printer.token_hash != _printer_token_hash(token):
        return None
    
    printer.status = "Online"
    printer.last_seen = datetime.now()
    db.session.commit()
    return printer
```

### 2️⃣ **Adicionar Logging Detalhado** (Prioridade: ALTA)

No agente (`tools/l42pro_print_agent.py`):
```python
except urllib.error.HTTPError as exc:
    response_body = exc.read().decode('utf-8', 'ignore')
    if exc.code == 401:
        print(f"❌ ERRO 401 - Autenticação falhou: {response_body}", file=sys.stderr)
        print(f"   Verificar: TICONTROL_AGENT_TOKEN, TICONTROL_PRINTER_ID, TICONTROL_API_URL", file=sys.stderr)
    elif exc.code == 404:
        print(f"❌ ERRO 404 - Impressora não encontrada: {response_body}", file=sys.stderr)
    else:
        print(f"❌ HTTP {exc.code}: {response_body}", file=sys.stderr)
    time.sleep(POLL_SECONDS)
```

### 3️⃣ **Validar Token na Criação** (Prioridade: MÉDIA)

```python
@app.route("/api/print-printers", methods=["POST"])
@requires("Administrador", "Técnico TI")
def create_print_printer():
    # ... código existente ...
    token = secrets.token_urlsafe(32)
    
    # Validar que clean_text não muda o token
    if clean_text(token) != token:
        # Isso causaria falha na autenticação!
        return jsonify({"error": "Token gerado tem caracteres inválidos após normalização"}), 500
    
    printer.token_hash = _printer_token_hash(token)
    # ... resto do código ...
```

### 4️⃣ **Adicionar Teste de Diagnóstico** (Prioridade: MÉDIA)

```python
@app.route("/api/print-printers/<printer_id>/test", methods=["POST"])
@requires("Administrador", "Técnico TI")
def test_printer_connection(printer_id):
    """Testa a conexão com um agente de impressora."""
    printer = db.session.get(PrintPrinter, clean_text(printer_id, 60))
    if not printer:
        return jsonify({"error": "Impressora não encontrada"}), 404
    
    d = json_payload()
    test_token = d.get("token")
    
    # Simula validação
    auth_ok = printer.token_hash == _printer_token_hash(test_token)
    
    return jsonify({
        "printer_id": printer.id,
        "status": printer.status,
        "auth_ok": auth_ok,
        "message": "Autenticação OK" if auth_ok else "Token incorreto ou não passou na validação"
    })
```

---

## Checklist de Troubleshooting

- [ ] Verificar se `TICONTROL_API_URL` está correto e acessível
- [ ] Verificar se `TICONTROL_PRINTER_ID` corresponde ao registrado no sistema
- [ ] Verificar se `TICONTROL_AGENT_TOKEN` não tem espaços extras (copy-paste)
- [ ] Verificar logs da API para erros 401, 404
- [ ] Testar endpoint `/api/print-jobs/next` manualmente com curl:
  ```bash
  curl -H "Authorization: Bearer YOUR_TOKEN" \
       "http://localhost:5000/api/print-jobs/next?printer_id=L42PRO-ALMOXARIFADO"
  ```
- [ ] Verificar se a impressora está com status "Online" (última vez visto)
- [ ] Verificar se há jobs com status "pending" ou "retry" na fila

---

## Endpoints da API de Impressoras

| Endpoint | Método | Auth | Descrição |
|----------|--------|------|-----------|
| `/api/print-printers` | GET | @api_auth | Lista todas as impressoras |
| `/api/print-printers` | POST | @requires | Cria nova impressora (retorna token) |
| `/api/print-agent/download` | GET | @requires | Baixa pacote do agente |
| `/api/print-jobs` | GET | @api_auth | Lista jobs (filtrar por status/printer) |
| `/api/print-jobs` | POST | @requires | Cria novo job de impressão |
| `/api/print-jobs/next` | GET | _agent_printer_from_request | ⚠️ Busca próximo job (agente local) |
| `/api/print-jobs/{id}/status` | POST | _agent_printer_from_request | ⚠️ Atualiza status do job (agente local) |

⚠️ Estes endpoints precisam de proteção adicional ou validação melhorada.

