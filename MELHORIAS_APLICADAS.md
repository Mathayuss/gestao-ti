# Melhorias aplicadas nesta versão

## Correções funcionais

- Corrigido o perfil público do ativo para usar `asset.colaborador` em vez de `asset.usuario`.
- Corrigida a exibição da Service Tag no perfil público usando `asset.service_tag`.
- Corrigido o botão de confirmação de localização via QR Code, que apontava para uma rota inexistente.
- Criada rota pública segura para auditoria por QR Code: `/api/public/assets/<aid>/audit`.
- Corrigida a URL exibida no módulo de QR Code para usar `APP_BASE_URL`, removendo o valor fixo `localhost` da tela.
- Corrigido erro de JavaScript no módulo de usuários/categorias causado por template literal aninhado.
- Corrigida inconsistência do estoque inicial nos dados de demonstração: periféricos já alocados agora reduzem o saldo no seed.

## Validações e integridade

- Adicionada validação de campos obrigatórios no cadastro de ativos conforme configuração `campos_ativo_obrigatorios`.
- Adicionada validação de status permitido para ativos.
- Adicionada proteção contra duplicidade de patrimônio, Service Tag e MAC.
- Sanitização básica de strings recebidas por API.
- Normalização de números inteiros e decimais em insumos/periféricos.
- Bloqueio de quantidades zeradas/negativas em entrada, saída, devolução, kit admissão e alocação.
- Validação de nome obrigatório em colaboradores e insumos.
- Validação de status permitido no cadastro/edição de colaboradores.
- Alocação agora respeita regra de e-mail obrigatório quando configurada.
- Alocação agora respeita limite configurado de periféricos por colaborador.
- Termos de alocações encerradas não podem mais ser marcados como assinados.
- Criação de usuário exige senha mínima de 6 caracteres e perfil válido.

## Segurança e governança

- Adicionados handlers JSON para erros 404 e 500 em APIs.
- Adicionada opção `SHOW_DEMO_CREDENTIALS` para ocultar credenciais de demonstração na tela de login.
- Exportações e backup registram auditoria.
- Backup JSON restrito a Administrador.
- Exportações CSV restritas a Administrador, Técnico TI e Gestor.

## Novas funcionalidades

- Exportação CSV de ativos.
- Exportação CSV de colaboradores.
- Exportação CSV de alocações.
- Backup JSON dos principais dados do sistema.
- Botões de exportação adicionados às telas de ativos, colaboradores, alocações e configurações.
- Nome do PDF do termo agora usa colaborador + código do termo.

## Arquivos adicionados

- `.env.example`
- `README.md`
- `MELHORIAS_APLICADAS.md`

## Atualização de interface e usabilidade — 2026-05-10

### Tema e layout

- Adicionado suporte a tema claro/escuro com preferência persistida no navegador.
- Corrigida a barra lateral do dashboard para acompanhar o tema claro, usando superfícies claras, bordas suaves e texto escuro no modo claro.
- Mantida a variação escura da barra lateral apenas quando o tema escuro estiver ativo.
- Atualizados login, dashboard, perfil público do ativo e tela de assinatura com tokens visuais mais consistentes.
- Substituídos emojis por ícones SVG modernos e textos mais claros nos templates e no payload de histórico do ativo.
- Removidos emojis remanescentes de `templates/` e `app.py`.

### QR Code e etiquetas

- Revisada a aba `QR Code & Etiquetas`.
- Mantida seleção de ativo, pré-visualização do QR Code e link público do ativo.
- Melhorada a personalização de etiquetas com opções de:
  - tamanho da etiqueta;
  - campos exibidos;
  - nome da empresa;
  - número de cópias;
  - tamanho do QR Code;
  - estilo de borda;
  - exibição/ocultação da identificação `TI Control`.
- Ajustada a geração de preview e impressão para respeitar as novas opções de personalização.

### Segurança e UX de autenticação

- Adicionados headers HTTP de segurança básicos nas respostas.
- Corrigido o redirecionamento pós-login para aceitar apenas destinos seguros da própria aplicação.
- Adicionado rate limit simples para tentativas de login.
- Preservado o parâmetro `next` no formulário de login.

### Validações realizadas

