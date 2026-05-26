# TI Control

Sistema web em Flask para gestão de ativos de TI, colaboradores, alocações, termos, QR Codes, insumos, licenças, manutenção, auditoria e rotinas operacionais. O projeto foi evoluído para um perfil mais próximo de produção, com PostgreSQL, Docker Compose, assistente inicial de configuração, backups pela aplicação, health checks e métricas Prometheus.

## Principais recursos

- Inventário de ativos com imagem, histórico, QR Code e perfil público para consulta.
- Gestão de colaboradores, alocações, devoluções, termos em PDF e assinatura digital.
- Controle de insumos, periféricos, kits de admissão, movimentações e estoque.
- Gestão de licenças, anexos, manutenções, incidentes e campanhas de auditoria.
- Configurações pela interface, incluindo aparência, SMTP, templates de e-mail, backup e perfis de acesso.
- Assistente web de primeira instalação em `/setup`.
- Execução com Docker Compose usando PostgreSQL incluso.
- Health checks, readiness check de banco, métricas Prometheus e endpoint operacional autenticado.

## Instalação recomendada

Para uma instalação nova, use os scripts do projeto. Eles criam o `.env`, configuram PostgreSQL, sobem os containers e exibem o link do assistente web.

### Linux

```bash
git clone https://github.com/Mathayuss/gestao-ti.git
cd gestao-ti
./scripts/install-linux.sh
```

Para validar pré-requisitos sem iniciar a instalação:

```bash
./scripts/install-linux.sh --check
```

### Windows

No PowerShell:

```powershell
git clone https://github.com/Mathayuss/gestao-ti.git
cd gestao-ti
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install-windows.ps1
```

Para validar pré-requisitos:

```powershell
.\scripts\install-windows.ps1 -Check
```

Mais detalhes estão em [INSTALL.md](INSTALL.md).

## Assistente de primeira configuração

Após subir a aplicação, acesse o link exibido pelo instalador:

```txt
http://localhost:5000/setup?token=SEU_TOKEN
```

O assistente permite configurar:

- conexão PostgreSQL usada pela aplicação;
- dados da empresa;
- usuário administrador inicial;
- URL pública do sistema;
- SMTP opcional;
- backup automático.

Depois que o primeiro administrador é criado, o assistente fica bloqueado.

## Execução com Docker Compose

Se preferir configurar manualmente:

```bash
cp .env.example .env
docker compose up --build
```

Serviços principais:

| Serviço | URL padrão |
|---|---|
| Aplicação | `http://localhost:5000` |
| PostgreSQL | `localhost:5432` |

Prometheus e Grafana ficam em um profile separado:

```bash
docker compose --profile observability up -d
```

| Serviço | URL padrão |
|---|---|
| Prometheus | `http://localhost:9090` |
| Grafana | `http://localhost:3000` |

Credencial padrão do Grafana local: `admin` / `admin`.

## Atualizações

Quando uma correção ou nova função for publicada no repositório público, instalações novas já ficam preparadas para atualização manual pela tela `Configurações > Atualizações`. O administrador clica em verificar/aplicar, o sistema gera backup lógico, executa `git pull --ff-only` e reinicia a aplicação automaticamente quando `SELF_UPDATE_AUTO_RESTART=1`.

Para instalações antigas ou ambientes sem metadados Git dentro do container, use os scripts abaixo uma vez para reconstruir a aplicação com suporte ao atualizador interno.

### Windows

```powershell
.\scripts\update-windows.ps1
```

Para validar pré-requisitos sem atualizar:

```powershell
.\scripts\update-windows.ps1 -Check
```

### Linux

```bash
./scripts/update-linux.sh
```

Para validar pré-requisitos sem atualizar:

```bash
./scripts/update-linux.sh --check
```

Se a nova versão foi copiada manualmente para o servidor e você não quer executar `git pull`, use `-NoPull` no Windows ou `--no-pull` no Linux. O atualizador recusa rodar quando há alterações locais não commitadas, para evitar sobrescrever customizações sem perceber.

## Desenvolvimento local

Para desenvolvimento sem Docker:

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate  # Windows
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Acesse `http://localhost:5000`.

O projeto suporta SQLite para desenvolvimento local quando `DATABASE_URL` não aponta para PostgreSQL, mas para homologação, beta e produção a recomendação é PostgreSQL.

Usuários de demonstração só devem ser exibidos em ambiente local quando `SHOW_DEMO_CREDENTIALS=1`. Em produção, mantenha `SHOW_DEMO_CREDENTIALS=0` e `AUTO_SEED_DEMO=0`.

