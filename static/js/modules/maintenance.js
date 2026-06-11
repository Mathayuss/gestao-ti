// ══════════════════════════════════════════════════════════════════════════
// MANUTENÇÃO
// ══════════════════════════════════════════════════════════════════════════
const MANUT_STATUS_COLOR = {
  'Aberta':'blue','Em análise':'amber','Aguardando peça':'amber',
  'Em reparo':'amber','Concluída':'green','Sem reparo':'red','Cancelada':'gray'
};
const MANUT_STATUS_LIST  = ['Aberta','Em análise','Aguardando peça','Em reparo','Concluída','Sem reparo','Cancelada'];
const MANUT_ENCERRADA    = ['Concluída','Sem reparo','Cancelada'];

async function renderManutencao(statusFilter='') {
  const url = '/maintenance' + (statusFilter ? '?status='+encodeURIComponent(statusFilter) : '');
  const data = await api(url);
  if (!data) return;

  const cnt = {
    Aberta:   data.filter(m=>m.status==='Aberta').length,
    andamento:data.filter(m=>['Em análise','Aguardando peça','Em reparo'].includes(m.status)).length,
    Concluída:data.filter(m=>m.status==='Concluída').length,
    SemReparo:data.filter(m=>m.status==='Sem reparo').length,
  };
  const abertas = cnt.Aberta + cnt.andamento;
  const mb = $('manut-badge');
  if (mb) { mb.style.display = abertas ? '' : 'none'; mb.textContent = abertas; }

  $('content').innerHTML = `
  <div class="flex-between mb-16" style="flex-wrap:wrap;gap:8px">
    <div class="flex-gap" style="flex-wrap:wrap">
      ${['','Aberta','Em análise','Aguardando peça','Em reparo','Concluída','Sem reparo','Cancelada'].map(s=>
        `<button class="btn btn-sm ${s===statusFilter?'btn-primary':'btn-default'}" onclick="renderManutencao('${s}')">${s||'Todas'}</button>`
      ).join('')}
    </div>
    <button class="btn btn-primary" onclick="openNewManutencao()">Abrir OS</button>
  </div>
  <div class="grid-4 mb-16">
    ${[['OS Abertas',cnt.Aberta,'blue'],['Em andamento',cnt.andamento,'amber'],['Concluídas',cnt.Concluída,'green'],['Sem reparo',cnt.SemReparo,'red']].map(([l,v,c])=>
      `<div class="stat-card"><div class="stat-label">${l}</div><div class="stat-value" style="color:var(--${c}-text)">${v}</div></div>`
    ).join('')}
  </div>
  <div class="card"><div class="table-wrap"><table>
    <thead><tr><th>OS</th><th>Ativo</th><th>Tipo</th><th>Defeito</th><th>Técnico</th><th>Abertura</th><th>Status</th><th>Custo</th><th></th></tr></thead>
    <tbody>${data.length ? data.map(m=>`<tr>
      <td class="mono" style="color:var(--text3);font-weight:700">${esc(m.id)}</td>
      <td class="mono" style="font-size:12px">${esc((m.assetNome||'').split('—')[0].trim())}</td>
      <td>${badge(m.tipo, m.tipo==='Corretiva'?'red':m.tipo==='Preventiva'?'blue':'purple')}</td>
      <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px">${esc(m.descricaoDefeito)}</td>
      <td style="font-size:12px">${esc(m.tecnico||'—')}</td>
      <td style="font-size:12px">${fmtDate(m.dataAbertura)}</td>
      <td>${badge(m.status, MANUT_STATUS_COLOR[m.status]||'gray')}</td>
      <td style="font-size:12px">${m.custoTotal>0?fmtCur(m.custoTotal):'—'}</td>
      <td><button class="btn btn-default btn-sm" onclick="viewManutencao('${m.id}')">Detalhes</button></td>
    </tr>`).join('') : '<tr><td colspan="9" style="text-align:center;color:var(--text3);padding:24px">Nenhuma OS encontrada.</td></tr>'}
    </tbody>
  </table></div></div>`;
}

