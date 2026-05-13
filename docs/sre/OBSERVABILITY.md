# Observabilidade — TI Control SRE

## Endpoints operacionais

| Endpoint | Uso |
|---|---|
| `/health/live` | Verifica se o processo está vivo |
| `/health/startup` | Verifica inicialização da aplicação |
| `/health/ready` | Verifica se o serviço pode receber tráfego |
| `/metrics` | Métricas Prometheus |
| `/api/sre/status` | Indicadores operacionais autenticados |

## Métricas expostas

- `ticontrol_http_requests_total`
- `ticontrol_http_request_duration_seconds`
- `ticontrol_http_active_requests`
- `ticontrol_http_exceptions_total`
- `ticontrol_app_info`

## Dashboards recomendados

1. Visão executiva
   - disponibilidade;
   - taxa de erro;
   - latência p95;
   - quantidade de incidentes abertos.

2. Visão técnica
   - requisições por rota;
   - erros por rota;
   - latência por rota;
   - health check do banco.

3. Visão operacional de TI
   - ativos em manutenção;
   - termos pendentes;
   - estoque abaixo do mínimo;
   - licenças vencendo.
