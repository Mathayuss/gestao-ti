# Preparacao para Integracao com Active Directory e GLPI

## 1. Objetivo

Preparar o TI Control para integrar com:

- Active Directory ou LDAP corporativo, para autenticacao, sincronizacao de colaboradores, setores, unidades e grupos.
- GLPI via API, para reaproveitar inventario, chamados, computadores, usuarios, contratos, documentos e historico operacional.

A proposta e manter o TI Control como camada de controle patrimonial, alocacao, termos, QR Code, estoque de perifericos e fluxo interno de TI, usando AD e GLPI como fontes complementares.

## 2. O que podemos aproveitar do Active Directory

### 2.1 Autenticacao corporativa

Podemos permitir login no TI Control usando usuario e senha do dominio.

Beneficios:

- Reduz senha local no sistema.
- Aplica politica corporativa de senha.
- Facilita bloqueio imediato quando a conta e desativada no AD.
- Permite mapear grupos do AD para perfis do sistema.

Modelo recomendado:

| Grupo AD | Perfil TI Control |
|---|---|
| `TIControl-Admins` | Administrador |
| `TIControl-Tecnicos` | Tecnico TI |
| `TIControl-Gestores` | Gestor |
| `TIControl-Viewers` | Visualizador |

### 2.2 Sincronizacao de colaboradores

O AD pode alimentar ou atualizar a base de `Colaborador`.

Campos aproveitaveis:

| AD / LDAP | TI Control |
|---|---|
| `displayName` | `colaborador.nome` |
| `mail` | `colaborador.email` |
| `telephoneNumber` / `mobile` | `colaborador.telefone` |
| `title` | `colaborador.cargo` |
| `department` | `colaborador.setor` |
| `physicalDeliveryOfficeName` / `company` | `colaborador.unidade` |
| `employeeID` / `employeeNumber` | `colaborador.matricula` |
| `userAccountControl` / status da conta | `colaborador.status` |
| `manager` | campo futuro de gestor, se o modelo for expandido |

### 2.3 Offboarding automatico

Quando um usuario for desativado no AD, o TI Control pode:

- Marcar colaborador como `Inativo`.
- Abrir pendencia de devolucao.
- Listar ativos e perifericos vinculados.
- Gerar alerta para TI.
- Iniciar fluxo de offboarding.

Recomendacao: nao encerrar alocacao automaticamente sem revisao humana. O AD deve abrir alerta ou tarefa, pois a devolucao fisica precisa de conferencia.

### 2.4 Atualizacao de setores e unidades

Podemos usar `department`, `company` e/ou `physicalDeliveryOfficeName` para manter listas de setores e unidades mais consistentes.

Recomendacao:

- Sincronizar novos setores/unidades como sugestao ou cadastro automatico configuravel.
- Evitar remover setores/unidades automaticamente, pois ativos antigos podem depender desses valores.

## 3. O que podemos aproveitar do GLPI

### 3.1 Inventario de ativos

O GLPI pode ser fonte ou destino para computadores, monitores, impressoras, telefones e outros ativos.

Campos possiveis:

| GLPI | TI Control |
|---|---|
| `Computer.name` | `Asset.hostname` |
| serial / otherserial | `Asset.service_tag` ou `Asset.patrimonio` |
| fabricante | `Asset.fabricante` |
| modelo | `Asset.modelo` |
| endereco IP | `Asset.ip` |
| MAC | `Asset.mac` |
| sistema operacional | `Asset.os` |
| entidade/localizacao | `Asset.unidade` |
| usuario associado | `Asset.colaborador` |
| status | `Asset.status` |

### 3.2 Chamados e manutencao

Podemos enviar ou consultar chamados do GLPI relacionados aos ativos.

Usos recomendados:

- Criar ticket no GLPI a partir de incidente ou manutencao aberta no TI Control.
- Anexar laudo ou evidencias ao chamado.
- Sincronizar status do ticket para a OS interna.
- Exibir link do ticket GLPI no historico do ativo.

Fluxo sugerido:

```text
Incidente/OS no TI Control
  -> Criar ticket no GLPI
  -> Salvar glpi_ticket_id no TI Control
  -> Atualizar historico do ativo
  -> Consultar status do ticket periodicamente
```

