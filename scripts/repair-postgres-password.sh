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
echo "Parando app para interromper tentativas com senha antiga..."
docker compose stop app >/dev/null 2>&1 || true

docker compose exec -T postgres psql \
  -U postgres \
  -d "$POSTGRES_DB" \
  -v ON_ERROR_STOP=1 \
  -c "ALTER USER \"${sql_user}\" WITH PASSWORD '${sql_password}';"

echo "Validando autenticacao TCP com a senha do .env..."
docker compose exec -T -e PGPASSWORD="$POSTGRES_PASSWORD" postgres psql \
  -h 127.0.0.1 \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  -v ON_ERROR_STOP=1 \
  -c "SELECT 1;"

echo "Recriando app com a configuracao atual..."
if ! docker compose up -d --build --force-recreate app; then
  die "Falha ao recriar o app. Verifique se a porta APP_PORT do .env esta livre e rode: docker compose logs --tail=80 app"
fi

echo "Senha ajustada e app recriado. Para acompanhar:"
echo "docker compose logs --tail=80 app"
