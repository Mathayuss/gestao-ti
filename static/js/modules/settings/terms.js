function isTermAvulsoKind(kind){
  return String(kind||'').startsWith('ta:');
}
function termAvulsoTipoFromKind(kind){
  if(!isTermAvulsoKind(kind)) return '';
  try{ return decodeURIComponent(String(kind).slice(3)); }
  catch(e){ return String(kind).slice(3); }
}
function termAvulsoKind(tipo){
  return `ta:${encodeURIComponent(String(tipo||''))}`;
}
function defaultTermoAvulsoModelo(tipo){
  return {
    titulo:`TERMO DE ${String(tipo||'TERMO').toUpperCase()}`,
    preambulo:`Eu, {colaborador}, do setor {setor}, unidade {unidade}, declaro estar ciente e de acordo com as regras referentes a {tipo}, com validade até {validade}.`,
    clausulas:[
      'O recurso, acesso ou obrigação descrito neste termo é pessoal e intransferível.',
      'O uso deve respeitar as políticas internas, normas de segurança da informação e orientações da área de TI.',
      'O descumprimento das regras poderá resultar em revogação do acesso e medidas administrativas cabíveis.',
    ],
    rodape:'{empresa} — Termo {tipo} emitido em {data} pelo Sistema de Gestão de TI',
  };
}
function getTermoAvulsoModelo(tipo){
  return {...defaultTermoAvulsoModelo(tipo), ...((_termoAvulsoModelos||{})[tipo]||{})};
}

