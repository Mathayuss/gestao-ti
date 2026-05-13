# Runbook Operacional — TI Control SRE

## 1. Serviço indisponível

### Sintomas

- `/health/live` não responde.
- Container/app parado.
- Usuários não conseguem abrir o sistema.

### Diagnóstico

```bash
docker compose ps
docker compose logs -f app
curl -i http://localhost:5000/health/live
curl -i http://localhost:5000/health/ready
```

### Ação

```bash
docker compose restart app
```

Se persistir, verificar variáveis `.env`, banco em `instance/`, permissões de pasta e logs do Gunicorn.

---

## 2. Readiness degradado

### Sintomas

- `/health/live` retorna 200.
- `/health/ready` retorna 503.

### Causa provável

Falha de acesso ao banco SQLite ou erro de permissão na pasta `instance`.

### Diagnóstico

```bash
docker compose exec app ls -lah /app/instance
docker compose exec app python - <<'PY'
from app import app, db
from sqlalchemy import text
with app.app_context():
    print(db.session.execute(text('SELECT 1')).scalar())
PY
```

### Ação

- Corrigir permissão do volume.
- Restaurar backup JSON, se necessário.
- Reiniciar a aplicação.

---

## 3. Alta latência

### Sintomas

- p95 acima de 500 ms.
- Lentidão em dashboard, ativos ou alocações.

### Diagnóstico

```bash
curl -s http://localhost:5000/metrics | grep ticontrol_http_request_duration_seconds
```

Avaliar:

- volume de registros;
- consultas sem paginação;
- concorrência acima do esperado;
- SQLite com lock por múltiplas escritas.

### Ação

- Aumentar workers/threads do Gunicorn.
- Reduzir consultas sem limite.
- Migrar SQLite para PostgreSQL se houver uso simultâneo intenso.

---

## 4. Backup lógico

### Execução manual

```bash
curl -b cookies.txt http://localhost:5000/api/backup.json -o backup_ticontrol.json
```

Recomendado automatizar diariamente com usuário administrador técnico e armazenar fora do servidor da aplicação.
