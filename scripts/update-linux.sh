#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

CHECK=0
NO_PULL=0
ALLOW_DIRTY=0
for arg in "$@"; do
  case "$arg" in
    --check) CHECK=1 ;;
    --no-pull) NO_PULL=1 ;;
    --allow-dirty) ALLOW_DIRTY=1 ;;
    *) echo "Erro: opcao desconhecida: $arg" >&2; exit 1 ;;
  esac
done

die() {
  echo "Erro: $*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Comando '$1' nao encontrado."
}

env_value() {
  local name="$1"
  local default="$2"
  if [[ ! -f .env ]]; then
    echo "$default"
    return
  fi
  local line
  line="$(grep -E "^${name}=" .env | head -n 1 || true)"
  if [[ -z "$line" ]]; then
    echo "$default"
  else
    echo "${line#*=}"
  fi
}

set_env_value() {
  local name="$1"
  local value="$2"
  [[ -f .env ]] || return 0
  local tmp
  tmp="$(mktemp)"
  if grep -qE "^${name}=" .env; then
    sed "s|^${name}=.*|${name}=${value}|" .env > "$tmp"
  else
    cat .env > "$tmp"
    printf '%s=%s\n' "$name" "$value" >> "$tmp"
  fi
  mv "$tmp" .env
}

app_backup() {
  local running
  running="$(docker compose ps --status running --services 2>/dev/null || true)"
  if ! printf '%s\n' "$running" | grep -qx "app"; then
    echo "Aviso: container app nao esta em execucao; backup pela aplicacao foi pulado."
    return
  fi
  echo "Gerando backup pre-atualizacao..."
  docker compose exec -T app python -c "from app import app, _write_backup_file; app.app_context().push(); result=_write_backup_file('manual', generated_by='update_script'); print(result.get('filename','backup gerado'))"
}

wait_ready() {
  echo "Aguardando aplicacao ficar pronta..."
  for _ in $(seq 1 30); do
    if docker compose exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health/ready', timeout=3).read()" >/dev/null 2>&1; then
      echo "OK: aplicacao pronta."
      return
    fi
    sleep 2
  done
  die "Aplicacao nao ficou pronta dentro do tempo esperado. Verifique: docker compose logs app"
}

need_cmd docker
docker compose version >/dev/null 2>&1 || die "Docker Compose nao esta disponivel. Atualize o Docker."
docker info >/dev/null 2>&1 || die "Docker nao esta rodando ou o usuario nao tem permissao."
[[ -f .env ]] || die "Arquivo .env nao encontrado. Execute a instalacao antes de atualizar."

if [[ "$CHECK" == "1" ]]; then
  echo "OK: Docker, Docker Compose e .env disponiveis."
  echo "OK: atualizador Linux pronto para executar."
  exit 0
fi

if [[ "$NO_PULL" != "1" ]]; then
  need_cmd git
  if [[ -n "$(git status --porcelain)" && "$ALLOW_DIRTY" != "1" ]]; then
    die "Existem alteracoes locais. Salve/commite antes de atualizar, ou use --allow-dirty se souber o que esta fazendo."
  fi
fi

echo
echo "TI Control - atualizacao"
echo

previous_version="$(env_value BUILD_VERSION 0.1.1-BETA)"
echo "Versao atual declarada: ${previous_version}"

app_backup

if [[ "$NO_PULL" != "1" ]]; then
  echo "Baixando ultima versao do repositorio..."
  git pull --ff-only
fi

new_version="0.1.1-BETA"
if [[ -f VERSION ]]; then
  new_version="$(tr -d '\r\n' < VERSION)"
elif command -v git >/dev/null 2>&1; then
  new_version="$(git rev-parse --short HEAD)"
fi
set_env_value BUILD_VERSION "$new_version"

echo "Recriando container da aplicacao..."
docker compose build app
docker compose up -d app postgres

wait_ready

echo
echo "Atualizacao concluida."
echo "Versao aplicada: ${new_version}"
echo "URL local: http://localhost:$(env_value APP_PORT 5000)"
echo
