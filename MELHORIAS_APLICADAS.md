# Melhorias aplicadas nesta versão

## Refatoração arquitetural incremental — 2026-07-22

- As rotas separadas passaram a usar o Blueprint compartilhado `routes.blueprint.bp`, preservando os nomes antigos de endpoint para manter compatibilidade com templates, `url_for` e links públicos existentes.
- Criada migration Alembic `b7c4d2a93f10_schema_sync_print_terms.py` para sincronizar recursos recentes de agentes de impressão, pacotes de termos, alocações múltiplas e campos auxiliares.
- O startup agora reconhece quando o banco já está no revision Alembic esperado e evita executar a migração legada manual desnecessariamente.
- Criado `services/email_service.py` para concentrar configuração SMTP, leitura de secret file, templates e envio de e-mails.
- Criado `services/settings_service.py` para centralizar leitura e gravação das configurações persistidas.
- Criado `services/template_renderer.py` para unificar a renderização de variáveis em termos, PDFs e e-mails.
- Removida a ponte `_export_route_globals()` de 12 módulos de rota, substituindo dependências implícitas por imports explícitos.
- A ponte temporária ficou restrita aos módulos mais densos de ativos, alocações, devoluções e termos avulsos, para uma próxima rodada dedicada.
- Mantidos wrappers de compatibilidade no `app.py`, reduzindo risco para as rotas atuais durante a migração gradual para camada de serviços.
- Adicionado teste para garantir que o Blueprint compartilhado mantém os nomes legados de endpoints.
- Validado `py_compile`, `unittest discover -s tests`, smoke de renderização de templates e `git diff --check`.

## Desmembramento do dashboard principal — 2026-06-10

- O antigo `templates/index.html` foi reduzido de mais de 6 mil linhas para um template mínimo de composição.
- Criado `templates/layouts/app.html` como layout base do dashboard autenticado.
- Criados partials para `sidebar`, `header`, `footer` e `modal`, reduzindo acoplamento visual no template principal.
- O CSS inline foi extraído para `static/css/app.css`.
- O JavaScript inline foi extraído e dividido entre `static/js/core/` e `static/js/modules/`.
- Criado `templates/partials/scripts.html` para carregar os módulos JavaScript em ordem explícita.
- O módulo de configurações foi subdividido em `static/js/modules/settings/`, separando renderização, categorias, dados gerais/aparência, e-mail, backup/atualizações e termos.
- A versão da aplicação passou a ser entregue ao JavaScript por um bootstrap mínimo `window.TICONTROL_BOOT`, preservando o uso de `build_version` do Flask.
- CSS, favicon inicial e scripts passaram a receber cache busting com `build_version` na query string.
- O CI passou a instalar Node.js 20 e validar sintaxe de todos os arquivos JavaScript com `node --check`.
- O CI passou a executar a suíte `unittest discover -s tests`.
- Adicionado smoke test para validar que o shell do dashboard referencia assets versionados e que todos os arquivos estáticos renderizados respondem corretamente.
- A refatoração foi feita sem mudança intencional de comportamento, preparando futuras melhorias por módulo.

## Modelos de termos independentes — 2026-06-10

- A tela `Configurações > Termos` passou a tratar todos os documentos como modelos de termos, sem distinção visual entre categorias antigas.
- Recebimento, devolução e empréstimo ficam identificados como modelos padrão do sistema.
- VPN, BYOD, confidencialidade e novos modelos passam a aparecer como modelos personalizados, com o mesmo estilo de card.
- Cada modelo salva título, preâmbulo, cláusulas e rodapé de forma independente.
- A prévia e o editor reconhecem cada modelo por tipo, mantendo textos totalmente separados entre si.
- A geração de PDF passou a usar o template específico do tipo selecionado.
- A página pública de assinatura passou a exibir o conteúdo personalizado do respectivo termo.
- A API ganhou aliases `/api/termos...`, preservando compatibilidade com rotas antigas.
- Links novos de assinatura usam `/assinar-termo/<token>`, preservando compatibilidade com links antigos.
- Adicionados testes para garantir independência dos modelos e validação de cláusulas.

## Migrações Alembic/Flask-Migrate — 2026-06-10

