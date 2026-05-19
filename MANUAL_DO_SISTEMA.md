# Manual do Sistema TI Control

## 1. Visao Geral

O TI Control e um sistema web para gestao de ativos de TI, colaboradores, insumos, perifericos, alocacoes, termos digitais, devolucoes, manutencoes, auditorias, licencas, QR Codes, etiquetas, backups e configuracoes administrativas.

O objetivo principal e manter rastreabilidade completa do ciclo de vida dos itens de TI, desde a entrada no estoque ate alocacao, troca, manutencao, devolucao, baixa ou descarte.

## 2. Acesso ao Sistema

1. Abra o endereco da aplicacao no navegador.
2. Informe usuario e senha.
3. Apos o login, o sistema exibira o painel principal com os modulos liberados para o seu perfil.

Usuarios iniciais de demonstracao, quando habilitados:

| Perfil | Usuario | Senha |
|---|---|---|
| Administrador | `admin.ti` | `admin123` |
| Tecnico TI | `marcos.souza` | `tecnico123` |
| Gestor | `roberto.faria` | `gestor123` |
| Visualizador | `viewer` | `viewer123` |

Em producao, altere as senhas iniciais e desative a exibicao de credenciais de demonstracao.

## 3. Perfis e Permissoes

| Perfil | Uso recomendado |
|---|---|
| Administrador | Configuracao do sistema, usuarios, backups, exportacoes, cadastros e operacoes completas. |
| Tecnico TI | Operacao diaria de ativos, alocacoes, manutencoes, insumos, QR Code e auditorias. |
| Gestor | Consulta, acompanhamento, relatorios e exportacoes autorizadas. |
| Visualizador | Consulta restrita, sem alteracoes operacionais. |

As permissoes podem ser ajustadas em `Configuracoes > Usuarios/Perfis`, conforme a politica interna da empresa.

## 4. Menu Principal

O menu lateral organiza os principais modulos:

| Modulo | Finalidade |
|---|---|
| Dashboard | Indicadores gerais, alertas e movimentos recentes. |
| Central de Alertas | Itens que exigem atencao, como garantia vencendo, estoque baixo e pendencias. |
| Insumos & Perifericos | Controle de estoque de perifericos e materiais de TI. |
| Entrada de Itens | Entrada individual ou em lote de ativos e itens de estoque. |
| Ativos de TI | Cadastro, edicao, consulta, historico e anexos dos equipamentos. |
| Alocacoes & Termos Digitais | Entrega de equipamentos, termos, assinaturas e troca de perifericos. |
| QR Code & Etiquetas | Geracao de QR Codes e etiquetas patrimoniais. |
| Auditorias | Campanhas de conferencia fisica e auditoria via QR Code. |
| Manutencao de Ativos | Ordens de manutencao, pecas, anexos e encerramento. |
| Licencas | Controle de licencas de software, vencimentos e saldo. |
| Colaboradores | Cadastro, reativacao, desligamento e offboarding. |
| Usuarios do Sistema | Cadastro, bloqueio, reset de senha e permissoes. |
| Configuracoes | Empresa, categorias, regras, e-mail, aparencia e backup. |

## 5. Fluxo de Entrada de Ativos

A entrada de ativos registra oficialmente equipamentos recebidos pela TI.

### 5.1 Entrada individual

Use quando apenas um equipamento sera cadastrado.

Campos comuns:

- Categoria ou tipo do item.
- Fabricante.
- Modelo.
- Hostname.
- IP, MAC ou Service Tag, quando aplicavel.
- Nota fiscal.
- Patrimonio.
- Garantia.
- Status.
- Colaborador ou unidade, quando aplicavel.

Regra importante: o patrimonio deve ser gerado ou informado na entrada do item, nao na saida.

### 5.2 Entrada em lote

Use quando varios equipamentos semelhantes serao cadastrados de uma vez.

O sistema deve gerar patrimonio individual para cada equipamento, mantendo controle separado por serie, garantia, historico, colaborador e manutencoes.

Exemplo:

| Item | Patrimonio |
|---|---|
| Notebook 01 | TI-000101 |
| Notebook 02 | TI-000102 |
| Notebook 03 | TI-000103 |