async function openNewManutencao() {
  const assets = await api('/assets');
  const elegiveis = assets.filter(a=>!['Baixado','Descartado','Extraviado','Vendido'].includes(a.status));
  openModal('Abrir Ordem de Serviço', `
  <div class="form-group"><label>Ativo</label>
    <select id="mn-asset">
      <option value="">Selecione o ativo...</option>
      ${elegiveis.map(a=>`<option value="${a.id}">[${esc(a.status)}] ${esc(a.hostname)} — ${esc(a.fabricante)} ${esc(a.modelo)}</option>`).join('')}
    </select>
  </div>
  <div class="form-grid-2">
    <div class="form-group"><label>Tipo</label>
      <select id="mn-tipo"><option>Corretiva</option><option>Preventiva</option><option>Melhoria</option></select>
    </div>
    <div class="form-group"><label>Técnico Responsável</label>
      <input id="mn-tec" list="mn-tec-list" placeholder="Nome do técnico">
      <datalist id="mn-tec-list">${_colab_cache.map(c=>`<option>${esc(c.nome)}</option>`).join('')}</datalist>
    </div>
  </div>
  <div class="form-group"><label>Descrição do Defeito / Motivo</label>
    <textarea id="mn-defeito" rows="3" placeholder="Descreva o problema ou motivo da manutenção..."></textarea>
  </div>
  <div class="form-group"><label>Observação</label>
    <textarea id="mn-obs" rows="2" placeholder="Informações adicionais (opcional)"></textarea>
  </div>
  <div class="info-box amber">Atenção: Ao abrir a OS, o status do ativo será alterado para <strong>Manutenção</strong> automaticamente.</div>
  <div class="modal-footer">
    <button class="btn btn-default" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="saveNewManutencao()">Abrir OS</button>
  </div>`, true);
}

async function saveNewManutencao() {
  const assetId = $('mn-asset').value;
  const defeito = $('mn-defeito').value.trim();
  if (!assetId) { toast('Selecione um ativo', 'error'); return; }
  if (!defeito)  { toast('Descreva o defeito', 'error'); return; }
  try {
    const r = await api('/maintenance', 'POST', {
      assetId, tipo: $('mn-tipo').value, tecnico: $('mn-tec').value,
      descricaoDefeito: defeito, observacao: $('mn-obs').value
    });
    toast('OS aberta: ' + r.id);
    closeModal(); renderManutencao();
  } catch(e) { toast(e.message, 'error'); }
}