- Criada a estrutura `migrations/` com Alembic/Flask-Migrate.
- Gerada migration baseline `ade7d99e9212_baseline_schema.py` com o schema atual da aplicação.
- Validado `flask db upgrade` em banco SQLite temporário para criar o schema a partir da baseline.
- Validado `flask db current` apontando para o revision `ade7d99e9212 (head)`.
- Validado `flask db check` sem diferenças pendentes entre modelos e migration.
- Atualizado `Dockerfile` com `FLASK_APP=app:create_app` para facilitar comandos Flask CLI dentro do container.
- Atualizado `README.md` com fluxo seguro para banco novo, banco existente e uso de `stamp head`.
- Atualizado `migrations/README` com alerta para não aplicar baseline diretamente sobre bancos existentes.

## Camada de serviço para Backup — 2026-06-10

- Criado `services/backup_service.py` com regras puras de configuração e agendamento de backup.
- O `app.py` passou a delegar parsing de horário, normalização de configuração, cálculo da próxima janela e verificação de vencimento para o service layer.
- Mantidos os helpers antigos com underscore para preservar compatibilidade com rotas e testes existentes.
- A configuração de backup agora possui testes dedicados para frequência diária, semanal e mensal.
- Adicionados testes para validação de horário, limites de retenção, dia da semana, dia do mês e rotina de backup devido.
- Confirmado o tratamento de frequência mensal em meses com menos dias, usando o último dia válido do mês.

## Camada de serviço para Ativos — 2026-06-10

- Criado o diretório `services/` para iniciar a separação formal de regras de negócio.
- Criado `services/asset_service.py` com validação de ativos, checagem de duplicidade, normalização de filtro de categoria e geração de patrimônio.
- O `app.py` passou a delegar validações e geração de patrimônio para a camada de serviço, mantendo compatibilidade com as rotas atuais.
- A rota `/api/assets` passou a usar o normalizador de categoria do service layer para tratar `Todos`, `Todas`, `all` e `__all__`.
- Corrigida a geração do próximo patrimônio para ignorar códigos legados sem sufixo numérico, evitando reiniciar a sequência indevidamente.
- Adicionados testes unitários para regras de ativos, filtro de categoria e sequência patrimonial.

## Refatoração arquitetural para beta — 2026-06-09

- Criado `extensions.py` para centralizar `SQLAlchemy`, `CSRFProtect`, `LoginManager` e `Flask-Migrate`.
- Criado `models.py` com os modelos SQLAlchemy e perfis de permissão, reduzindo o tamanho e a responsabilidade do `app.py`.
- O `app.py` agora inicializa extensões via `init_app`, mantendo compatibilidade com as rotas atuais.
- Adicionado `create_app()` como ponto de entrada compatível com testes, Flask CLI e evolução para application factory.
- Adicionado `wsgi.py` para deploys que preferem importar `wsgi:app`.
- Adicionadas chaves `AUTO_CREATE_DB` e `AUTO_LEGACY_MIGRATIONS` para permitir transição gradual de migração manual para Alembic/Flask-Migrate em produção.
- Adicionados smoke tests para factory, health checks, login e proteção de API sem autenticação.

## Remodelagem de Configurações > Termos — 2026-06-09

- A tela de termos foi reorganizada como um gerenciador de modelos em cards.
- Cada modelo agora possui ações consistentes para editar, pré-visualizar e carregar exemplo.
- Os modelos personalizados saíram da linha de chips do preview e passaram para uma lista compacta com botão dedicado de novo termo.
- O editor passou a abrir como uma área dedicada com botão de voltar, reduzindo poluição visual na primeira dobra.
- A prévia passou a abrir em modal amplo, sem ocupar espaço fixo na tela de configuração.

## Matriz de compatibilidade visual — 2026-05-27

- A lista `Compatibilidade — Ativo × Insumo` recebeu layout visual mais alinhado à identidade Enterprise SaaS do sistema.
- A matriz foi compactada em uma lista por categoria de ativo, com chips selecionáveis para categorias de insumo.
- Cada linha exibe estado visual `Livre` ou quantidade de categorias permitidas, mantendo a regra existente de linha sem seleção liberar todos os insumos.

## Imagens por categoria de ativo — 2026-05-27

- A tela `Configurações > Operação > Categorias de Ativos` agora permite definir imagem padrão por categoria.
- Os cards da aba `Ativos de TI` usam a imagem da categoria quando cadastrada, mantendo o ícone automático como fallback.
- As imagens aceitas são PNG, JPG ou WEBP, com limite de 1 MB por categoria.
- A configuração aproveita a estrutura existente `categorias_config`, sem criar uma nova aba.