### 3.3 Usuarios e areas

O GLPI tambem possui usuarios, entidades, grupos e localizacoes. Podemos usar esses dados para enriquecer:

- colaboradores;
- unidades;
- setores;
- responsaveis;
- localizacao fisica do ativo.

### 3.4 Documentos e anexos

Documentos ja existentes no GLPI podem ser relacionados ao ativo no TI Control:

- notas fiscais;
- imagens;
- contratos;
- comprovantes;
- laudos.

Recomendacao: inicialmente sincronizar apenas metadados e links. Copiar arquivos deve ser uma etapa posterior, pois envolve armazenamento, tamanho e permissao.

### 3.5 Contratos, fornecedores e garantias

O GLPI pode ajudar a preencher:

- fornecedor;
- contrato;
- data de compra;
- fim de garantia;
- documentos de aquisicao.

Esses dados podem alimentar alertas de garantia e relatorios no TI Control.

## 4. Fontes de verdade recomendadas

Para evitar conflito, cada dado deve ter uma fonte principal.

| Dado | Fonte recomendada |
|---|---|
| Login e status de conta | AD |
| Nome, e-mail, cargo e setor do colaborador | AD |
| Patrimonio interno | TI Control |
| Termos de responsabilidade | TI Control |
| Alocacao atual e assinatura | TI Control |
| Estoque de perifericos | TI Control |
| Chamados tecnicos | GLPI |
| Inventario tecnico detalhado | GLPI ou TI Control, conforme realidade atual |
| QR Code e etiqueta patrimonial | TI Control |
| Garantia e contratos | GLPI, se ja estiver maduro; senao TI Control |

Regra importante: patrimonio, termos e assinaturas devem continuar no TI Control, pois sao o diferencial operacional do sistema.

## 5. Arquitetura proposta

Criar uma camada isolada de integracoes:

```text
integrations/
  ad_client.py
  glpi_client.py
  sync_service.py
  mapping.py
  errors.py

routes/
  integrations.py
```

### 5.1 Responsabilidades

| Arquivo | Responsabilidade |
|---|---|
| `ad_client.py` | Conectar ao LDAP/AD, autenticar usuario, buscar usuarios e grupos. |
| `glpi_client.py` | Controlar sessao/token, chamadas REST, busca e criacao de itens/tickets. |
| `mapping.py` | Converter campos AD/GLPI para modelos do TI Control. |
| `sync_service.py` | Orquestrar sincronizacao, detectar diferencas e aplicar mudancas. |
| `errors.py` | Padronizar erros, timeouts e falhas externas. |
| `routes/integrations.py` | Endpoints administrativos para testar conexao, pre-visualizar sync e executar sync. |

### 5.2 Modo dry-run

Toda sincronizacao deve ter modo `dry-run` antes de alterar dados.

Exemplo:

```text
POST /api/integrations/ad/sync?dry_run=1
POST /api/integrations/glpi/sync-assets?dry_run=1
```

O retorno deve mostrar:

- registros novos;
- registros que seriam atualizados;
- conflitos;
- registros ignorados;
- erros de validacao.

## 6. Configuracoes necessarias

### 6.1 Active Directory

Configuracoes sugeridas:

| Chave | Exemplo |
|---|---|
| `AD_ENABLED` | `1` |
| `AD_SERVER` | `ldaps://ad.empresa.local` |
| `AD_DOMAIN` | `EMPRESA` |
| `AD_BASE_DN` | `DC=empresa,DC=local` |
| `AD_BIND_USER` | `svc_ticontrol@empresa.local` |
| `AD_BIND_PASSWORD` | senha da conta de servico |
| `AD_USER_FILTER` | `(objectClass=user)` |
| `AD_GROUP_ADMIN` | `CN=TIControl-Admins,OU=Grupos,DC=empresa,DC=local` |
| `AD_GROUP_TECH` | `CN=TIControl-Tecnicos,OU=Grupos,DC=empresa,DC=local` |

Recomendacoes:

- Usar LDAPS.
- Usar conta de servico somente leitura.
- Nao gravar senha do AD em texto claro na interface sem estrategia de segredo.
- Permitir fallback para usuario local administrador.

