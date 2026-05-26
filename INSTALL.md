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

Se o Docker Desktop ainda não estiver instalado, o instalador irá orientar o processo. Também é possível pedir a instalação automática via `winget`:

```powershell
.\scripts\install-windows.ps1 -InstallDocker
```

Depois da instalação do Docker Desktop, abra o Docker Desktop, finalize a configuração inicial e execute o instalador novamente. Pode ser necessário reiniciar o Windows ou o PowerShell.
Se o `winget` solicitar permissão elevada, execute o PowerShell como administrador.

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

## Atualização

Instalações novas já ficam preparadas para atualização pela tela `Configurações > Atualizações`. A ação é manual: o administrador escolhe aplicar, o sistema gera backup lógico, baixa a versão mais recente do repositório público e reinicia a aplicação automaticamente.

Para instalações antigas, ou para reconstruir o container com esse suporte, use os scripts de atualização. Eles preservam o `.env`, geram backup lógico pela aplicação quando o container está em execução, atualizam o código, recriam apenas a aplicação e validam `/health/ready`.

No Windows PowerShell:

```powershell
.\scripts\update-windows.ps1
```

No Linux:

```bash
./scripts/update-linux.sh
```

Valide o ambiente sem alterar nada com:

```powershell
.\scripts\update-windows.ps1 -Check
```

ou:

```bash
./scripts/update-linux.sh --check
```

Use `-NoPull` ou `--no-pull` quando a nova versão já tiver sido copiada manualmente para a pasta do projeto. Se houver alterações locais, o atualizador interrompe por segurança; resolva essas alterações antes ou use `-AllowDirty` / `--allow-dirty` conscientemente.

## Dump do banco

Além do backup lógico JSON da aplicação, gere dumps periódicos do PostgreSQL em ambientes importantes:

```bash
python scripts/db-dump.py
```

O dump é salvo em `db_dumps/` e usa o `pg_dump` disponível no container `postgres`. Para gerar SQL texto:

```bash
python scripts/db-dump.py --format sql
```

## Solução de problemas

### `password authentication failed for user "ticontrol"`

Esse erro costuma acontecer quando já existe um volume PostgreSQL criado com uma senha antiga, mas o `.env` foi recriado com uma senha nova. O PostgreSQL só aplica `POSTGRES_PASSWORD` na primeira criação do volume; depois disso, trocar o `.env` não muda a senha gravada no banco.

Para corrigir sem apagar dados, rode:

```bash
./scripts/repair-postgres-password.sh
```

No Windows PowerShell:

```powershell
.\scripts\repair-postgres-password.ps1
```

O script para o app, ajusta a senha do usuário PostgreSQL conforme o `.env`, valida a autenticação TCP e recria o container da aplicação.

Não remova o volume `postgres_data` se já houver dados importantes na instalação.