## Cards de ativos — 2026-05-27

- A aba `Ativos de TI` passou a ter visualização em cards como padrão.
- Mantida alternância entre `Cards` e `Tabela`, com preferência persistida no navegador.
- Cada card exibe categoria, marca/modelo, patrimônio, hostname, Service Tag, status, responsável, localização, garantia e IP/MAC.
- Adicionada barra de ações por card para visualizar, editar, abrir QR Code e consultar histórico.
- A visualização em cards segue o padrão visual corporativo do sistema, com bordas discretas, sombras suaves e badges de status.

## Correção de filtros em Ativos — 2026-05-27

- Corrigido o filtro de categorias na aba `Ativos de TI` para manter todas as opções disponíveis após selecionar uma categoria.
- A opção `Todos` agora limpa corretamente o filtro em vez de buscar uma categoria literal chamada `Todos`.
- A API `/api/assets` também passou a tratar `Todos`, `Todas` e `all` como ausência de filtro para compatibilidade.

## Agendamento avançado de backup — 2026-05-27

- Adicionado horário configurável para execução do backup automático.
- Frequência semanal agora permite escolher o dia da semana.
- Frequência mensal agora permite escolher o dia do mês, respeitando o último dia válido em meses menores.
- A rotina automática passou a executar apenas após a janela configurada da frequência atual.
- A tela `Configurações > Backup` exibe a programação atual e salva os novos campos.

## Limpeza de identidade pública e observabilidade — 2026-05-21

- Removida a documentação de estudo pessoal de confiabilidade operacional do repositório público.
- Padronizada a marca exibida para `TI Control`, sem sufixos internos de estudo.
- Mantidos health checks, métricas, readiness e endpoint operacional por serem úteis para operação real.
- Renomeado o endpoint autenticado de indicadores para `/api/operational/status`.
- Atualizados README, instaladores, Docker Compose, Prometheus e templates públicos para a nova nomenclatura.

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

## Finalização de Backup e Templates de E-mail — 2026-05-13

### Configurações de e-mail

- Adicionada seção `Templates de E-mail` dentro de `Configurações > E-mail`.
- Criado editor visual para personalizar assunto, mensagem, texto do botão e rodapé dos e-mails de:
  - termo de responsabilidade;
  - termo de devolução.
- Incluída indicação das variáveis disponíveis por template, como `{empresa}`, `{colaborador}`, `{ativo}` e `{link}`.
- Adicionada ação para restaurar o conteúdo padrão de cada template antes de salvar.
- Integrada a tela com a rota `PUT /api/settings/email/templates`.

### Backup pela aplicação

- Reestruturada a aba `Configurações > Backup`.
- Adicionada chave visual para ativar/desativar backup automático.
- Adicionados campos para frequência do backup, retenção de arquivos e inclusão opcional do log de auditoria.
- Adicionados cartões de status com última execução, situação atual e frequência configurada.
- Adicionada ação `Gerar Agora`, integrada à rota `POST /api/backups/run`.
- Adicionada listagem de backups armazenados pela aplicação, com tamanho, data, hash SHA-256, download e exclusão.
- Mantidas as exportações CSV na mesma aba, separadas da rotina de backup.

### Validações realizadas

- `git diff --check`
- `py_compile` de `app.py`
- Smoke test via Flask test client:
  - login com usuário administrador de demonstração;
  - `GET /api/settings`;
  - `PUT /api/settings/backup`;
  - `PUT /api/settings/email/templates`;
  - `GET /api/backups`;
  - `POST /api/backups/run`;
  - `DELETE /api/backups/files/<arquivo>`.

## Etiquetas, Aparência e Tela de Login — 2026-05-14

### Etiquetas

- Logo da empresa agora é exibida ao lado do nome da empresa na mesma linha (layout flex row com `align-items:center` e `gap:4px`).
- Nome do ativo (hostname) mantido em uma única linha: removido `word-break:break-all`, adicionado `white-space:nowrap`. Font-size reduzido automaticamente com base na largura disponível e no comprimento do nome, respeitando mínimo de 7px.
- Corrigido o `print-zone` (div de impressão de etiquetas) que ficava visível no rodapé da tela após abrir o diálogo de impressão. Adicionado `display:none` fora do `@media print`.

### Personalização Visual (Aparência)