Mesmo quando entram em lote, os itens passam a ser tratados individualmente.

## 6. Patrimonio

O patrimonio e o identificador principal do equipamento dentro da empresa.

Regras:

- Deve ser unico.
- Deve nascer na entrada do item.
- Nao deve ser recriado na alocacao.
- Deve acompanhar o ativo em QR Code, etiqueta, termo, historico e auditoria.
- Pode usar prefixo configuravel, como `TI`.

Para configurar o prefixo, acesse `Configuracoes > Regras/Patrimonio`, conforme a tela disponivel na versao instalada.

## 7. Cadastro e Consulta de Ativos

No modulo `Ativos de TI`, e possivel:

- Cadastrar ativo.
- Editar dados tecnicos.
- Consultar por nome, patrimonio, colaborador, setor ou unidade.
- Anexar documentos, notas fiscais, fotos e comprovantes.
- Ver historico completo.
- Baixar ou excluir, conforme permissao.
- Gerar QR Code do ativo.

Status comuns:

| Status | Significado |
|---|---|
| Disponivel | Item pronto para alocacao. |
| Alocado | Item entregue a colaborador ou unidade. |
| Manutencao | Item em reparo ou analise tecnica. |
| Baixado | Item retirado do ciclo operacional, com historico preservado. |

## 8. Insumos e Perifericos

Use `Insumos & Perifericos` para controlar itens de estoque que podem ser entregues junto com ativos, como:

- Mouse.
- Teclado.
- Headset.
- Cabo.
- Fonte.
- Adaptador.
- Mochila.
- Outros acessorios.

Operacoes disponiveis:

- Cadastro do item.
- Entrada de estoque.
- Saida manual.
- Devolucao.
- Uso em kit de admissao.
- Vinculo em alocacoes.
- Troca por defeito quando o periferico estiver vinculado a uma alocacao ativa.

Boas praticas:

- Nunca use quantidade negativa.
- Cadastre estoque minimo para alertas.
- Use nomes padronizados, por exemplo `Mouse USB Logitech M90`.
- Registre motivo nas saidas e devolucoes.

## 9. Alocacao de Ativos

A alocacao e a saida do ativo do estoque para um colaborador ou unidade.

Fluxo recomendado:

1. Acesse `Alocacoes & Termos Digitais`.
2. Clique para criar nova alocacao.
3. Selecione o ativo disponivel.
4. Selecione o colaborador responsavel.
5. Confira setor, unidade e e-mail.
6. Adicione perifericos, se houver.
7. Informe motivo da entrega.
8. Confirme.

Ao confirmar, o sistema:

- Altera o status do ativo para `Alocado`.
- Vincula o ativo ao colaborador.
- Baixa os perifericos do estoque.
- Gera o termo de responsabilidade.
- Registra a movimentacao no historico.

## 10. Termo de Responsabilidade

O termo documenta a entrega do equipamento ao colaborador.

Ele pode conter:

- Dados da empresa.
- Dados do colaborador.
- Dados do ativo.
- Patrimonio.
- Perifericos vinculados.
- Data da entrega.
- Responsabilidades de uso.
- Assinatura do colaborador.
- Assinatura do responsavel de TI.
- Codigo do termo.
- QR Code ou link de assinatura.

Operacoes disponiveis:

- Baixar PDF.
- Marcar como assinado.
- Gerar link de assinatura digital.
- Assinar como responsavel de TI.
- Visualizar assinaturas registradas.

## 11. Troca de Periferico com Defeito

Quando um periferico entregue ao colaborador apresentar defeito, use a funcao de troca.

Fluxo:

1. Acesse `Alocacoes & Termos Digitais`.
2. Abra o termo da alocacao ativa.
3. Localize o periferico vinculado.
4. Clique em `Trocar`.
5. Informe a quantidade.
6. Informe o motivo, como `Defeito`, `Dano fisico` ou `Mau funcionamento`.
7. Escolha o periferico substituto.
8. Registre uma observacao, se necessario.
9. Confirme em `Registrar Troca`.

O sistema:

- Registra o item antigo como defeituoso.
- Nao devolve o item defeituoso ao estoque disponivel.
- Baixa o periferico substituto do estoque.
- Atualiza o vinculo da alocacao.
- Registra os eventos no historico do ativo.