function termPreviewCtx(){
  const tipoAvulso = _activeTermAvulsoTipo || 'VPN';
  return {
    colaborador:'Ana Costa',
    setor:'Financeiro',
    unidade:'Sede',
    ativo:'Notebook Dell Latitude 5440 · Patrimônio TI-000123',
    data:fmtDate(new Date().toISOString().slice(0,10)),
    empresa:_settings?.empresa?.nome||'Empresa',
    termo:'TERMO-EXEMPLO',
    tipo:tipoAvulso,
    validade:'31/12/2026',
    dataDevolucao:'31/12/2026'
  };
}
function renderTermTextPreview(text, ctx){
  return esc(String(text||'').replace(/\{(\w+)\}/g, (_,k)=>ctx[k] ? `{${k}}`)).replace(/\n/g,'<br>');
}
function termPreviewFields(kind, ctx){
  if(kind==='td') return [['Colaborador',ctx.colaborador],['Setor / Unidade',`${ctx.setor} / ${ctx.unidade}`],['Itens','Notebook Dell Latitude 5440; Mouse sem fio Logitech']];
  if(isTermAvulsoKind(kind)) return [['Colaborador',ctx.colaborador],['Setor / Unidade',`${ctx.setor} / ${ctx.unidade}`],['Tipo',ctx.tipo],['Validade',ctx.validade]];
  if(kind==='te') return [['Colaborador',ctx.colaborador],['Ativo',ctx.ativo],['Devolução prevista',ctx.dataDevolucao]];
  return [['Colaborador',ctx.colaborador],['Ativo',ctx.ativo],['Termo',ctx.termo]];
}
function termPreviewPayload(kind){
  if(isTermAvulsoKind(kind)){
    return {
      titulo: $('ta-titulo')?.value || '',
      preambulo: $('ta-preambulo')?.value || '',
      clausulas: ($('ta-clausulas')?.value || '').split('\n').map(s=>s.trim()).filter(Boolean),
      declaracao: '',
      rodape: $('ta-rodape')?.value || ''
    };
  }
  const p = {
    tr:{titulo:'tr-titulo',preambulo:'tr-preambulo',clausulas:'tr-clausulas',rodape:'tr-rodape'},
    td:{titulo:'td-titulo',preambulo:'td-preambulo',clausulas:'td-clausulas',rodape:'td-rodape',declaracao:'td-declaracao'},
    te:{titulo:'te-titulo',preambulo:'te-preambulo',clausulas:'te-clausulas',rodape:'te-rodape'},
  }[kind] || {};
  return {
    titulo: $(p.titulo)?.value || '',
    preambulo: $(p.preambulo)?.value || '',
    clausulas: ($(p.clausulas)?.value || '').split('\n').map(s=>s.trim()).filter(Boolean),
    declaracao: p.declaracao ? ($(p.declaracao)?.value || '') : '',
    rodape: $(p.rodape)?.value || ''
  };
}
function termKindTitle(kind){
  if(isTermAvulsoKind(kind)) return `Termo ${termAvulsoTipoFromKind(kind) || 'Personalizado'}`;
  return ({
    tr:'Termo de Recebimento',
    td:'Termo de Devolução',
    te:'Termo de Empréstimo',
  })[kind] || 'Termo';
}
function termKindSub(kind){
  if(isTermAvulsoKind(kind)) return 'Modelo personalizado com texto próprio e independente dos demais termos.';
  return ({
    tr:'Modelo usado na entrega de equipamentos ao colaborador.',
    td:'Modelo usado na devolução e conferência de equipamentos.',
    te:'Modelo usado para empréstimos com devolução prevista.',
  })[kind] || 'Modelo de termo';
}
function termPreviewHtml(kind){
  kind = kind || $('term-preview-kind')?.value || 'tr';
  const ctx = termPreviewCtx();
  const p = termPreviewPayload(kind);
  const fields = termPreviewFields(kind, ctx).map(([k,v])=>`
    <div style="display:grid;grid-template-columns:95px 1fr;gap:8px;border-bottom:1px solid #e5e7eb;padding:5px 0">
      <strong>${esc(k)}</strong><span>${renderTermTextPreview(v,ctx)}</span>
    </div>`).join('');
  const clauses = p.clausulas.length
    ? p.clausulas.slice(0,3).map(cl=>`<p style="margin:0 0 7px">${renderTermTextPreview(cl,ctx)}</p>`).join('') + (p.clausulas.length>3?`<p style="margin:0;color:#64748b">+ ${p.clausulas.length-3} cláusula(s) no PDF final.</p>`:'')
    : '<p style="margin:0;color:#64748b">Sem cláusulas cadastradas.</p>';
  return `
    <div class="term-preview-modal">
      <div class="term-preview-doc">
        <div style="text-align:center;font-weight:800;font-size:13px;margin-bottom:4px">${renderTermTextPreview(p.titulo,ctx)}</div>
        <div style="text-align:center;color:#64748b;font-size:10px;margin-bottom:10px">${esc(ctx.termo)} · ${esc(ctx.data)}</div>
        <div style="margin-bottom:10px">${renderTermTextPreview(p.preambulo,ctx)}</div>
        <div style="margin:8px 0 12px">${fields}</div>
        <div>${clauses}</div>
        ${p.declaracao?`<div style="font-weight:700;margin-top:10px">${renderTermTextPreview(p.declaracao,ctx)}</div>`:''}
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:22px;margin-top:30px;text-align:center;font-size:10px">
          <div style="border-top:1px solid #111827;padding-top:5px">${esc(ctx.colaborador)}</div>
          <div style="border-top:1px solid #111827;padding-top:5px">Responsável TI</div>
        </div>
        ${p.rodape?`<div style="text-align:center;color:#64748b;font-size:9px;margin-top:16px">${renderTermTextPreview(p.rodape,ctx)}</div>`:''}
      </div>
      <div class="term-preview-fields">
        <div style="font-weight:700;color:var(--text);margin-bottom:6px">Campos exibidos nesta prévia</div>
        ${termPreviewFields(kind, ctx).map(([k,v])=>`<div style="padding:5px 0;border-bottom:1px solid var(--border)"><strong>${esc(k)}:</strong> ${renderTermTextPreview(v,ctx)}</div>`).join('')}
      </div>
    </div>`;
}
function renderTermPreview(kind){
  const box = $('term-preview-box');
  if(box) box.innerHTML = termPreviewHtml(kind);
}
function setActiveTermConfig(kind){
  kind = kind || 'tr';
  const isAvulso = isTermAvulsoKind(kind);
  const cardKind = isAvulso ? 'ta' : kind;
  const tipoAvulso = termAvulsoTipoFromKind(kind);
  if(isAvulso){
    _activeTermAvulsoTipo = tipoAvulso;
    const model = getTermoAvulsoModelo(tipoAvulso);
    if($('ta-editor-label')) $('ta-editor-label').textContent = `Termo ${tipoAvulso}`;
    if($('ta-titulo')) $('ta-titulo').value = model.titulo || '';
    if($('ta-preambulo')) $('ta-preambulo').value = model.preambulo || '';
    if($('ta-clausulas')) $('ta-clausulas').value = (model.clausulas || []).join('\n');
    if($('ta-rodape')) $('ta-rodape').value = model.rodape || '';
  }
  if($('term-preview-kind')) $('term-preview-kind').value = kind;
  document.querySelectorAll('.term-config-card').forEach(card=>{
    card.style.display = card.dataset.termKind === cardKind ? '' : 'none';
  });
  document.querySelectorAll('.term-template-card[data-term-kind]').forEach(card=>{
    card.classList.toggle('active', card.dataset.termKind === kind);
  });
  if($('term-editor-title')) $('term-editor-title').textContent = termKindTitle(kind);
  if($('term-editor-sub')) $('term-editor-sub').textContent = termKindSub(kind);
  renderTermTiposConfig();
}
function selectTermConfig(kind){
  setActiveTermConfig(kind);
}
function openTermEditor(kind, scroll=true){
  setActiveTermConfig(kind);
  const manager = $('terms-manager');
  const shell = $('term-editor-shell');
  if(manager) manager.classList.add('is-hidden');
  if(shell) shell.classList.add('is-open');
  if(scroll && shell) shell.scrollIntoView({behavior:'smooth',block:'start'});
}
function closeTermEditor(scroll=true){
  const manager = $('terms-manager');
  const shell = $('term-editor-shell');
  if(shell) shell.classList.remove('is-open');
  if(manager) manager.classList.remove('is-hidden');
  if(scroll && manager) manager.scrollIntoView({behavior:'smooth',block:'start'});
}
function initTermsPanel(){
  setActiveTermConfig($('term-preview-kind')?.value || 'tr');
  closeTermEditor(false);
}
function editTermConfig(kind){
  openTermEditor(kind);
}
function previewTermConfig(kind){
  setActiveTermConfig(kind);
  openModal(`Prévia — ${termKindTitle(kind)}`, `
    ${termPreviewHtml(kind)}
    <div class="modal-footer">
      <button class="btn btn-default" onclick="closeModal()">Fechar</button>
      <button class="btn btn-primary" onclick="closeModal();openTermEditor('${kind}')">${inlineIcon('edit')} Editar modelo</button>
    </div>`, true);
}
function loadTermExample(kind){
  openTermEditor(kind);
  if(kind === 'tr'){ carregarExemploTR(); return; }
  if(kind === 'td'){ carregarExemploTD(); return; }
  if(kind === 'te'){
    if(!confirm('Isso substituirá o conteúdo atual pelo modelo de exemplo. Deseja continuar?')) return;
    $('te-titulo').value = 'TERMO DE EMPRÉSTIMO DE EQUIPAMENTO';
    $('te-preambulo').value = 'Eu, {colaborador}, do setor {setor}, unidade {unidade}, recebo em caráter temporário o equipamento abaixo, comprometendo-me a devolvê-lo até {dataDevolucao}.';
    $('te-clausulas').value = [
      'O equipamento deve ser utilizado exclusivamente para atividades profissionais autorizadas.',
      'O colaborador se responsabiliza pela guarda, conservação e devolução no prazo acordado.',
      'Qualquer dano, perda ou roubo deve ser comunicado imediatamente ao departamento de TI.',
    ].join('\n');
    $('te-rodape').value = '{empresa} — Termo emitido em {data} pelo Sistema de Gestão de TI';
    toast('Modelo de exemplo carregado — edite conforme necessário e salve.');
    renderTermPreview('te');
    return;
  }
  if(isTermAvulsoKind(kind)){
    const tipo = termAvulsoTipoFromKind(kind) || 'Termo';
    if(!confirm('Isso substituirá o conteúdo atual pelo modelo de exemplo. Deseja continuar?')) return;
    $('ta-titulo').value = `TERMO DE ${tipo.toUpperCase()}`;
    $('ta-preambulo').value = 'Eu, {colaborador}, do setor {setor}, unidade {unidade}, declaro estar ciente e de acordo com as regras referentes a {tipo}, com validade até {validade}.';
    $('ta-clausulas').value = [
      `Este termo de ${tipo} é pessoal, intransferível e aplicável somente à finalidade autorizada.`,
      'É proibido compartilhar acessos, informações, documentos, credenciais ou recursos corporativos com terceiros.',
      'O descumprimento das regras poderá resultar em revogação do acesso e medidas administrativas cabíveis.',
    ].join('\n');
    $('ta-rodape').value = '{empresa} — Termo {tipo} emitido em {data} pelo Sistema de Gestão de TI';
    toast('Modelo de exemplo carregado — edite conforme necessário e salve.');
    renderTermPreview(kind);
  }
}
function renderTermTiposConfig(){
  const el = $('termos-tipos-list');
  if(!el) return;
  const tipos = _settings.termos_avulsos_tipos || _termoAvulsoTipos || [];
  el.innerHTML = tipos.length
    ? `<div class="term-type-list">${tipos.map(t=>`
        <div class="term-type-row">
          <div style="min-width:0">
            <div class="term-type-name" title="${escAttr(t)}">${esc(t)}</div>
            <div style="font-size:11px;color:var(--text3)">Modelo personalizado</div>
          </div>
          <button class="btn btn-danger btn-sm btn-icon" type="button" title="Remover modelo" onclick="removeTipoTermoConfig(${jsArg(t)})">${svgIcon('trash')}</button>
        </div>`).join('')}</div>`
    : '<div style="font-size:12px;color:var(--text3)">Nenhum modelo configurado.</div>';
}
async function saveTermTiposConfig(tipos){
  tipos = Array.from(new Set((tipos||[]).map(t=>String(t||'').trim()).filter(Boolean))).slice(0,80);
  if(!tipos.length){ toast('Mantenha pelo menos um modelo de termo','error'); return false; }
  const modelos = {};
  tipos.forEach(tipo=>{
    modelos[tipo] = _termoAvulsoModelos[tipo] || defaultTermoAvulsoModelo(tipo);
  });
  const cfg = await api('/settings','PUT',{termos_avulsos_tipos:tipos, termos_avulsos_modelos:modelos});
  _settings.termos_avulsos_tipos = cfg?.termos_avulsos_tipos || tipos;
  _settings.termos_avulsos_modelos = cfg?.termos_avulsos_modelos || modelos;
  _termoAvulsoTipos = [..._settings.termos_avulsos_tipos];
  _termoAvulsoModelos = {..._settings.termos_avulsos_modelos};
  renderTermTiposConfig();
  toast('Modelos de termos atualizados');
  return true;
}
async function addTipoTermoConfig(){
  openModal('Novo Modelo de Termo',`
    <div class="form-group">
      <label>Nome do termo</label>
      <input id="novo-tipo-termo" placeholder="Ex: Uso de Equipamento Particular" onkeydown="if(event.key==='Enter')saveNovoTipoTermoConfig()">
    </div>
    <div class="info-box blue" style="font-size:12px">O novo termo será criado como um card próprio e terá template independente para edição.</div>
    <div class="modal-footer">
      <button class="btn btn-default" onclick="closeModal()">Cancelar</button>
      <button class="btn btn-primary" onclick="saveNovoTipoTermoConfig()">Criar modelo</button>
    </div>`);
  setTimeout(()=>$('novo-tipo-termo')?.focus(), 60);
}
async function saveNovoTipoTermoConfig(){
  const tipo = ($('novo-tipo-termo')?.value||'').trim();
  if(!tipo) return;
  if(tipo.length > 60){ toast('Use no máximo 60 caracteres','error'); return; }
  const tipos = _settings.termos_avulsos_tipos || _termoAvulsoTipos || [];
  if(tipos.some(t=>t.toLowerCase()===tipo.toLowerCase())){ toast('Tipo já cadastrado','warning'); return; }
  _termoAvulsoModelos[tipo] = defaultTermoAvulsoModelo(tipo);
  const ok = await saveTermTiposConfig([...tipos, tipo]);
  if(ok){
    closeModal();
    await renderConfiguracoes();
    cfgTab('termos');
    setTimeout(()=>editTermConfig(termAvulsoKind(tipo)), 80);
  }
}
async function removeTipoTermoConfig(tipo){
  if(!confirm(`Remover o modelo "${tipo}"? O histórico de termos já criados será mantido, mas o modelo deixará de aparecer nas novas configurações.`)) return;
  const tipos = (_settings.termos_avulsos_tipos || _termoAvulsoTipos || []).filter(t=>t!==tipo);
  delete _termoAvulsoModelos[tipo];
  const ok = await saveTermTiposConfig(tipos);
  if(ok){
    await renderConfiguracoes();
    cfgTab('termos');
  }
}