### 6.2 GLPI

Configuracoes sugeridas:

| Chave | Exemplo |
|---|---|
| `GLPI_ENABLED` | `1` |
| `GLPI_BASE_URL` | `https://glpi.empresa.com/apirest.php` |
| `GLPI_API_VERSION` | `v1` ou `v2` |
| `GLPI_APP_TOKEN` | token do cliente API |
| `GLPI_USER_TOKEN` | token do usuario de integracao |
| `GLPI_ENTITY_ID` | entidade padrao, se aplicavel |
| `GLPI_TIMEOUT_SECONDS` | `15` |
| `GLPI_VERIFY_TLS` | `1` |

Pontos confirmados na documentacao oficial do GLPI:

- A REST API v1 usa `App-Token` para identificar o cliente de API.
- A maioria das chamadas apos `initSession` exige `Session-Token`.
- Chamadas devem enviar `Content-Type`, normalmente `application/json`.
- Requisicoes `GET` devem enviar parametros na URL e corpo vazio.
- GLPI tambem possui documentacao de RESTful API v2 para versoes recentes.

## 7. Endpoints internos sugeridos

| Endpoint | Objetivo |
|---|---|
| `GET /api/integrations/status` | Ver status das integracoes configuradas. |
| `POST /api/integrations/ad/test` | Testar conexao e bind LDAP. |
| `POST /api/integrations/ad/auth-test` | Testar autenticacao de um usuario, sem salvar senha. |
| `POST /api/integrations/ad/sync-colaboradores` | Sincronizar colaboradores do AD. |
| `POST /api/integrations/glpi/test` | Testar conexao com GLPI. |
| `POST /api/integrations/glpi/sync-assets` | Sincronizar ativos GLPI/TI Control. |
| `POST /api/integrations/glpi/tickets` | Criar ticket GLPI a partir de incidente/OS. |
| `GET /api/integrations/jobs` | Listar ultimas execucoes. |

Todos devem exigir perfil `Administrador` ou permissao explicita em `Configuracoes`.

## 8. Campos novos recomendados

Para uma integracao segura, e melhor guardar IDs externos em vez de depender de nomes.

### 8.1 Colaborador

Campos futuros:

- `ad_dn`
- `ad_object_guid`
- `ad_sam_account_name`
- `ad_user_principal_name`
- `source`
- `last_sync_at`

### 8.2 Ativo

Campos futuros:

- `glpi_itemtype`
- `glpi_id`
- `glpi_entity_id`
- `glpi_last_sync_at`
- `source`

### 8.3 Manutencao / Incidente

Campos futuros:

- `glpi_ticket_id`
- `glpi_ticket_url`
- `glpi_ticket_status`
- `glpi_last_sync_at`

### 8.4 Nova tabela de logs

Criar tabela futura `integration_runs`:

| Campo | Uso |
|---|---|
| `id` | identificador da execucao |
| `provider` | `ad` ou `glpi` |
| `job_type` | tipo da rotina |
| `status` | sucesso, parcial, erro |
| `started_at` | inicio |
| `finished_at` | fim |
| `created_count` | criados |
| `updated_count` | atualizados |
| `skipped_count` | ignorados |
| `error_count` | erros |
| `details_json` | resumo detalhado |

## 9. Regras de sincronizacao

### 9.1 Colaboradores via AD

Criar colaborador quando:

- usuario AD estiver ativo;
- possuir nome e e-mail ou matricula;
- ainda nao existir no TI Control por `ad_object_guid`, matricula ou e-mail.

Atualizar colaborador quando:

- cargo, setor, unidade, e-mail ou telefone mudarem no AD;
- status mudar para inativo.

Nao fazer automaticamente:

- apagar colaborador;
- encerrar alocacao;
- remover historico;
- sobrescrever observacoes manuais.

### 9.2 Ativos via GLPI

Criar ativo quando:

- item GLPI for de tipo mapeado;
- tiver identificador confiavel, como serial, nome ou patrimonio;
- ainda nao existir no TI Control por `glpi_id`, patrimonio, service tag ou hostname.

Atualizar ativo quando:

- hostname, IP, MAC, modelo, fabricante, OS ou unidade mudarem;
- status GLPI for mapeado para status TI Control.