## Configurações importantes

| Variável | Finalidade |
|---|---|
| `SECRET_KEY` | Chave da aplicação. Deve ser única e segura em produção. |
| `DATABASE_URL` | URL SQLAlchemy do banco para execução fora do Docker. Recomendado: PostgreSQL. |
| `DB_STARTUP_RETRIES` | Número de tentativas de conexão no boot da aplicação. |
| `DB_STARTUP_RETRY_DELAY` | Intervalo, em segundos, entre tentativas de conexão no boot. |
| `POSTGRES_DB` | Nome do banco usado pelo Docker Compose. |
| `POSTGRES_USER` | Usuário PostgreSQL usado pelo Docker Compose. |
| `POSTGRES_PASSWORD` | Senha PostgreSQL usada pelo Docker Compose. |
| `POSTGRES_PORT` | Porta local exposta para o PostgreSQL. |
| `APP_BASE_URL` | URL pública usada em QR Codes e links externos. |
| `APP_PORT` | Porta local da aplicação no Docker Compose. |
| `SETUP_TOKEN` | Token temporário para liberar `/setup` na primeira instalação. |
| `SESSION_SECURE` | Use `1` quando a aplicação estiver atrás de HTTPS. |
| `METRICS_TOKEN` | Token Bearer opcional para proteger `/metrics`. |
| `SMTP_*` | Configuração SMTP opcional via ambiente. Também pode ser feita pela interface. |

Nunca compartilhe ou versiona o arquivo `.env`.

Ao executar com Docker Compose, a aplicação usa o hostname interno `postgres`. Use `127.0.0.1` apenas quando a aplicação estiver rodando fora do container e acessando o PostgreSQL pela porta publicada no host.

## Backup

A aplicação possui backup lógico em JSON pela tela `Configurações > Backup` e pelas rotas autenticadas:

- `/api/backups`: lista configuração e arquivos.
- `/api/backups/run`: gera backup manual.
- `/api/backups/files/<arquivo>`: baixa ou exclui backup armazenado.
- `/api/backup.json`: baixa um backup lógico imediato.

Os arquivos gerados pela aplicação ficam em `instance/backups`. Para produção, esse backup lógico deve complementar snapshots ou dumps do PostgreSQL, não substituir uma política de backup do banco.

Para gerar um dump real do PostgreSQL pelo Docker Compose:

```bash
python scripts/db-dump.py
```

O script salva em `db_dumps/` usando `pg_dump` dentro do container `postgres`. Use `--format sql` se preferir dump texto; o padrão é formato customizado (`.dump`).

Backups locais de migração podem ser mantidos em `migration_backups/`, que não deve ser versionado.

## Endpoints operacionais

| Endpoint | Finalidade |
|---|---|
| `/health/live` | Liveness check |
| `/health/startup` | Startup check |
| `/health/ready` | Readiness check com teste de banco |
| `/metrics` | Métricas Prometheus |
| `/api/operational/status` | Indicadores operacionais autenticados |
| `/ping` | Health simples público |

## Rotas úteis

- `/`: dashboard principal.
- `/login`: autenticação.
- `/setup`: assistente de primeira configuração.
- `/asset/<id>`: perfil público do ativo via QR Code.
- `/api/export/assets.csv`: exportação CSV de ativos.
- `/api/export/colaboradores.csv`: exportação CSV de colaboradores.
- `/api/export/alocacoes.csv`: exportação CSV de alocações.

## Smoke test

Com a aplicação rodando:

```bash
./scripts/smoke-test.sh
```

Ou usando outra URL:

```bash
BASE_URL=http://servidor:5000 ./scripts/smoke-test.sh
```

## Documentação complementar

- [INSTALL.md](INSTALL.md)

## Recomendações para beta e produção

Antes de publicar em rede corporativa:

1. Troque `SECRET_KEY`, `POSTGRES_PASSWORD` e `SETUP_TOKEN`.
2. Use PostgreSQL e mantenha `FLASK_DEBUG=0`.
3. Configure `APP_BASE_URL` com o endereço real do sistema.
4. Use HTTPS e `SESSION_SECURE=1`.
5. Crie um administrador próprio e altere/remova credenciais de demonstração.
6. Proteja `/metrics` com `METRICS_TOKEN` ou restrição de rede.
7. Ative e teste backup automático.
8. Teste restauração antes de depender do backup em produção.
9. Monitore `/health/ready`, logs da aplicação e espaço em disco.
