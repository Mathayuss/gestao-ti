#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

die() {
  echo "Erro: $*" >&2
  exit 1
}

FORCE=0
CHECK=0
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    --check) CHECK=1 ;;
    *) die "Opcao desconhecida: $arg" ;;
  esac
done

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Comando '$1' nao encontrado."
}

random_hex() {
  local bytes="${1:-32}"
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "$bytes"
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c "import secrets; print(secrets.token_hex($bytes))"
  else
    od -An -N "$bytes" -tx1 /dev/urandom | tr -d ' \n'
  fi
}

prompt_default() {
  local label="$1"
  local default="$2"
  local value
  read -r -p "$label [$default]: " value
  echo "${value:-$default}"
}

port_in_use() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -H -ltn "sport = :$port" 2>/dev/null | grep -q .
  elif command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
  else
    return 1
  fi
}

validate_port() {
  local value="$1"
  local label="$2"
  [[ "$value" =~ ^[0-9]+$ ]] || die "$label deve ser numerica."
  (( value >= 1 && value <= 65535 )) || die "$label deve estar entre 1 e 65535."
}

validate_pg_identifier() {
  local value="$1"
  local label="$2"
  [[ "$value" =~ ^[A-Za-z_][A-Za-z0-9_]{1,62}$ ]] || die "$label deve ter 2 a 63 caracteres e usar letras, numeros ou underline, iniciando por letra/underline."
}

validate_url() {
  local value="$1"
  [[ "$value" =~ ^https?://[^[:space:]]+$ ]] || die "URL publica deve comecar com http:// ou https://."
}

need_cmd docker
docker compose version >/dev/null 2>&1 || die "Docker Compose nao esta disponivel. Atualize o Docker."
docker info >/dev/null 2>&1 || die "Docker nao esta rodando ou o usuario nao tem permissao."

if [[ "$CHECK" == "1" ]]; then
  echo "OK: Docker e Docker Compose disponiveis."
  echo "OK: instalador Linux pronto para executar."
  exit 0
fi

if [[ -f ".env" && "$FORCE" != "1" ]]; then
  read -r -p "Arquivo .env ja existe. Sobrescrever? [s/N]: " overwrite
  if [[ ! "$overwrite" =~ ^[sS]$ ]]; then
    die "Instalacao cancelada para preservar o .env atual."
  fi
fi

echo
echo "TI Control - instalacao com PostgreSQL"
echo

APP_PORT="$(prompt_default "Porta web da aplicacao" "5000")"
POSTGRES_PORT="$(prompt_default "Porta local do PostgreSQL" "5432")"
POSTGRES_DB="$(prompt_default "Nome do banco" "ticontrol_db")"
POSTGRES_USER="$(prompt_default "Usuario do banco" "ticontrol")"
APP_BASE_URL="$(prompt_default "URL publica" "http://localhost:${APP_PORT}")"

validate_port "$APP_PORT" "Porta web"
validate_port "$POSTGRES_PORT" "Porta PostgreSQL"
validate_pg_identifier "$POSTGRES_DB" "Nome do banco"
validate_pg_identifier "$POSTGRES_USER" "Usuario do banco"
validate_url "$APP_BASE_URL"

if port_in_use "$APP_PORT"; then
  die "A porta web $APP_PORT ja esta em uso."
fi
if port_in_use "$POSTGRES_PORT"; then
  die "A porta PostgreSQL $POSTGRES_PORT ja esta em uso."
fi

POSTGRES_PASSWORD="$(random_hex 24)"
SECRET_KEY="$(random_hex 32)"
SETUP_TOKEN="$(random_hex 18)"
SESSION_SECURE=0
[[ "$APP_BASE_URL" =~ ^https:// ]] && SESSION_SECURE=1

umask 077
cat > .env <<EOF
SECRET_KEY=${SECRET_KEY}
APP_BASE_URL=${APP_BASE_URL}
APP_PORT=${APP_PORT}
FLASK_DEBUG=0
SESSION_SECURE=${SESSION_SECURE}
SHOW_DEMO_CREDENTIALS=0
AUTO_SEED_DEMO=0
SERVICE_NAME=ti-control
BUILD_VERSION=0.1.2-BETA
ENVIRONMENT=local
SETUP_TOKEN=${SETUP_TOKEN}
WEB_CONCURRENCY=2
WEB_THREADS=4
GUNICORN_TIMEOUT=60
SELF_UPDATE_ENABLED=1
SELF_UPDATE_AUTO_RESTART=1
METRICS_TOKEN=
SMTP_ENABLED=0
POSTGRES_DB=${POSTGRES_DB}
POSTGRES_USER=${POSTGRES_USER}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_PORT=${POSTGRES_PORT}
EOF

echo
echo "Subindo containers..."
docker compose up -d --build app postgres

echo
echo "Instalacao iniciada."
echo "Acesse: ${APP_BASE_URL}/setup?token=${SETUP_TOKEN}"
echo
echo "Guarde este token ate finalizar o assistente:"
echo "${SETUP_TOKEN}"
echo
