// ══════════════════════════════════════════════════════════════════════════
// CAMPANHAS DE AUDITORIA
// ══════════════════════════════════════════════════════════════════════════
let _auditCampaignSelected = null;
let _auditFilter = '';

function normalizeAuditAssetInput(value){
  let v=String(value||'').trim();
  const marker='/asset/';
  if(v.includes(marker)) v=v.split(marker).pop().split('?')[0].split('#')[0].replace(/\/+$/,'');
  return v;
}

function auditStatusBadge(status){
  return badge(status, status==='Conferido'?'green':status==='Divergente'?'red':status==='Extra'?'amber':status==='Encerrada'?'gray':'blue');
}

async function renderAuditorias(){
  const [campaigns, settings] = await Promise.all([api('/audit-campaigns'), api('/settings')]);
  if(!campaigns || !settings) return;
  const openCampaigns = campaigns.filter(c=>c.status==='Aberta').length;
  const totalPend = campaigns.reduce((s,c)=>s+(c.stats?.pendentes||0),0);
  const totalDiv = campaigns.reduce((s,c)=>s+(c.stats?.divergentes||0)+(c.stats?.extras||0),0);
  $('content').innerHTML = `
  <div class="grid-3 mb-16">
    <div class="stat-card"><div class="stat-label">Campanhas abertas</div><div class="stat-value" style="color:var(--blue)">${openCampaigns}</div></div>
    <div class="stat-card"><div class="stat-label">Pendências de conferência</div><div class="stat-value" style="color:var(--amber)">${totalPend}</div></div>
    <div class="stat-card"><div class="stat-label">Divergências / extras</div><div class="stat-value" style="color:var(--red)">${totalDiv}</div></div>
  </div>
  <div class="flex-between mb-16" style="gap:12px;flex-wrap:wrap">
    <div class="search-wrap"><span class="search-icon">${inlineIcon('search')}</span>
      <input placeholder="Filtrar campanhas..." onkeyup="_auditFilter=this.value;renderAuditoriasList()" id="audit-filter" value="${esc(_auditFilter)}">
    </div>
    <button class="btn btn-primary" onclick="openNewAuditCampaign()">Nova Campanha</button>
  </div>
  <div class="grid-2">
    <div class="card">
      <div class="section-title">Campanhas</div>
      <div id="audit-campaign-list"></div>
    </div>
    <div id="audit-detail" class="card">
      <div class="section-title">Detalhes</div>
      <p style="font-size:13px;color:var(--text3)">Selecione uma campanha para acompanhar pendências e registrar conferências.</p>
    </div>
  </div>`;
  window._auditCampaigns = campaigns;
  window._auditSettings = settings;
  renderAuditoriasList();
}

function renderAuditoriasList(){
  const campaigns = (window._auditCampaigns || []).filter(c=>{
    const q=(_auditFilter||'').toLowerCase();
    return !q || [c.nome,c.unidade,c.setor,c.status].join(' ').toLowerCase().includes(q);
  });
  const html = campaigns.length ? campaigns.map(c=>{
    const st=c.stats||{};
    return `<div class="alert-row" style="align-items:flex-start;gap:10px;padding:10px 0">
      <div style="flex:1;min-width:0">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:4px">
          <strong style="font-size:13px">${esc(c.nome)}</strong>${auditStatusBadge(c.status)}
        </div>
        <div style="font-size:11px;color:var(--text3);line-height:1.6">
          ${esc(c.unidade||'Todas as unidades')} · ${esc(c.setor||'Todos os setores')} · ${fmtDate(c.dataInicio)}
        </div>
        <div class="progress-wrap" style="margin-top:8px"><div class="progress-bar" style="width:${st.progresso||0}%;background:var(--blue)"></div></div>
        <div style="font-size:11px;color:var(--text3);margin-top:4px">${st.conferidos||0}/${st.total||0} conferidos · ${st.pendentes||0} pendentes · ${st.divergentes||0} divergências · ${st.extras||0} extras</div>
      </div>
      <button class="btn btn-default btn-sm" onclick="openAuditCampaign('${c.id}')">Abrir</button>
    </div>`;
  }).join('') : `<p style="font-size:13px;color:var(--text3);padding:8px 0">Nenhuma campanha encontrada.</p>`;
  const el=$('audit-campaign-list');
  if(el) el.innerHTML=html;
}