async function viewManutencao(mid) {
  const m = await api('/maintenance/' + mid);
  if (!m) return;
  const isClosed = MANUT_ENCERRADA.includes(m.status);

  const pecasList = m.pecas && m.pecas.length
    ? m.pecas.map(p=>`
      <div style="display:flex;gap:10px;align-items:center;padding:8px 10px;border:1px solid var(--border);border-radius:var(--r);margin-bottom:6px">
        <span></span>
        <div style="flex:1">
          <div style="font-size:13px;font-weight:600">${esc(p.nome)}</div>
          <div style="font-size:11px;color:var(--text3)">${p.quantidade}x · ${fmtCur(p.custoUnitario)}/un</div>
        </div>
        <span class="badge badge-blue">${fmtCur(p.custoTotal)}</span>
        ${!isClosed?`<button class="btn btn-danger btn-icon btn-sm" onclick="removePeca('${mid}','${p.id}')">x</button>`:''}
      </div>`).join('')
    : '<p style="font-size:12px;color:var(--text3);padding:6px 0">Nenhuma peça registrada.</p>';

  openModal(`OS ${m.id}`, `
  <div class="form-grid-2" style="margin-bottom:16px">
    ${[['Ativo',esc(m.assetNome||'—')],['Tipo',badge(m.tipo,m.tipo==='Corretiva'?'red':m.tipo==='Preventiva'?'blue':'purple')],
       ['Status',badge(m.status,MANUT_STATUS_COLOR[m.status]||'gray')],['Técnico',esc(m.tecnico||'—')],
       ['Abertura',fmtDate(m.dataAbertura)],['Conclusão',fmtDate(m.dataConclusao)||'—'],
       ['Custo Total',fmtCur(m.custoTotal)],['Status anterior do ativo',esc(m.statusAnterior||'—')]
    ].map(([k,v])=>`<div style="background:var(--bg3);border-radius:var(--r);padding:8px 10px">
      <div style="font-size:11px;color:var(--text2);margin-bottom:2px">${k}</div>
      <div style="font-size:13px;font-weight:600">${v}</div>
    </div>`).join('')}
  </div>

  <div class="form-group"><label>Defeito Reportado</label>
    <div style="padding:8px 10px;background:var(--bg3);border-radius:var(--r);font-size:13px">${esc(m.descricaoDefeito||'—')}</div>
  </div>

  ${!isClosed ? `
  <div class="form-grid-2">
    <div class="form-group"><label>Status</label>
      <select id="mn-upd-status">
        ${MANUT_STATUS_LIST.filter(s=>!MANUT_ENCERRADA.includes(s)).map(s=>`<option ${s===m.status?'selected':''}>${s}</option>`).join('')}
      </select>
    </div>
    <div class="form-group"><label>Técnico</label>
      <input id="mn-upd-tec" value="${esc(m.tecnico||'')}" list="mn-tec-list3">
      <datalist id="mn-tec-list3">${_colab_cache.map(c=>`<option>${esc(c.nome)}</option>`).join('')}</datalist>
    </div>
  </div>
  <div class="form-group"><label>Diagnóstico</label>
    <textarea id="mn-upd-diag" rows="3" placeholder="O que foi identificado?">${esc(m.diagnostico||'')}</textarea>
  </div>` : `
  <div class="form-group"><label>Diagnóstico</label>
    <div style="padding:8px 10px;background:var(--bg3);border-radius:var(--r);font-size:13px">${esc(m.diagnostico||'—')}</div>
  </div>`}

  <hr class="divider">
  <div class="section-title" style="font-size:13px">Peças / Insumos (${m.pecas?m.pecas.length:0})</div>
  ${pecasList}
  ${!isClosed?`<button class="btn btn-default btn-sm" style="margin-bottom:12px" onclick="openAddPeca('${mid}')">Adicionar Peça</button>`:''}

  ${attachmentPanel('maintenance', mid, 'Anexos da OS')}

  <div class="modal-footer">
    <button class="btn btn-default" onclick="closeModal()">Fechar</button>
    ${!isClosed?`
    <button class="btn btn-warning" onclick="updateManutencao('${mid}')">Salvar Alterações</button>
    <button class="btn btn-success" onclick="openEncerrarOS('${mid}',${m.custoTotal||0})">Encerrar OS</button>`:''}
  </div>`, true);
  loadAttachments('maintenance', mid);
}

async function updateManutencao(mid) {
  try {
    await api('/maintenance/'+mid, 'PUT', {
      status:      $('mn-upd-status').value,
      diagnostico: $('mn-upd-diag').value,
      tecnico:     $('mn-upd-tec').value,
    });
    toast('OS atualizada'); closeModal(); renderManutencao();
  } catch(e) { toast(e.message, 'error'); }
}

