# Guia de Troubleshooting - API de Impressoras

## 📋 Resumo Executivo

Foram identificados **5 problemas potenciais** na comunicação entre o agente de impressoras e a API do TI Control, além de implementadas **3 correções críticas** no código.

### ✓ Correções Implementadas

1. ✅ **Melhorada a função `_agent_printer_from_request()`**
   - Extração de token Bearer mais robusta
   - Melhor tratamento de erros
   - Commit seguro com rollback em caso de falha

2. ✅ **Adicionado logging detalhado**
   - Logs com prefixo `[PRINTER]` para fácil filtro
   - Diferenciação entre erros de autenticação e outras falhas
   - Registro de IP do cliente para análise de segurança

3. ✅ **Novo endpoint de diagnóstico**
   - `POST /api/print-printers/<printer_id>/test`
   - Permite testar autenticação sem iniciar o agente
   - Retorna informações detalhadas de status

## 🔍 Problemas Identificados

### 1️⃣ Extração Frágil de Token Bearer
**Severidade:** 🔴 ALTA

O código original usava:
```python
token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
```

**Problema:** Assumia sempre 7 caracteres para "Bearer "

**Fixado:** Agora usa split() mais robusto:
```python
parts = auth.split(None, 1)
if len(parts) == 2 and parts[0].lower() == "bearer":
    token = parts[1]
```

---

### 2️⃣ Endpoints Sem Proteção de Autenticação da API
**Severidade:** 🔴 ALTA

Endpoints:
- `GET /api/print-jobs/next`
- `POST /api/print-jobs/<id>/status`

**Problema:** Não têm decorador `@api_auth`, dependem APENAS de `_agent_printer_from_request()`

**Fixado:** Adicionados logs de segurança e melhorado validação

---

### 3️⃣ Falta de Logging Estruturado
**Severidade:** 🟠 MÉDIA

**Problema:** Sem diferenciação entre erros de autenticação e servidor

**Fixado:** Adicionado logger estruturado com contexto (printer_id, job_id, IP)

---

### 4️⃣ Agente Sem Diferenciação de Erro
**Severidade:** 🟠 MÉDIA

**Problema:** Agente trata erro 401 (auth) igual a erro 503 (server)

**Recomendação:** Usar o novo script de diagnóstico

---

### 5️⃣ Falta de Validação de Token na Criação
**Severidade:** 🟡 BAIXA

**Recomendação:** Usar `clean_text()` de forma consistente

---

## 🚀 Como Usar

### 1. Criar uma Nova Impressora

```bash
# Via curl
curl -X POST http://localhost:5000/api/print-printers \
  -H "Authorization: Bearer seu_token_de_admin" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "L42PRO-ALMOXARIFADO",
    "name": "Impressora Almoxarifado",
    "location": "Almoxarifado",
    "windowsName": "ELGIN L42Pro",
    "type": "USB/ZPL"
  }'

# Resposta (guarde o token!):
{
  "id": "L42PRO-ALMOXARIFADO",
  "name": "Impressora Almoxarifado",
  "status": "Offline",
  "token": "RgL8K_q1e2X-9v7m3nT0p4q5r6s7t8u9v"  ← TOKEN DO AGENTE
}
```

---

### 2. Testar Autenticação com Novo Endpoint

```bash
# Teste de autenticação (novo endpoint)
curl -X POST http://localhost:5000/api/print-printers/L42PRO-ALMOXARIFADO/test \
  -H "Authorization: Bearer seu_token_de_admin" \
  -H "Content-Type: application/json" \
  -d '{
    "token": "RgL8K_q1e2X-9v7m3nT0p4q5r6s7t8u9v"
  }'

# Resposta:
{
  "printer_id": "L42PRO-ALMOXARIFADO",
  "printer_name": "Impressora Almoxarifado",
  "printer_status": "Offline",
  "printer_last_seen": null,
  "auth_ok": true,
  "token_provided": true,
  "token_hash_match": true,
  "message": "Autenticação bem-sucedida"
}
```

---

### 3. Usar Script de Diagnóstico Completo

```bash
cd /home/gestao-ti-v2-melhorado

# Teste com token válido
python test_print_api_diagnostic.py \
  --api-url http://localhost:5000 \
  --printer-id L42PRO-ALMOXARIFADO \
  --token "RgL8K_q1e2X-9v7m3nT0p4q5r6s7t8u9v"

# Exemplo de saída:
# ✓ Conectividade da API
# ✓ Extração de Token Bearer
# ✓ Consistência clean_text()
# ✓ Existência da Impressora
# ✓ Busca do Próximo Job
# ✓ Token com Espaços
# Resultado: 6/6 testes passaram
```

---

### 4. Configurar Agente Local

```bash
# 1. Baixar pacote do agente
curl -X GET "http://localhost:5000/api/print-agent/download?printer_id=L42PRO-ALMOXARIFADO&windows_printer=ELGIN%20L42Pro" \
  -H "Authorization: Bearer seu_token_de_admin" \
  -o ti-control-print-agent.zip

# 2. Extrair
unzip ti-control-print-agent.zip

# 3. Configurar arquivo agent.env
cp agent.env.example agent.env
# Editar agent.env e colar o token gerado

# 4. Instalar dependências
pip install -r requirements.txt

# 5. Testar
python l42pro_print_agent.py

# 6. Para produção, registrar como serviço Windows com NSSM
nssm install EtiquetaPrintAgent C:\caminho\run-agent.bat
```

