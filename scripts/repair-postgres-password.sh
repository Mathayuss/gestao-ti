#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

die() {
  echo "Erro: $*" >&2
  exit 1
}

read_env() {
  local key="$1"
  local line
  line="$(grep -E "^${key}=" .env 2>/dev/null | head -n 1 || true)"
  [[ -n "$line" ]] || die "Variavel ${key} nao encontrada no .env."
  line="${line#*=}"
  line="${line%\"}"
  line="${line#\"}"
  line="${line%\'}"
  line="${line#\'}"
  printf '%s' "$line"
}

command -v docker >/dev/null 2>&1 || die "Docker nao encontrado."
docker compose version >/dev/null 2>&1 || die "Docker Compose nao esta disponivel."
[[ -f ".env" ]] || die "Arquivo .env nao encontrado."

POSTGRES_DB="$(read_env POSTGRES_DB)"
POSTGRES_USER="$(read_env POSTGRES_USER)"
POSTGRES_PASSWORD="$(read_env POSTGRES_PASSWORD)"

[[ -n "$POSTGRES_DB" ]] || die "POSTGRES_DB vazio."
[[ -n "$POSTGRES_USER" ]] || die "POSTGRES_USER vazio."
[[ -n "$POSTGRES_PASSWORD" ]] || die "POSTGRES_PASSWORD vazio."

sql_user="${POSTGRES_USER//\"/\"\"}"
sql_password="${POSTGRES_PASSWORD//\'/\'\'}"

echo "Ajustando senha do usuario PostgreSQL '${POSTGRES_USER}' conforme o .env..."
docker compose exec -T postgres psql \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -v ON_ERROR_STOP=1 \
  -c "ALTER USER \"${sql_user}\" WITH PASSWORD '${sql_password}';"

echo "Senha ajustada. Reinicie a aplicacao com:"
echo "docker compose up -d --force-recreate app"
