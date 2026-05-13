# Runbook — TIControlServiceDown

## Descrição

Este alerta dispara quando o Prometheus não consegue coletar métricas do serviço TI Control SRE.

Isso normalmente significa que a aplicação está fora do ar, o Gunicorn parou, o serviço systemd falhou ou a porta 5000 não está respondendo localmente.

## Impacto

Usuários podem não conseguir acessar o sistema de gestão de ativos, termos, alocações e consultas via QR Code.

## Verificação inicial

```bash
systemctl status ticontrol
curl http://127.0.0.1:5000/health/live
curl http://127.0.0.1:5000/health/ready
curl http://127.0.0.1:5000/metrics