---

## 🔧 Checklist de Troubleshooting

Se a impressora não está se comunicando com a API:

- [ ] **Verificar URL da API**
  ```bash
  # Teste se a API está acessível
  curl -v http://localhost:5000/
  ```

- [ ] **Verificar Token**
  ```bash
  # Execute o teste de autenticação
  python test_print_api_diagnostic.py --token "seu_token"
  ```

- [ ] **Verificar Printer ID**
  ```bash
  # Listar todas as impressoras registradas
  curl -H "Authorization: Bearer seu_token" \
       http://localhost:5000/api/print-printers
  ```

- [ ] **Verificar Logs do Servidor**
  ```bash
  # Procurar por logs com [PRINTER]
  tail -f /var/log/ticontrol.log | grep PRINTER
  ```

- [ ] **Verificar Logs do Agente**
  ```bash
  # Agente imprime no stdout/stderr
  # Procurar por linhas com ✓ (sucesso) ou ✗ (erro)
  ```

- [ ] **Testar Fila de Jobs**
  ```bash
  curl -H "Authorization: Bearer seu_token_de_admin" \
       http://localhost:5000/api/print-jobs?status=pending
  ```

---

## 📊 Cenários de Erro Comuns

### ❌ Erro: HTTP 401 - Agente não autorizado

**Causas possíveis:**
1. Token incorreto ou expirado
2. Printer ID não corresponde ao registrado
3. Token tem espaços extras (copy-paste)

**Solução:**
```bash
# Use o endpoint de teste
python test_print_api_diagnostic.py \
  --printer-id "seu_printer_id" \
  --token "seu_token"
```

---

### ❌ Erro: HTTP 404 - Printer não encontrado

**Causas possíveis:**
1. Impressora não está registrada no sistema
2. Printer ID tem espaço extra ou case diferente

**Solução:**
```bash
# Listar impressoras disponíveis
curl -H "Authorization: Bearer seu_token" \
     http://localhost:5000/api/print-printers
```

---

### ❌ Erro: Connection Refused / Timeout

**Causas possíveis:**
1. API não está rodando
2. URL incorreta (host ou porta)
3. Firewall bloqueando conexão

**Solução:**
```bash
# Testar conectividade
curl -v http://seu_api_url:5000/

# Ou usar diagnóstico
python test_print_api_diagnostic.py --api-url "http://seu_api_url:5000"
```

---

### ❌ Agente Rodando mas Sem Imprimir

**Causas possíveis:**
1. Nenhum job na fila
2. Impressora não conectada no Windows
3. Erro ao enviar ZPL

**Solução:**
```bash
# Verificar jobs na fila
curl -H "Authorization: Bearer seu_token_de_admin" \
     http://localhost:5000/api/print-jobs?status=pending

# Verificar status da impressora (deve estar Online)
curl -H "Authorization: Bearer seu_token_de_admin" \
     http://localhost:5000/api/print-printers
```

---

## 📈 Monitoramento em Produção

### Logs a Monitorar

```bash
# Erros de autenticação
grep "\[PRINTER\] Acesso não autorizado" /var/log/ticontrol.log

# Erros de impressão
grep "\[PRINTER\].*ERROR\|ERROR" /var/log/ticontrol.log

# Status do agente
grep "\[PRINTER\] Job" /var/log/ticontrol.log
```

### Alertas Recomendados

1. **Impressora Offline por mais de 5 minutos**
   ```sql
   SELECT * FROM print_printers 
   WHERE status = 'Offline' 
   AND last_seen < NOW() - INTERVAL 5 MINUTE
   ```

2. **Jobs em Processamento Sem Finalizar**
   ```sql
   SELECT * FROM print_jobs 
   WHERE status = 'processing' 
   AND picked_at < NOW() - INTERVAL 30 MINUTE
   ```

3. **Taxa Alta de Erros de Impressão**
   ```sql
   SELECT printer_id, COUNT(*) as error_count 
   FROM print_jobs 
   WHERE status = 'error' 
   AND created_at > NOW() - INTERVAL 1 HOUR
   GROUP BY printer_id
   HAVING error_count > 10
   ```

---

## 📚 Documentação de Referência

- Arquivo de diagnóstico completo: [DIAGNOSTICO_API_IMPRESSORAS.md](DIAGNOSTICO_API_IMPRESSORAS.md)
- Recomendações de correção: [CORRECOES_API_IMPRESSORAS.md](CORRECOES_API_IMPRESSORAS.md)
- Script de teste: [test_print_api_diagnostic.py](test_print_api_diagnostic.py)
- Testes unitários: [tests/test_print_jobs.py](tests/test_print_jobs.py)

---

## 📞 Suporte

Para problemas não resolvidos:

1. Executar o script de diagnóstico completo
2. Coletar logs do servidor com `grep PRINTER`
3. Verificar status da impressora no dashboard do TI Control
4. Criar ticket com saída do diagnóstico anexada