async function saveTermoRecebimento(){
  const clausulas = ($('tr-clausulas').value||'').split('\n').map(s=>s.trim()).filter(Boolean);
  await api('/settings/termos','PUT',{termo_recebimento:{
    titulo:    $('tr-titulo').value,
    preambulo: $('tr-preambulo').value,
    clausulas,
    rodape:    $('tr-rodape').value,
  }});
  toast('Termo de recebimento salvo');
}

async function saveTermoDevolucao(){
  const clausulas = ($('td-clausulas').value||'').split('\n').map(s=>s.trim()).filter(Boolean);
  await api('/settings/termos','PUT',{termo_devolucao:{
    titulo:      $('td-titulo').value,
    preambulo:   $('td-preambulo').value,
    clausulas,
    declaracao:  $('td-declaracao').value,
    rodape:      $('td-rodape').value,
  }});
  toast('Termo de devolução salvo');
}

function carregarExemploTR(){
  if(!confirm('Isso substituirá o conteúdo atual pelo modelo de exemplo. Deseja continuar?')) return;
  $('tr-titulo').value = 'TERMO DE RESPONSABILIDADE DE EQUIPAMENTO DE INFORMÁTICA';
  $('tr-preambulo').value =
    'Eu, {colaborador}, lotado(a) no setor de {setor}, unidade {unidade}, declaro ter recebido\n' +
    'em {data} os equipamentos de propriedade de {empresa} listados neste documento,\n' +
    'para uso exclusivo no exercício das minhas funções profissionais.';
  $('tr-clausulas').value = [
    'CLÁUSULA 1 — RESPONSABILIDADE: O(A) colaborador(a) se responsabiliza integralmente pela guarda, conservação e uso adequado dos equipamentos recebidos.',
    'CLÁUSULA 2 — USO EXCLUSIVO: Os equipamentos destinam-se exclusivamente ao desempenho das atividades profissionais, sendo expressamente vedado o uso pessoal, empréstimo ou cessão a terceiros.',
    'CLÁUSULA 3 — COMUNICAÇÃO DE OCORRÊNCIAS: Qualquer dano, defeito, perda ou furto deverá ser comunicado imediatamente ao departamento de TI, independentemente da causa.',
    'CLÁUSULA 4 — INSTALAÇÃO DE SOFTWARES: É vedada a instalação de programas, aplicativos ou extensões não homologados pela TI, bem como qualquer alteração nas configurações de hardware ou software sem autorização prévia.',
    'CLÁUSULA 5 — SIGILO E SEGURANÇA: O(A) colaborador(a) compromete-se a manter o sigilo das credenciais de acesso e das informações corporativas acessadas por meio dos equipamentos, em conformidade com a Política de Segurança da Informação da {empresa}.',
    'CLÁUSULA 6 — DEVOLUÇÃO OBRIGATÓRIA: Os equipamentos deverão ser devolvidos ao departamento de TI em plenas condições nas seguintes situações: (a) encerramento do contrato de trabalho; (b) transferência de cargo ou setor; (c) substituição do equipamento; (d) qualquer solicitação formal da empresa.',
    'CLÁUSULA 7 — PENALIDADES: O descumprimento das cláusulas acima poderá acarretar: desconto em folha de pagamento pelo valor de mercado do equipamento não devolvido ou danificado por uso indevido; e demais sanções disciplinares previstas no contrato de trabalho e na legislação vigente.',
  ].join('\n');
  $('tr-rodape').value = '{empresa} — Documento {termo} emitido em {data} pelo Sistema de Gestão de TI';
  toast('Modelo de exemplo carregado — edite conforme necessário e salve.');
  renderTermPreview('tr');
}

