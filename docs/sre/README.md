# Trilha SRE do Projeto

Esta pasta documenta a evolução do TI Control para um projeto demonstrável de SRE.

## Camadas implementadas

- Health checks: liveness, readiness e startup.
- Métricas Prometheus.
- Request ID por requisição.
- Execução com Gunicorn.
- Docker Compose com App + Prometheus + Grafana.
- Smoke test de disponibilidade.
- SLO, runbook e processo de incidentes.

## Próximas camadas recomendadas

1. Migrar para PostgreSQL.
2. Criar testes automatizados com pytest.
3. Criar dashboards Grafana versionados em JSON.
4. Criar alert rules Prometheus.
5. Criar pipeline com build, teste, scan e deploy.
6. Adicionar OpenTelemetry para tracing.
7. Criar Terraform/Ansible para provisionamento.
