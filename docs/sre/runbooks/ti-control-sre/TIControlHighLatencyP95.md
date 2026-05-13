# Runbook — TIControlHighLatencyP95

## Descrição

Este alerta dispara quando a latência p95 da aplicação fica acima do limite definido.

p95 significa que 95% das requisições estão respondendo abaixo daquele tempo. Se o p95 sobe, a experiência do usuário começa a degradar.

## Impacto

O sistema pode continuar disponível, mas lento. Usuários podem perceber demora ao abrir dashboard, listar ativos, gerar termos ou consultar QR Code.

## Verificação inicial

```bash
systemctl status ticontrol
journalctl -u ticontrol -n 100
