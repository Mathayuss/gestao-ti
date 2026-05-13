# Melhorias SRE aplicadas

## Código

- Adicionados endpoints `/health/live`, `/health/startup` e `/health/ready`.
- Adicionado endpoint `/metrics` com Prometheus.
- Adicionado `X-Request-ID` por requisição.
- Adicionadas métricas HTTP:
  - total de requisições por método/rota/status;
  - histograma de latência;
  - requisições ativas;
  - exceções observadas;
  - informações de serviço/versão/ambiente.
- Adicionado endpoint autenticado `/api/sre/status` com indicadores operacionais.

## Operação

- Adicionado `Dockerfile` com Gunicorn.
- Adicionado `docker-compose.yml` com aplicação, Prometheus e Grafana.
- Adicionado `ops/prometheus/prometheus.yml`.
- Adicionado `scripts/smoke-test.sh`.
- Adicionado workflow `.github/workflows/ci.yml`.

## Documentação

- Criado `docs/sre/SLO.md`.
- Criado `docs/sre/RUNBOOK.md`.
- Criado `docs/sre/INCIDENT_RESPONSE.md`.
- Criado `docs/sre/OBSERVABILITY.md`.