- `python -m py_compile app.py`
- Renderização via Flask test client:
  - `/login`
  - `/asset/A001`
  - `/assinar/badtoken`
  - `/` autenticado com usuário de demonstração
- Busca Unicode por emojis em `templates/` e `app.py`, sem ocorrências remanescentes.

## Qualidade de código e robustez administrativa — 2026-05-12

### Backend

- Adicionado helper `json_payload()` para tratar payload JSON vazio ou inválido sem gerar erro interno.
- Adicionado helper `parse_bool()` para normalizar booleanos vindos da API.
- Criados normalizadores para configurações de empresa, alertas, regras de operação, campos obrigatórios de ativos, categorias, unidades e termos.
- A rota `PUT /api/settings` agora rejeita chaves desconhecidas e valida o formato das configurações antes de salvar.
- Rotas de setores e unidades passaram a limpar entradas, evitar duplicidade e responder erro claro para payload inválido.
- Configurações SMTP agora validam porta e e-mail remetente antes de persistir.
- Teste de e-mail agora aceita destinatário informado no payload e valida o endereço antes do envio.
- Normalização de dados da empresa passou a preservar e validar também `logo_base64`, usado em PDFs, configurações e etiquetas.
- Removido aviso com emoji no fallback de `SECRET_KEY`, substituído por logging estruturado.

### Frontend

- Removidos símbolos/emoji remanescentes encontrados por varredura Unicode.
- Corrigidos textos duplicados em botões de edição e limpeza de assinatura.
- Substituído indicador visual de sucesso na assinatura de devolução por marcador textual compatível com o tema.
- Adicionado upload, pré-visualização e remoção de logo da empresa em `Configurações > Geral > Dados da Empresa`.
- Adicionada validação client-side de tamanho do logo da empresa, com limite de 300 KB.
- Etiquetas agora podem exibir o logo da empresa no topo da etiqueta.
- Etiquetas agora podem exibir o logo da empresa no centro do QR Code, quando houver logo cadastrado.
- A aba de colaboradores agora separa a visualização entre colaboradores ativos e desligados/inativos.
- Adicionado botão `Desligados` com contador na tela de colaboradores.
- A visão de desligados passa a exibir data de desligamento e ação de reativação.
- Adicionado fluxo de reativação de colaborador com data de readmissão e opção de alteração de setor.
- Navegação principal agora persiste o módulo ativo em `localStorage` e no hash da URL, mantendo a tela atual após atualizar a página.
- Adicionada sincronização do menu ativo, título da página e rota hash para evitar retorno automático ao Dashboard no refresh.
- Configuração SMTP agora usa uma chave visual para ligar/desligar o envio de e-mail, deixando a tela mais limpa.
- SMTP configurado pela aplicação pode ser ativado, salvo e testado sem alterar variáveis de ambiente do servidor.
- Campo de senha SMTP pela aplicação deixou de ser bloqueado quando existe `SMTP_PASSWORD` no servidor; ao salvar pela tela, a aplicação usa a configuração cadastrada nela.
- Adicionado campo de destinatário para teste SMTP e ação `Salvar e Testar`.

### Operação e scripts

- `scripts/smoke-test.sh` foi mantido como script executável, permitindo execução direta do smoke test em ambientes locais ou CI.
- `.env.example` atualizado para informar que SMTP via variáveis de ambiente é opcional quando a configuração pela aplicação for usada.
- `README.md` atualizado para documentar que o SMTP pode ser configurado pela própria aplicação.

### Validações realizadas

- `git diff --check`
- `py_compile` de `app.py`
- Smoke test via Flask test client:
  - `/login`
  - `/asset/A001`
  - `/assinar/badtoken`
  - `/devolver/badtoken`
  - login com usuário administrador de demonstração
  - `GET /api/settings`
  - validações negativas em `/api/settings`, `/api/settings/unidades` e `/api/settings/email`
- Teste temporário de configuração SMTP pela aplicação com restauração dos settings originais.
- Varredura Unicode para emojis/símbolos problemáticos em `app.py` e `templates/`.
- Conferência do código atual contra `MELHORIAS_APLICADAS.md`, incluindo alterações em `app.py`, `templates/index.html`, `templates/devolver.html` e `scripts/smoke-test.sh`.
