#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:5000}"

echo "[1/5] liveness"
curl -fsS "$BASE_URL/health/live" >/dev/null

echo "[2/5] readiness"
curl -fsS "$BASE_URL/health/ready" >/dev/null

echo "[3/5] ping"
curl -fsS "$BASE_URL/ping" >/dev/null

echo "[4/5] metrics"
curl -fsS "$BASE_URL/metrics" | grep -q "ticontrol_http_requests_total"

echo "[5/5] login page"
curl -fsS "$BASE_URL/login" | grep -qi "login\|entrar\|usuário\|usuario"

echo "Smoke test OK"
