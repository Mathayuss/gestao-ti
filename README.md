# TI Control SRE — Gestão de Ativos de TI com práticas de confiabilidade

Sistema Flask para gestão de ativos, colaboradores, insumos/periféricos, alocações, termos, QR Code e auditoria, agora evoluído com uma camada prática de SRE: health checks, métricas Prometheus, execução com Gunicorn, Docker Compose, smoke test, SLO e runbooks.

## Como executar em desenvolvimento

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate  # Windows
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Acesse: `http://localhost:5000`

Usuários iniciais, quando `SHOW_DEMO_CREDENTIALS=1`:

- Administrador: `admin.ti` / `admin123`
- Técnico: `marcos.souza` / `tecnico123`
- Gestor: `roberto.faria` / `gestor123`
- Visualizador: `viewer` / `viewer123`

## Como executar com Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

Serviços:

- Aplicação: `http://localhost:5000`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`

Credencial padrão do Grafana local: `admin` / `admin`.

## Endpoints SRE

| Endpoint | Finalidade |
|---|---|
| `/health/live` | Liveness check |
| `/health/startup` | Startup check |
| `/health/ready` | Readiness check com teste de banco |
| `/metrics` | Métricas Prometheus |
| `/api/sre/status` | Indicadores operacionais autenticados |
| `/ping` | Health simples público |

## Smoke test

Com a aplicação rodando:

```bash
./scripts/smoke-test.sh
```

Ou usando outra URL:

```bash
BASE_URL=http://servidor:5000 ./scripts/smoke-test.sh
```

## Configurações importantes

- `SECRET_KEY`: altere obrigatoriamente em produção.
- `DATABASE_URL`: por padrão usa SQLite em `instance/ticontrol.db`.
- `APP_BASE_URL`: URL usada nos QR Codes e links públicos.
- `SESSION_SECURE=1`: use quando estiver em HTTPS.
- `SHOW_DEMO_CREDENTIALS=0`: oculta usuários/senhas de exemplo na tela de login.
- `SERVICE_NAME`: nome do serviço exposto nas métricas.
- `BUILD_VERSION`: versão/build exibida em health checks e métricas.
- `ENVIRONMENT`: ambiente, por exemplo `development`, `homolog`, `production`.
- SMTP: pode ser configurado e ativado pela própria aplicação em `Configurações > E-mail`; variáveis `SMTP_*` são opcionais para quem preferir administrar pelo servidor.

## Rotas úteis do sistema

- `/api/backup.json`: backup JSON dos principais cadastros e movimentos.
- `/api/export/assets.csv`: exportação CSV dos ativos.
- `/api/export/colaboradores.csv`: exportação CSV dos colaboradores.
- `/api/export/alocacoes.csv`: exportação CSV das alocações.
- `/asset/<id>`: perfil público do ativo via QR Code.

## Documentação SRE

- `docs/sre/SLO.md`
- `docs/sre/RUNBOOK.md`
- `docs/sre/INCIDENT_RESPONSE.md`
- `docs/sre/OBSERVABILITY.md`

## Observações de produção

Antes de publicar em rede corporativa:

1. Troque `SECRET_KEY`.
2. Use `FLASK_DEBUG=0`.
3. Configure `APP_BASE_URL` com o endereço real do sistema.
4. Use HTTPS e `SESSION_SECURE=1`.
5. Altere as senhas dos usuários iniciais.
6. Proteja `/metrics` na borda, permitindo acesso apenas ao Prometheus/rede interna.
7. Avalie migração para PostgreSQL se houver uso multiusuário intenso.
8. Automatize backup diário e teste de restauração.
