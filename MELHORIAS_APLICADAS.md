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
