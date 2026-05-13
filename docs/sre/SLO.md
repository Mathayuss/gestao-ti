# SLO — TI Control SRE

## Objetivo do serviço

O TI Control SRE é o serviço interno responsável por gestão de ativos, alocações, termos, estoque, QR Code e auditoria operacional de TI.

## SLIs principais

| SLI | Medição | Fonte |
|---|---|---|
| Disponibilidade HTTP | Percentual de respostas não 5xx nas rotas principais | `/metrics` |
| Readiness | Percentual de checks `/health/ready` com HTTP 200 | `/health/ready` |
| Latência | p95 de `ticontrol_http_request_duration_seconds` | Prometheus |
| Taxa de erro | Percentual de HTTP 5xx | Prometheus |
| Pendência operacional | Quantidade de termos pendentes, incidentes abertos e estoque crítico | `/api/sre/status` |

## SLO inicial recomendado

| Indicador | Meta inicial |
|---|---:|
| Disponibilidade mensal | 99,5% |
| Latência p95 rotas principais | <= 500 ms |
| Taxa de erro 5xx | < 1% |
| RPO backup lógico | 24 h |
| RTO ambiente local | 4 h |

## Error budget

Para SLO de 99,5%, o orçamento mensal de indisponibilidade é de aproximadamente 3h39min por mês.

## Rotas críticas

- `/login`
- `/`
- `/api/dashboard`
- `/api/assets`
- `/api/allocations`
- `/api/backup.json`
- `/asset/<id>`
- `/health/ready`

## Alertas sugeridos no Prometheus

```promql
# Taxa de erro 5xx acima de 1% em 5 minutos
sum(rate(ticontrol_http_requests_total{status=~"5.."}[5m]))
/
sum(rate(ticontrol_http_requests_total[5m])) > 0.01
```

```promql
# p95 de latência acima de 500 ms
histogram_quantile(0.95,
  sum(rate(ticontrol_http_request_duration_seconds_bucket[5m])) by (le)
) > 0.5
```
