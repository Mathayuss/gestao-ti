# Instalação do TI Control

Esta instalação usa Docker Compose com PostgreSQL incluso e um assistente web em `/setup`.

## Requisitos

- Docker instalado e em execução.
- Docker Compose disponível pelo comando `docker compose`.
- Porta web livre, por padrão `5000`.
- Porta local do PostgreSQL livre, por padrão `5432`.

## Linux

```bash
git clone https://github.com/Mathayuss/gestao-ti.git
cd gestao-ti
./scripts/install-linux.sh
```

Para validar pré-requisitos sem criar `.env` nem subir containers:

```bash
./scripts/install-linux.sh --check
```

O script irá:

- validar Docker e Docker Compose;
- perguntar porta web, porta do PostgreSQL, banco, usuário e URL pública;
- gerar `.env` com `SECRET_KEY`, senha do PostgreSQL e `SETUP_TOKEN`;
- subir `app` e `postgres`;
- exibir o link do assistente web.

## Windows

No PowerShell:

```powershell
git clone https://github.com/Mathayuss/gestao-ti.git
cd gestao-ti
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install-windows.ps1
```

Para validar pré-requisitos sem criar `.env` nem subir containers:

```powershell
.\scripts\install-windows.ps1 -Check
```

O fluxo é o mesmo do Linux.

## Assistente Web

Após subir os containers, acesse o link exibido pelo instalador:

```txt
http://localhost:5000/setup?token=SEU_TOKEN
```

O assistente permite configurar:

- validação visual da conexão PostgreSQL usada pela aplicação;
- dados da empresa;
- usuário administrador inicial;
- URL pública;
- SMTP opcional pela aplicação;
- backup automático.

Depois de concluir, o assistente fica bloqueado porque já existe um administrador.

## Arquivo `.env`

O instalador gera automaticamente:

```env
DATABASE_URL=postgresql+psycopg://usuario:senha@postgres:5432/ticontrol_db
POSTGRES_DB=ticontrol_db
POSTGRES_USER=ticontrol
POSTGRES_PASSWORD=...
SETUP_TOKEN=...
AUTO_SEED_DEMO=0
```

Quando a aplicação roda dentro do Docker Compose, o host do banco deve ser `postgres`. Use `127.0.0.1` apenas para executar a aplicação fora do container, conectando no PostgreSQL publicado na máquina.

Não compartilhe o `.env`; ele contém segredos da instalação.

## Observabilidade

Prometheus e Grafana ficam em profile separado. Para subir:

```bash
docker compose --profile observability up -d
```

## Reinstalação

Para recriar o `.env`, use:

```bash
./scripts/install-linux.sh --force
```

ou:

```powershell
.\scripts\install-windows.ps1 -Force
```

Isso não remove volumes Docker automaticamente. Para apagar dados persistentes, faça isso manualmente e com backup prévio.