function openNewAuditCampaign(){
  const settings = window._auditSettings || {unidades:[],setores:[]};
  openModal('Nova Campanha de Auditoria',`
    <div class="form-group"><label>Nome</label><input id="ac-nome" placeholder="Auditoria física - Maio/2026"></div>
    <div class="form-grid-2">
      <div class="form-group"><label>Unidade</label><select id="ac-unidade"><option value="">Todas</option>${settings.unidades.map(u=>`<option>${esc(u.nome)}</option>`).join('')}</select></div>
      <div class="form-group"><label>Setor</label><select id="ac-setor"><option value="">Todos</option>${settings.setores.map(s=>`<option>${esc(s)}</option>`).join('')}</select></div>
    </div>
    <div class="form-group"><label>Observação</label><textarea id="ac-obs" style="min-height:80px;resize:vertical"></textarea></div>
    <div class="info-box blue">A campanha cria uma lista esperada com os ativos ativos do escopo escolhido. Depois, cada item pode ser conferido e marcado como OK, divergente ou extra.</div>
    <div class="modal-footer"><button class="btn btn-default" onclick="closeModal()">Cancelar</button><button class="btn btn-primary" onclick="saveAuditCampaign()">Criar Campanha</button></div>
  `,false);
}

async function saveAuditCampaign(){
  const r = await api('/audit-campaigns','POST',{
    nome:$('ac-nome').value,
    unidade:$('ac-unidade').value,
    setor:$('ac-setor').value,
    observacao:$('ac-obs').value,
  });
  toast('Campanha criada');
  closeModal();
  _auditCampaignSelected = r.id;
  await renderAuditorias();
  await openAuditCampaign(r.id);
}

async function openAuditCampaign(id){
  _auditCampaignSelected = id;
  const c = await api('/audit-campaigns/'+id);
  const items = c.items || [];
  const st = c.stats || {};
  const pending = items.filter(i=>i.status==='Pendente').length;
  $('audit-detail').innerHTML = `
    <div class="flex-between" style="align-items:flex-start;gap:12px;flex-wrap:wrap;margin-bottom:14px">
      <div>
        <div class="section-title" style="margin-bottom:4px">${esc(c.nome)}</div>
        <div style="font-size:12px;color:var(--text3)">${esc(c.unidade||'Todas as unidades')} · ${esc(c.setor||'Todos os setores')} · início ${fmtDate(c.dataInicio)}</div>
      </div>
      <div class="flex-gap">
        ${auditStatusBadge(c.status)}
        ${c.status==='Aberta'
          ? `<button class="btn btn-default btn-sm" onclick="toggleAuditCampaign('${c.id}','Encerrada')">Encerrar</button>`
          : `<button class="btn btn-default btn-sm" onclick="toggleAuditCampaign('${c.id}','Aberta')">Reabrir</button>`}
      </div>
    </div>
    <div class="grid-4 mb-16">
      <div class="stat-card"><div class="stat-label">Total</div><div class="stat-value">${st.total||0}</div></div>
      <div class="stat-card"><div class="stat-label">Conferidos</div><div class="stat-value" style="color:var(--green)">${st.conferidos||0}</div></div>
      <div class="stat-card"><div class="stat-label">Pendentes</div><div class="stat-value" style="color:var(--amber)">${pending}</div></div>
      <div class="stat-card"><div class="stat-label">Divergências</div><div class="stat-value" style="color:var(--red)">${(st.divergentes||0)+(st.extras||0)}</div></div>
    </div>
    <div class="flex-between mb-16" style="gap:10px;flex-wrap:wrap">
      <input id="audit-asset-id" placeholder="ID, URL do QR, patrimonio, Service Tag ou hostname..." style="max-width:360px">
      <div class="flex-gap">
        <button class="btn btn-primary btn-sm" onclick="checkAuditByAsset('${c.id}')">Conferir por ID</button>
        <button class="btn btn-default btn-sm" onclick="exportAuditCampaignCsv('${c.id}')">Exportar CSV</button>
      </div>
    </div>
    <div class="table-wrap"><table>
      <thead><tr><th>Ativo</th><th>Esperado</th><th>Observado</th><th>Status</th><th>Ação</th></tr></thead>
      <tbody>${items.map(i=>`<tr>
        <td><div class="mono" style="font-weight:700">${esc(i.assetId||'—')}</div><div style="font-size:11px;color:var(--text3)">${esc(i.assetNome||'')}</div><div style="font-size:11px;color:var(--text3)">Pat: ${esc(i.patrimonio||'—')} · ST: ${esc(i.serviceTag||'—')}</div></td>
        <td style="font-size:12px;color:var(--text2)">${esc(i.expectedUnidade||'—')}<br>${esc(i.expectedSetor||'—')}<br>${esc(i.expectedColaborador||'—')}</td>
        <td style="font-size:12px;color:var(--text2)">${esc(i.observedUnidade||'—')}<br>${esc(i.observedSetor||'—')}<br>${esc(i.observedResponsavel||'—')}${i.observedLocal?`<br><span style="color:var(--text3)">Local: ${esc(i.observedLocal)}</span>`:''}</td>
        <td>${auditStatusBadge(i.status)}${i.divergencia?`<div style="font-size:11px;color:var(--red-text);margin-top:4px">${esc(i.divergencia)}</div>`:''}</td>
        <td>${c.status==='Aberta'?`<button class="btn btn-default btn-sm" onclick="openAuditCheck('${c.id}','${i.id}')">Conferir</button>`:'—'}</td>
      </tr>`).join('')}</tbody>
    </table></div>`;
}