async function openAddPeca(mid) {
  const supplies = await api('/supplies');
  const disponiveis = supplies.filter(s=>s.estoque>0);
  openModal('Adicionar Peça / Insumo', `
  <div class="form-group"><label>Item do Estoque</label>
    <select id="mp-supply" onchange="preenchePreco(this)">
      <option value="" data-preco="0">Selecione...</option>
      ${disponiveis.map(s=>`<option value="${s.id}" data-preco="${s.preco}">${esc(s.nome)} — estoque: ${s.estoque} · ${fmtCur(s.preco)}</option>`).join('')}
    </select>
  </div>
  <div class="form-grid-2">
    <div class="form-group"><label>Quantidade</label><input id="mp-qty" type="number" min="1" value="1"></div>
    <div class="form-group"><label>Custo Unitário (R$)</label><input id="mp-custo" type="number" step="0.01" min="0" value="0"></div>
  </div>
  <div class="info-box blue">O item será deduzido do estoque e o custo somado ao total da OS.</div>
  <div class="modal-footer">
    <button class="btn btn-default" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="saveAddPeca('${mid}')">Adicionar</button>
  </div>`, false, true);
}
function preenchePreco(sel){
  const opt = sel.options[sel.selectedIndex];
  if(opt && opt.dataset.preco) $('mp-custo').value = opt.dataset.preco;
}
async function saveAddPeca(mid) {
  const supplyId = $('mp-supply').value;
  if (!supplyId) { toast('Selecione um item', 'error'); return; }
  try {
    await api('/maintenance/'+mid+'/parts', 'POST', {
      supplyId, quantidade: +$('mp-qty').value, custoUnitario: +$('mp-custo').value
    });
    toast('Peça adicionada'); closeModal(); viewManutencao(mid);
  } catch(e) { toast(e.message, 'error'); }
}
async function removePeca(mid, pid) {
  try {
    await api('/maintenance/'+mid+'/parts/'+pid, 'DELETE');
    toast('Peça removida'); viewManutencao(mid);
  } catch(e) { toast(e.message, 'error'); }
}

function openEncerrarOS(mid, custoAtual) {
  openModal('Encerrar Ordem de Serviço', `
  <div class="form-group"><label>Resultado</label>
    <select id="enc-resultado" onchange="sugerirStatusAtivo(this.value)">
      <option value="Concluída">Concluída — equipamento reparado</option>
      <option value="Sem reparo">Sem reparo — não foi possível reparar</option>
      <option value="Cancelada">Cancelada — OS cancelada</option>
    </select>
  </div>
  <div class="form-group"><label>Status do Ativo após encerramento</label>
    <select id="enc-status-ativo">
      <option value="Disponível">Disponível</option>
      <option value="Alocado">Alocado (retornar ao colaborador)</option>
      <option value="Ativo">Ativo (infraestrutura)</option>
      <option value="Descartado">Descartado</option>
      <option value="Baixado">Baixado (baixa patrimonial)</option>
    </select>
  </div>
  <div class="form-group"><label>Diagnóstico / O que foi feito</label>
    <textarea id="enc-diag" rows="3" placeholder="Descreva a resolução ou motivo do encerramento..."></textarea>
  </div>
  <div class="form-group"><label>Custo Total Final (R$)</label>
    <input id="enc-custo" type="number" step="0.01" min="0" value="${custoAtual}">
  </div>
  <div class="modal-footer">
    <button class="btn btn-default" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-success" onclick="encerrarOS('${mid}')">Encerrar OS</button>
  </div>`, false, true);
}
function sugerirStatusAtivo(resultado) {
  const sel = $('enc-status-ativo');
  if(resultado==='Sem reparo') sel.value='Descartado';
  else if(resultado==='Cancelada') sel.value='Disponível';
  else sel.value='Disponível';
}
async function encerrarOS(mid) {
  try {
    await api('/maintenance/'+mid+'/close', 'POST', {
      resultado:   $('enc-resultado').value,
      statusAtivo: $('enc-status-ativo').value,
      diagnostico: $('enc-diag').value,
      custoTotal:  +$('enc-custo').value,
    });
    toast('OS encerrada com sucesso'); closeModal(); renderManutencao();
  } catch(e) { toast(e.message, 'error'); }
}