- Substituída a opção "Cor de Fundo do Sidebar" pela opção **"Cor de Hover dos Itens do Menu"**, que aplica a variável CSS `--sb-hover` em vez de `--sb`. Atualizado normalizer em `app.py` (`cor_sidebar` → `cor_hover`).

### Tela de Login

- Removido o botão de alternância de tema claro/escuro da tela de login. O tema continua sendo aplicado automaticamente via `localStorage` ou preferência do sistema operacional.
- Removidos CSS e funções JS não utilizados após a remoção do botão (`.topbar`, `.theme-btn`, `applyTheme`, `toggleTheme`, ícones `sun`/`moon`).
- Adicionado campo **Transparência do Box de Login** na aba `Configurações > Aparência > Tela de Login`:
  - Slider moderno com gradiente azul preenchendo o progresso e thumb circular estilizado (classe `.ap-range`).
  - Badge com valor percentual atualizado em tempo real ao lado do slider.
  - Campo numérico sincronizado com o slider.
  - Valor salvo como `login_box_transparencia` (inteiro 0–100) via `PUT /api/settings`.
  - Normalizer em `app.py` valida o intervalo 0–100.
  - Aplicado no `login.html` via Jinja2 como `rgba(255,255,255, opacity)` no `.card`, com variante dark `rgba(17,24,39, opacity)`.

### Preview ao vivo da tela de login

- Adicionado preview ao vivo da transparência do box de login na aba Aparência.
- Preview exibe a imagem de fundo salva ou nova imagem selecionada, com o box mock sobre ela.
- Opacidade do box atualizada em tempo real ao mover o slider ou digitar no campo numérico.
- Ao selecionar nova imagem de fundo, o preview é atualizado imediatamente via `FileReader`.
- Layout reorganizado em **três colunas** no card Tela de Login:
  1. **Transparência** (172px fixo): slider compacto + badge + campo numérico.
  2. **Pré-visualização** (flex, máx. 500px): preview 16/9 com imagem de fundo real.
  3. **Esquema de Cores** (220px fixo): cor primária, cor dos botões, hover do menu — com botões Salvar e Restaurar. Card separado de cores removido.

### Validações realizadas

- `py_compile` de `app.py` sem erros.
- Verificada ausência de `</script>` dentro de template literals em `index.html`.
- Teste manual: slider, badge e preview sincronizados; transparência refletida corretamente no login após salvar.

## Endurecimento Beta: Permissões, Licenças e Anexos — 2026-05-15

### Modularização de rotas

- Criado o módulo `routes/licenses.py` para concentrar as rotas de licenças fora do `app.py` e fora de `routes/operations.py`.
- Registrado o novo módulo no carregamento da aplicação em `register_route_modules()`.
- Mantido no `app.py` apenas o que ainda é compartilhado por toda a aplicação: modelos, helpers, permissões e rotinas transversais.

### Permissões dinâmicas no backend

- O decorator `requires()` passou a considerar o módulo acessado e a ação HTTP executada.
- As permissões configuradas em `perfil_permissoes` agora são aplicadas nas APIs, não apenas na interface.
- Perfis personalizados podem liberar ações quando tiverem módulo e permissão compatíveis.
- O perfil Administrador segue com acesso total garantido pelo sistema.
- Adicionado mapeamento de rotas para módulos como ativos, insumos, colaboradores, alocações, licenças, manutenção, auditorias, alertas, usuários e configurações.

### Licenças

- Adicionada validação centralizada para cadastro e edição de licenças.
- Campos numéricos rejeitam valores inválidos ou negativos.
- O campo vencimento passa a validar o formato `AAAA-MM-DD`.
- O campo tipo passa a aceitar somente opções conhecidas.
- Software passou a ser obrigatório.
- O retorno da licença agora inclui `saldo` e `situacao`, facilitando leitura de compliance e excesso de licenças.
- Cadastro e edição de licenças agora registram auditoria.

### Anexos

- Criado helper central `_create_attachment_record()` para padronizar uploads.
- Uploads legados de ativo, licença e manutenção foram conectados à rotina central de anexos.
- Corrigido o upload legado de ativo, que tentava usar um campo de anexos inexistente no modelo `Asset`.
- Downloads e remoções de anexos passaram a respeitar o módulo da entidade vinculada.
- Remoção de anexos agora também permite perfis personalizados quando tiverem permissão de exclusão no módulo correspondente.

### Validações realizadas