function openAuditCheck(cid,itemId){
  const c = window._auditCampaigns?.find(x=>x.id===cid);
  api('/audit-campaigns/'+cid).then(full=>{
    const item=(full.items||[]).find(i=>i.id===itemId);
    if(!item) return;
    openModal('Conferir Ativo',`
      <div class="info-box blue" style="margin-bottom:12px"><strong>${esc(item.assetNome||item.assetId)}</strong><br>Esperado: ${esc(item.expectedUnidade||'—')} · ${esc(item.expectedColaborador||'—')}</div>
      <div class="form-grid-2">
        <div class="form-group"><label>Unidade observada</label><input id="aci-unidade" value="${escAttr(item.observedUnidade||item.expectedUnidade||'')}"></div>
        <div class="form-group"><label>Setor observado</label><input id="aci-setor" value="${escAttr(item.observedSetor||item.expectedSetor||'')}"></div>
        <div class="form-group"><label>Local fisico / sala</label><input id="aci-local" value="${escAttr(item.observedLocal||'')}" placeholder="Ex: Sala 03, bancada TI, recepcao..."></div>
        <div class="form-group"><label>Responsável observado</label><input id="aci-resp" value="${escAttr(item.observedResponsavel||item.expectedColaborador||'')}"></div>
      </div>
      <div class="form-group"><label>Status manual</label><select id="aci-status"><option value="">Automático</option><option>Conferido</option><option>Divergente</option><option>Extra</option></select></div>
      <div class="form-group"><label>Observação</label><textarea id="aci-obs" style="min-height:80px;resize:vertical">${esc(item.observacao||'')}</textarea></div>
      <div class="modal-footer"><button class="btn btn-default" onclick="closeModal()">Cancelar</button><button class="btn btn-primary" onclick="saveAuditCheck('${cid}','${itemId}')">Salvar Conferência</button></div>
    `);
  });
}

async function saveAuditCheck(cid,itemId){
  await api(`/audit-campaigns/${cid}/items/${itemId}/check`,'POST',{
    unidade:$('aci-unidade').value,
    setor:$('aci-setor').value,
    localFisico:$('aci-local').value,
    responsavel:$('aci-resp').value,
    status:$('aci-status').value,
    observacao:$('aci-obs').value,
  });
  toast('Ativo conferido');
  closeModal();
  await renderAuditorias();
  await openAuditCampaign(cid);
}

async function checkAuditByAsset(cid){
  const aid = normalizeAuditAssetInput($('audit-asset-id').value);
  if(!aid){toast('Informe ou leia o ID do ativo.','error');return;}
  await api(`/audit-campaigns/${cid}/assets/${encodeURIComponent(aid)}/check`,'POST',{});
  toast('Ativo conferido pela campanha');
  await renderAuditorias();
  await openAuditCampaign(cid);
}

async function toggleAuditCampaign(cid,status){
  let payload={status};
  if(status==='Encerrada'){
    const c = await api('/audit-campaigns/'+cid);
    const pend = c?.stats?.pendentes || 0;
    if(pend && !confirm(`Esta campanha ainda possui ${pend} item(ns) pendente(s). Encerrar mesmo assim?`)) return;
    if(pend) payload.confirmarPendencias = true;
  }
  await api('/audit-campaigns/'+cid,'PUT',payload);
  toast(status==='Encerrada'?'Campanha encerrada':'Campanha reaberta');
  await renderAuditorias();
  await openAuditCampaign(cid);
}

async function exportAuditCampaignCsv(cid){
  const c = await api('/audit-campaigns/'+cid);
  const rows = [['Campanha','Ativo','Hostname','Patrimonio','Service Tag','Unidade Esperada','Setor Esperado','Responsavel Esperado','Unidade Observada','Setor Observado','Local Fisico','Responsavel Observado','Status','Divergencia','Auditado Por','Auditado Em']];
  (c.items||[]).forEach(i=>rows.push([c.nome,i.assetId,i.assetNome,i.patrimonio,i.serviceTag,i.expectedUnidade,i.expectedSetor,i.expectedColaborador,i.observedUnidade,i.observedSetor,i.observedLocal,i.observedResponsavel,i.status,i.divergencia,i.auditadoPor,i.auditadoEm]));
  const csv = rows.map(r=>r.map(v=>`"${String(v||'').replace(/"/g,'""')}"`).join(';')).join('\n');
  const blob = new Blob([csv], {type:'text/csv;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = `auditoria_${cid}.csv`; a.click();
  URL.revokeObjectURL(url);
}

