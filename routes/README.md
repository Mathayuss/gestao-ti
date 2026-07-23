# Organizacao das rotas

As rotas Flask foram separadas por dominio para reduzir o tamanho do `app.py`
e facilitar a leitura do codigo.

- `auth.py`: login, logout, usuario atual, health checks e metricas.
- `assets.py`: tela inicial, perfil publico, ativos, QR Code e auditoria de ativo.
- `supplies.py`: insumos, estoque, entradas, saidas, devolucoes e kit de admissao.
- `colaboradores.py`: colaboradores, offboarding, perifericos e termos de devolucao.
- `allocations.py`: alocacoes, termos, assinaturas e links publicos de assinatura.
- `operations.py`: licencas, incidentes e manutencoes.
- `users.py`: usuarios do sistema e perfis.
- `settings.py`: configuracoes, e-mail, templates, backup e termos.
- `devolucoes.py`: devolucoes, laudo tecnico, ciencia do RH e assinatura de devolucao.
- `reports.py`: dashboard, alertas, auditoria, movimentos, exportacoes e backups.

Os modulos usam o Blueprint compartilhado `routes.blueprint.bp`, registrado sem
prefixo de endpoint para preservar compatibilidade com `url_for`, templates e
links publicos existentes. Todos os modulos de rota agora usam imports
explicitos de modelos, extensoes, helpers e services, sem ponte global a partir
do `app.py`.

O proximo passo natural e mover esses itens para pacotes dedicados, por exemplo:

- `models/`: classes SQLAlchemy.
- `services/`: regras de negocio, autorizacao/RBAC, backup, ativos, anexos, validacoes, e-mail, configuracoes e renderizacao de templates.
- `extensions.py`: `db`, `lm`, migrate e integracoes Flask.
- `config.py`: leitura e normalizacao de variaveis de ambiente, versao, cookies e parametros de banco.