- `py_compile` de `app.py` e `routes/*.py`.
- `git diff --check`.
- Smoke test via Flask test client:
  - login com administrador;
  - `GET /api/licenses`;
  - validação negativa em `POST /api/licenses`;
  - criação temporária de licença válida;
  - upload temporário de anexo em licença;
  - liberação temporária de edição de licenças para perfil Gestor via `perfil_permissoes`;
  - restauração das permissões originais e remoção dos dados temporários criados no teste.

## Instalador com PostgreSQL e Setup Web — 2026-05-19

### Instalação Linux e Windows

- Criado `scripts/install-linux.sh` para instalação guiada em Linux.
- Criado `scripts/install-windows.ps1` para instalação guiada em Windows/PowerShell.
- Scripts validam Docker, Docker Compose e portas locais antes de iniciar.
- Adicionado modo seguro de verificação: `install-linux.sh --check` e `install-windows.ps1 -Check`.
- Adicionada validação de portas, nomes de banco/usuário PostgreSQL e URL pública antes de gerar `.env`.
- Scripts geram automaticamente `.env`, `SECRET_KEY`, senha do PostgreSQL e `SETUP_TOKEN`.
- Scripts sobem `app` e `postgres` via Docker Compose e exibem o link de `/setup`.

### PostgreSQL no Docker Compose

- `docker-compose.yml` passou a usar PostgreSQL como banco padrão da instalação.
- `DATABASE_URL`, portas, banco, usuário e senha passaram a ser parametrizados pelo `.env`.
- Prometheus e Grafana foram movidos para o profile `observability`, evitando subir ferramentas extras na instalação padrão.
- Adicionado suporte aos drivers `psycopg` e `psycopg2-binary` em `requirements.txt`.

### Assistente Web `/setup`

- Criada rota `routes/setup.py`.
- Criado template `templates/setup.html` com fluxo em etapas:
  - banco de dados;
  - empresa;
  - administrador;
  - serviços;
  - finalização.
- `/setup` exige `SETUP_TOKEN` e fica bloqueado após existir administrador.
- O assistente cria o administrador inicial, configura dados da empresa, backup e SMTP opcional.
- SMTP opcional agora valida servidor, e-mail remetente e faixa de porta.
- URL pública salva no setup passou a ser usada pelos links gerados pelo sistema mesmo após restart.
- Adicionado `AUTO_SEED_DEMO=0` para instalações novas não criarem dados demonstrativos automaticamente.
- Adicionado lock advisory no startup PostgreSQL para evitar corrida de `db.create_all()` quando o Gunicorn inicia múltiplos workers.

### Documentação

- Criado `INSTALL.md` com instruções de instalação para Linux, Windows, setup web e observabilidade.
- Atualizado `.env.example` com variáveis de PostgreSQL, setup e instalação Docker.

### Validações realizadas

- Instalação real do Docker Engine e Docker Compose plugin em Debian 13.
- `docker run --rm hello-world`.
- `docker compose config --quiet`.
- Build da imagem da aplicação via `docker compose build app`.
- Teste real do instalador Linux em cópia temporária do projeto com:
  - porta web alternativa `5055`;
  - porta PostgreSQL alternativa `55433`;
  - geração automática de `.env`;
  - subida de `app` e `postgres`;
  - healthcheck `GET /health/ready`;
  - finalização do `/setup`;
  - criação e login do administrador inicial;
  - bloqueio do `/setup` após conclusão;
  - restart do container app;
  - validação de persistência das configurações no PostgreSQL.

## Ajuste de Upload de Background — 2026-05-20

- A imagem de fundo da tela de login em `Configurações > Aparência` passou de 1 MB para 8 MB.
- O frontend agora informa o limite correto e valida usando `AP_BG_MAX_BYTES`.
- O backend valida `bg_login` como PNG, JPG ou WEBP com limite real de 8 MB.
- O limite global de request Flask foi ajustado para 16 MB para comportar o aumento de tamanho causado pelo envio em base64.

## Correção do Botão Sair — 2026-05-20

- O botão `Sair` da barra lateral deixou de usar a variável `--sb-hover`.
- Criadas variáveis próprias `--sb-logout-bg` e `--sb-logout-hover`.
- A personalização de `Cor de Hover dos Itens do Menu` agora afeta apenas os itens de navegação, sem alterar visualmente o botão de logout.

## Ciclo de Vida de Ativos, Categorias e Manual do Sistema - 2026-05-19

### Entrada, patrimonio e categorias