Nao fazer automaticamente:

- alterar patrimonio sem revisao;
- encerrar termo;
- trocar colaborador responsavel se houver termo ativo assinado, sem politica definida;
- baixar ativo sem confirmacao.

## 10. Conflitos esperados

| Conflito | Como tratar |
|---|---|
| E-mail duplicado entre colaboradores | Parar registro e pedir revisao. |
| Patrimonio diferente entre GLPI e TI Control | Manter TI Control e gerar alerta. |
| Ativo alocado no TI Control, mas outro usuario no GLPI | Gerar divergencia de auditoria. |
| Usuario inativo no AD com ativos alocados | Abrir pendencia de offboarding. |
| GLPI indisponivel | Nao bloquear operacao interna do TI Control. |
| Token vencido ou invalido | Registrar erro e alertar administrador. |

## 11. Segurança

Regras obrigatorias:

- Nunca expor tokens GLPI ou senha de bind AD nas respostas da API.
- Redigir segredos em backup JSON, como ja ocorre com SMTP.
- Usar timeout em chamadas externas.
- Usar TLS/LDAPS.
- Registrar auditoria de execucoes manuais.
- Permitir desativar integracao sem remover configuracao.
- Implementar rate limit ou bloqueio em testes de autenticacao AD.
- Manter login local de emergencia para administrador.

## 12. Fases de implementacao

### Fase 1 - Base segura

- Adicionar dependencias: `ldap3` e `requests`, se ainda nao existirem.
- Criar `integrations/ad_client.py` e `integrations/glpi_client.py`.
- Criar configuracoes e normalizadores.
- Criar endpoints de teste de conexao.
- Redigir segredos no backup.

### Fase 2 - AD

- Login via AD com fallback local.
- Mapeamento de grupos AD para perfis.
- Sincronizacao dry-run de colaboradores.
- Sincronizacao real de colaboradores.
- Alertas para usuario AD inativo com ativo alocado.

### Fase 3 - GLPI inventario

- Teste de sessao GLPI.
- Busca de ativos GLPI.
- Mapeamento GLPI -> TI Control.
- Dry-run de criacao/atualizacao de ativos.
- Sincronizacao controlada.

### Fase 4 - GLPI chamados

- Criar ticket GLPI a partir de incidente.
- Criar ticket GLPI a partir de OS.
- Salvar link/id do ticket no TI Control.
- Consultar status do ticket.
- Registrar eventos no historico do ativo.

### Fase 5 - UI administrativa

- Aba `Integracoes` em `Configuracoes`.
- Botao de testar AD.
- Botao de testar GLPI.
- Tela de pre-visualizacao de sincronizacao.
- Historico das ultimas execucoes.
- Alertas de divergencia.

## 13. Primeiro MVP recomendado

O melhor primeiro MVP e:

1. Tela/configuracao de integracao.
2. Teste de conexao AD.
3. Login AD com fallback local.
4. Sincronizacao dry-run de colaboradores.
5. Teste de conexao GLPI.
6. Busca de um ativo GLPI por serial/patrimonio.
7. Vinculo manual entre ativo TI Control e item GLPI.

Depois disso, podemos evoluir para sincronizacao automatica.

## 14. Dependencias de decisao antes de codar

Precisamos confirmar:

- Versao do GLPI em uso.
- Se o GLPI esta com REST API v1, RESTful API v2 ou ambas habilitadas.
- Se teremos `App-Token` e `User-Token` para uma conta de servico.
- Se o AD aceita LDAPS.
- Base DN e filtros reais do AD.
- Quais grupos AD mapeiam para cada perfil.
- Quem sera a fonte oficial do inventario: GLPI ou TI Control.
- Se a sincronizacao sera manual, agendada ou ambas.
- Se chamados de manutencao devem nascer no TI Control ou no GLPI.

## 15. Referencias oficiais GLPI

- GLPI REST API v1: https://help.glpi-project.org/documentation/modules/configuration/general/api/api
- GLPI RESTful API v2: https://help.glpi-project.org/documentation/modules/configuration/general/api/restful-api-v2
- GLPI Developer API: https://glpi-developer-documentation.readthedocs.io/en/master/devapi/

