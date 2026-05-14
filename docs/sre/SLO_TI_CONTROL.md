# SLO — TI Control SRE

## Serviço

TI Control SRE — sistema Flask para gestão de ativos, termos, alocações, QR Code e controle operacional de TI.

## Objetivo

Definir metas mínimas de confiabilidade para operação, monitoramento e resposta a incidentes.

## Período de avaliação

30 dias.

---

## SLI 1 — Disponibilidade

### Definição

Percentual de tempo em que o Prometheus consegue coletar métricas do serviço.

### Query PromQL

```promql
avg_over_time(up{job="ti-control-sre"}[30d]) * 100