- Adicionado suporte a fluxo mais completo de entrada de itens de TI, com separacao entre cadastro individual e entrada em lote.
- Entrada de ativos passou a usar categorias configuraveis em vez de depender apenas da lista fixa do frontend.
- Adicionado normalizador de configuracao para `categorias`, garantindo lista valida, sem nomes vazios e sem duplicidades.
- Criadas rotas administrativas para adicionar, remover e renomear categorias de ativos via configuracoes.
- Mantida a configuracao de tipo de alocacao por categoria, permitindo definir se o ativo deve ser alocado para colaborador ou unidade.
- Adicionado uso do prefixo de patrimonio configuravel no fluxo de cadastro, preservando a regra de que o patrimonio nasce na entrada do item.

### Alocacoes e perifericos

- Reforcada a validacao de perifericos na criacao de alocacao:
  - payload precisa ser lista valida;
  - itens invalidos sao rejeitados;
  - `supplyId` passa por limpeza;
  - quantidades sao normalizadas com minimo 1;
  - perifericos duplicados no payload sao consolidados antes da validacao de estoque;
  - a validacao passa a impedir baixa parcial quando o total solicitado excede o estoque disponivel.
- Movimentos de saida de perifericos em alocacao agora registram `ativo_id`, conectando o consumo de perifericos ao historico do ativo.
- `AllocationItem.to_dict()` agora retorna o `id` do item vinculado, permitindo operacoes precisas sobre perifericos especificos da alocacao.

### Troca de periferico com defeito

- Criado endpoint `POST /api/allocations/<aid>/perifericos/<item_id>/troca`.
- A troca exige alocacao ativa e periferico previamente vinculado.
- A quantidade de troca nao pode exceder a quantidade vinculada ao termo/alocacao.
- O periferico substituto precisa existir e ter estoque suficiente.
- O item defeituoso e registrado no historico como movimento `DEFEITO`, sem retornar ao estoque disponivel.
- O substituto recebe movimento de `SAIDA`, baixando o estoque e mantendo rastreabilidade.
- Quando o substituto e de outro tipo/modelo, o vinculo da alocacao e atualizado para refletir o novo periferico.
- Quando ja existe o mesmo substituto vinculado a alocacao, a quantidade e consolidada.
- O historico do ativo passa a reconhecer eventos `DEFEITO` e `TROCA_PERIFERICO`.

### Interface e usabilidade

- Adicionado botao `Trocar` na visualizacao do termo para perifericos vinculados a alocacoes ativas.
- Criado modal de troca com item atual, quantidade, motivo, periferico substituto, observacao e acao de confirmacao.
- A tela informa que o item defeituoso sera registrado no historico e que o substituto saira do estoque.
- O botao de confirmar troca e desabilitado quando nao ha periferico cadastrado para substituicao.
- A lista de categorias em `Entrada de Itens` e `Ativos de TI` passa a respeitar as categorias cadastradas nas configuracoes.
- A tela de configuracoes ganhou gerenciamento visual de categorias, com adicionar, renomear, remover e definir tipo de alocacao.

### Documentacao

- Criado o arquivo `MANUAL_DO_SISTEMA.md` com manual operacional do TI Control.
- O manual cobre acesso, perfis, modulos, entrada de ativos, patrimonio, estoque, alocacao, termos digitais, troca de periferico, devolucao, manutencao, QR Code, auditoria, licencas, colaboradores, anexos, configuracoes, backup, seguranca e boas praticas.
- Incluidos fluxos resumidos para entrada/alocacao, troca de periferico com defeito e devolucao.

### Validacoes realizadas

- `py -m py_compile app.py routes/allocations.py routes/assets.py`
- `git diff --check`
- `git diff --check -- MANUAL_DO_SISTEMA.md`
- Revisao estatica do diff de `app.py`, `routes/allocations.py`, `routes/assets.py`, `routes/settings.py` e `templates/index.html`.

### Pendencia conhecida de validacao

- O teste funcional via Flask test client nao foi concluido nesta sessao porque o ambiente bloqueou a execucao direta do Python pelo launcher com erro `Acesso negado`.
- A validacao sintatica passou, mas recomenda-se executar um teste runtime completo antes de publicar:
  - criar alocacao com periferico;
  - registrar troca por defeito;
  - confirmar baixa do substituto no estoque;
  - confirmar evento `DEFEITO` no historico do ativo;
  - confirmar que alocacao encerrada rejeita troca.
