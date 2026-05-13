# Runbook — TIControlHighErrorRate

## Descrição

Este alerta dispara quando a aplicação começa a retornar erros HTTP 5xx.

Erros 5xx indicam falha interna no serviço, falha no backend, exceção não tratada ou problema de dependência.

## Impacto

Usuários podem conseguir acessar o sistema, mas algumas funções podem falhar, como cadastro, alocação, geração de termo, exportação ou consulta de QR Code.

## Verificação inicial

```bash
curl http://127.0.0.1:5000/health/ready
journalctl -u ticontrol -n 100
