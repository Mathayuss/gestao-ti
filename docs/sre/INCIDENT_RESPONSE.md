# Processo de Incidentes — TI Control SRE

## Severidade

| Severidade | Critério | Exemplo |
|---|---|---|
| SEV1 | Sistema indisponível para todos | App fora do ar, banco inacessível |
| SEV2 | Função crítica indisponível | Não gera termo, não aloca ativo |
| SEV3 | Degradação parcial | Lentidão, erro intermitente |
| SEV4 | Baixo impacto | Ajuste visual, erro em relatório não crítico |

## Fluxo

1. Detectar pelo alerta, chamado ou usuário.
2. Classificar severidade.
3. Registrar incidente no sistema ou ferramenta ITSM.
4. Comunicar impacto e previsão inicial.
5. Mitigar primeiro, corrigir depois.
6. Registrar causa raiz.
7. Criar ação preventiva.

## Modelo de RCA

```text
Incidente:
Data/hora início:
Data/hora normalização:
Severidade:
Impacto:
Causa raiz:
Fator contribuinte:
Ação imediata:
Ação definitiva:
Como detectar mais cedo:
Como evitar recorrência:
Responsável:
Prazo:
```