Essa operacao deve ser usada quando o item continua com o colaborador, mas um acessorio precisa ser substituido.

## 12. Devolucao e Offboarding

O fluxo de devolucao e usado quando o colaborador devolve ativos e perifericos.

Usos comuns:

- Desligamento.
- Troca de equipamento.
- Mudanca de funcao.
- Fim de emprestimo.
- Retorno ao estoque.

No modulo `Colaboradores`, o offboarding pode gerar uma devolucao com lista de itens vinculados. O sistema permite termo de devolucao, assinatura e laudo tecnico.

Ao concluir a devolucao:

- O ativo pode voltar ao estoque, ir para manutencao ou ser baixado.
- Os perifericos devolvidos podem retornar ao estoque conforme avaliacao.
- O historico do ativo e atualizado.

## 13. Manutencao de Ativos

Use `Manutencao de Ativos` para abrir e acompanhar ordens de servico.

Fluxo basico:

1. Selecione o ativo.
2. Informe tipo de manutencao.
3. Descreva o defeito ou necessidade.
4. Atribua tecnico responsavel.
5. Anexe evidencias, fotos ou orcamentos.
6. Registre pecas utilizadas, quando houver.
7. Encerre a OS com resultado e custo.

Resultados comuns:

- Concluida.
- Sem reparo.
- Aguardando peca.
- Encaminhada a fornecedor.

## 14. QR Code e Etiquetas

O modulo `QR Code & Etiquetas` permite gerar identificacao fisica para os ativos.

Recursos:

- QR Code individual por ativo.
- Link publico do ativo.
- Confirmacao de localizacao via QR Code.
- Etiquetas customizaveis.
- Opcao de exibir logo da empresa.
- Impressao em lote ou por quantidade de copias.

Boas praticas:

- Cole a etiqueta em local visivel e seguro.
- Use patrimonio e QR Code juntos.
- Configure `APP_BASE_URL` corretamente antes de imprimir etiquetas em producao.

## 15. Auditorias

As auditorias servem para conferir se os ativos estao fisicamente no local esperado.

Tipos de uso:

- Campanhas de auditoria.
- Conferencia por unidade.
- Confirmacao via QR Code.
- Registro de localizacao informada.

O historico do ativo recebe os eventos de auditoria, ajudando a rastrear movimentacoes e divergencias.

## 16. Licencas

O modulo `Licencas` controla softwares, contratos e vencimentos.

Campos comuns:

- Software.
- Fornecedor.
- Total de licencas.
- Licencas atribuidas.
- Vencimento.
- Custo.
- Tipo.
- Anexos.

O sistema calcula saldo e situacao, ajudando a identificar licencas vencidas, excedidas ou regulares.

## 17. Colaboradores

O modulo `Colaboradores` permite:

- Cadastrar colaborador.
- Editar dados.
- Consultar ativos e perifericos vinculados.
- Separar ativos de desligados/inativos.
- Reativar colaborador.
- Iniciar offboarding.
- Gerar termo de devolucao.

Dados recomendados:

- Nome completo.
- CPF ou matricula.
- E-mail corporativo.
- Cargo.
- Setor.
- Unidade.
- Gestor.
- Status.

## 18. Anexos

O sistema permite anexar documentos a ativos, licencas e manutencoes.

Exemplos:

- Nota fiscal.
- Contrato.
- Foto.
- Laudo.
- Orcamento.
- Comprovante.

Boas praticas:

- Use nomes de arquivo claros.
- Informe descricao.
- Evite anexar documentos desnecessarios ou sensiveis.
- Respeite as permissoes de acesso.

## 19. Configuracoes

Em `Configuracoes`, o administrador pode ajustar:

- Dados da empresa.
- Logo.
- Setores.
- Unidades.
- Categorias de ativos.
- Tipo de alocacao por categoria.
- Regras de alocacao.
- Campos obrigatorios de ativos.
- Prefixo de patrimonio.
- Aparencia.
- Tela de login.
- SMTP e templates de e-mail.
- Backup.
- Permissoes por perfil.

Altere configuracoes com cuidado, pois elas podem afetar validacoes e fluxos operacionais.