function carregarExemploTD(){
  if(!confirm('Isso substituirá o conteúdo atual pelo modelo de exemplo. Deseja continuar?')) return;
  $('td-titulo').value = 'TERMO DE DEVOLUÇÃO DE EQUIPAMENTOS DE TI';
  $('td-preambulo').value =
    'Pelo presente instrumento, o(a) colaborador(a) {colaborador}, do setor {setor},\n' +
    'unidade {unidade}, declara ter devolvido ao departamento de Tecnologia da Informação\n' +
    'de {empresa}, na data de {data}, os equipamentos abaixo relacionados:';
  $('td-clausulas').value = [
    'CLÁUSULA 1 — ESTADO DE CONSERVAÇÃO: O(A) colaborador(a) declara que os equipamentos são devolvidos em boas condições de funcionamento, salvo desgaste natural decorrente do uso regular.',
    'CLÁUSULA 2 — CONFERÊNCIA TÉCNICA: O departamento de TI realizará a conferência física e funcional dos equipamentos recebidos em até 5 (cinco) dias úteis após a data desta devolução.',
    'CLÁUSULA 3 — NOTIFICAÇÃO DE DIVERGÊNCIAS: Eventuais danos, peças faltantes ou acessórios não devolvidos identificados durante a conferência serão comunicados formalmente ao(à) colaborador(a) e ao setor de Recursos Humanos no prazo estabelecido na cláusula anterior.',
    'CLÁUSULA 4 — EXONERAÇÃO DE RESPONSABILIDADE: Após a conferência e ausência de divergências, o(a) colaborador(a) fica exonerado(a) de qualquer responsabilidade sobre os equipamentos listados neste termo.',
    'CLÁUSULA 5 — DADOS PESSOAIS: O(A) colaborador(a) declara estar ciente de que quaisquer dados pessoais armazenados nos dispositivos poderão ser apagados durante o processo de reintegração dos equipamentos ao inventário da empresa.',
  ].join('\n');
  $('td-declaracao').value =
    'Declaro ter devolvido todos os equipamentos listados acima ao departamento de TI de {empresa}, ' +
    'estando ciente de que divergências apuradas na conferência técnica poderão ensejar responsabilização nos termos da legislação vigente.';
  $('td-rodape').value = '{empresa} — Documento {termo} emitido em {data} pelo Sistema de Gestão de TI';
  toast('Modelo de exemplo carregado — edite conforme necessário e salve.');
  renderTermPreview('td');
}

async function saveTermoEmprestimo(){
  const clausulas = ($('te-clausulas').value||'').split('\n').map(s=>s.trim()).filter(Boolean);
  await api('/settings/termos','PUT',{termo_emprestimo:{
    titulo:    $('te-titulo').value,
    preambulo: $('te-preambulo').value,
    clausulas,
    rodape:    $('te-rodape').value,
  }});
  toast('Termo de empréstimo salvo');
}

async function saveTermoAvulsoModelo(){
  const tipo = _activeTermAvulsoTipo || termAvulsoTipoFromKind($('term-preview-kind')?.value || '');
  if(!tipo){ toast('Selecione um modelo para salvar.','error'); return; }
  const clausulas = ($('ta-clausulas').value||'').split('\n').map(s=>s.trim()).filter(Boolean);
  _termoAvulsoModelos[tipo] = {
    titulo:    $('ta-titulo').value,
    preambulo: $('ta-preambulo').value,
    clausulas,
    rodape:    $('ta-rodape').value,
  };
  await api('/settings/termos','PUT',{termos_avulsos_modelos:_termoAvulsoModelos});
  _settings.termos_avulsos_modelos = {..._termoAvulsoModelos};
  toast(`Modelo ${tipo} salvo`);
}