## 20. Backup e Exportacoes

Recursos disponiveis:

- Backup JSON dos principais dados.
- Backup automatico configuravel.
- Retencao de arquivos.
- Download de backups.
- Exclusao de backups antigos.
- Exportacao CSV de ativos.
- Exportacao CSV de colaboradores.
- Exportacao CSV de alocacoes.

Recomendacoes:

- Gere backup antes de alteracoes grandes.
- Teste restauracao periodicamente.
- Armazene copia fora do servidor.
- Restrinja acesso a backups apenas a administradores.

## 21. Alertas e Dashboard

O dashboard apresenta uma visao rapida da operacao.

Indicadores comuns:

- Total de ativos.
- Ativos alocados.
- Ativos disponiveis.
- Estoque baixo.
- Garantias vencendo.
- Licencas vencendo.
- Pendencias de assinatura.
- Movimentos recentes.

A Central de Alertas deve ser acompanhada periodicamente pela equipe de TI.

## 22. Historico do Ativo

Cada ativo possui uma linha do tempo com eventos como:

- Criacao.
- Edicao.
- Alocacao.
- Assinatura de termo.
- Troca de periferico.
- Defeito.
- Manutencao.
- Uso de pecas.
- Incidente.
- Auditoria.
- Devolucao.
- Baixa.

Esse historico e a principal fonte de rastreabilidade do ciclo de vida do equipamento.

## 23. Regras de Seguranca Operacional

Recomendacoes:

- Use senhas fortes.
- Remova usuarios que nao precisam mais acessar.
- Revise perfis periodicamente.
- Nao compartilhe usuario e senha.
- Use HTTPS em producao.
- Configure `SECRET_KEY` forte.
- Desative credenciais de demonstracao.
- Restrinja backups e exportacoes.
- Proteja o endpoint de metricas na rede interna.
- Evite expor dados internos em links publicos.

## 24. Boas Praticas de Uso

- Cadastre o ativo assim que ele chegar.
- Gere ou confira o patrimonio antes da entrega.
- Use QR Code e etiqueta fisica.
- Mantenha colaborador, setor e unidade atualizados.
- Registre perifericos entregues junto ao termo.
- Exija assinatura do termo.
- Registre manutencoes e incidentes no sistema.
- Use devolucao/offboarding quando o colaborador sair.
- Nao ajuste estoque manualmente para corrigir erro sem registrar motivo.
- Use backup antes de importacoes, limpezas ou mudancas administrativas.

## 25. Fluxos Resumidos

### Entrada e alocacao

```text
Entrada do item
  -> Cadastro individual ou em lote
  -> Geracao/registro do patrimonio
  -> Status Disponivel
  -> Alocacao para colaborador ou unidade
  -> Geracao do termo
  -> Assinatura
  -> Historico atualizado
```

### Troca de periferico com defeito

```text
Periferico com defeito
  -> Abrir termo da alocacao
  -> Clicar em Trocar
  -> Selecionar substituto
  -> Registrar motivo
  -> Defeito entra no historico
  -> Substituto sai do estoque
  -> Vinculo da alocacao atualizado
```

### Devolucao

```text
Colaborador devolve equipamento
  -> Registrar devolucao/offboarding
  -> Gerar termo de devolucao
  -> Assinar
  -> Avaliar estado fisico
  -> Retornar ao estoque, manutencao ou baixa
  -> Historico atualizado
```

## 26. Suporte e Manutencao

Em caso de problema:

1. Verifique se o usuario tem permissao para a acao.
2. Confira se os campos obrigatorios foram preenchidos.
3. Consulte a Central de Alertas.
4. Consulte o historico do ativo.
5. Verifique o estoque antes de alocar ou trocar perifericos.
6. Gere backup antes de qualquer correcao manual.
7. Consulte os logs da aplicacao ou os endpoints de saude, quando disponiveis.

Endpoints uteis para operacao tecnica:

| Endpoint | Uso |
|---|---|
| `/ping` | Teste simples de disponibilidade. |
| `/health/live` | Liveness check. |
| `/health/ready` | Readiness com banco. |
| `/health/startup` | Startup check. |
| `/metrics` | Metricas para Prometheus, quando habilitado. |

