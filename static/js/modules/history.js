// ══════════════════════════════════════════════════════════════════════════
// HISTÓRICO DO ATIVO
// ══════════════════════════════════════════════════════════════════════════
const HIST_COR_MAP = {
  green:  ['var(--green-bg)',  'var(--green-text)',  'var(--green-border)'],
  blue:   ['var(--blue-bg)',   'var(--blue-text)',   'var(--blue-border)'],
  amber:  ['var(--amber-bg)',  'var(--amber-text)',  'var(--amber-border)'],
  red:    ['var(--red-bg)',    'var(--red-text)',    'var(--red-border)'],
  purple: ['var(--purple-bg)', 'var(--purple-text)', 'var(--border2)'],
  gray:   ['var(--bg3)',       'var(--text2)',        'var(--border2)'],
};

async function viewAssetHistory(aid) {
  const h = await api('/assets/' + aid + '/history');
  if (!h) return;
  const { asset, eventos, totalEventos } = h;

  const fmtEvData = iso => {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR', {hour:'2-digit',minute:'2-digit'});
  };

  const tipoLabel = {
    auditoria:'Sistema', alocacao:'Alocação', devolucao:'Devolução',
    manutencao:'Manutenção', incidente:'Incidente', insumo:'Insumo',
  };

  const rowHtml = eventos.length ? eventos.map((e, i) => {
    const [bg, fg, border] = HIST_COR_MAP[e.cor] || HIST_COR_MAP.gray;
    const icone = (e.extra && e.extra.icone) || e.icone || 'clipboard';
    const cor   = (e.extra && e.extra.cor)   || e.cor  || 'gray';
    const [bg2, fg2] = HIST_COR_MAP[cor] || HIST_COR_MAP.gray;

    let extraHtml = '';
    if (e.extra) {
      if (e.extra.alocacaoId) extraHtml += `<span class="badge badge-gray" style="font-size:10px">${esc(e.extra.alocacaoId)}</span> `;
      if (e.extra.termoStatus) extraHtml += badge(e.extra.termoStatus) + ' ';
      if (e.extra.motivo)      extraHtml += `<span style="font-size:11px;color:var(--text3)">${esc(e.extra.motivo)}</span>`;
      if (e.extra.osId)        extraHtml += `<span class="badge badge-gray" style="font-size:10px">${esc(e.extra.osId)}</span> `;
      if (e.extra.status && e.tipo === 'manutencao') extraHtml += badge(e.extra.status, MANUT_STATUS_COLOR[e.extra.status]||'gray') + ' ';
      if (e.extra.custoTotal)  extraHtml += `<span style="font-size:11px;color:var(--text2)">${fmtCur(e.extra.custoTotal)}</span>`;
      if (e.extra.incidenteId) extraHtml += `<span class="badge badge-gray" style="font-size:10px">${esc(e.extra.incidenteId)}</span>`;
    }

    return `
    <div style="display:flex;gap:12px;align-items:flex-start;padding:10px 0;border-bottom:1px solid var(--border)">
      <!-- ícone + linha vertical -->
      <div style="display:flex;flex-direction:column;align-items:center;flex-shrink:0;width:32px">
        <div style="width:32px;height:32px;border-radius:99px;background:${bg2};color:${fg2};display:flex;align-items:center;justify-content:center;font-size:15px;flex-shrink:0">${inlineIcon(icone)}</div>
        ${i < eventos.length-1 ? `<div style="width:2px;flex:1;background:var(--border);margin-top:4px;min-height:16px"></div>` : ''}
      </div>
      <!-- conteúdo -->
      <div style="flex:1;min-width:0">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;flex-wrap:wrap">
          <div>
            <span style="font-size:13px;font-weight:600">${esc(e.descricao)}</span>
            ${e.usuario && e.usuario !== 'sistema' ? `<span style="font-size:11px;color:var(--text3);margin-left:6px">por ${esc(e.usuario)}</span>` : ''}
          </div>
          <div style="font-size:11px;color:var(--text3);white-space:nowrap;flex-shrink:0">${fmtEvData(e.data)}</div>
        </div>
        ${extraHtml ? `<div style="margin-top:4px;display:flex;flex-wrap:wrap;gap:4px;align-items:center">${extraHtml}</div>` : ''}
        <div style="margin-top:3px">
          <span style="font-size:10px;padding:1px 6px;border-radius:99px;background:${bg};color:${fg};border:1px solid ${border}">${tipoLabel[e.tipo]||e.tipo}</span>
        </div>
      </div>
    </div>`;
  }).join('') : '<p style="text-align:center;color:var(--text3);padding:32px 0">Nenhum evento registrado para este ativo.</p>';

  openModal(`Histórico — ${esc(asset.hostname)}`, `
  <!-- resumo do ativo -->
  <div style="display:flex;gap:12px;align-items:center;padding:10px 14px;background:var(--bg3);border-radius:var(--r);margin-bottom:16px">
    <div style="color:var(--blue)">${inlineIcon('ativos')}</div>
    <div style="flex:1">
      <div style="font-weight:700;font-size:14px">${esc(asset.hostname)}</div>
      <div style="font-size:12px;color:var(--text2)">${esc(asset.fabricante)} ${esc(asset.modelo)} · ${esc(asset.categoria)}</div>
    </div>
    ${badge(asset.status)}
    <span class="badge badge-gray" style="font-size:11px">${totalEventos} evento(s)</span>
  </div>

  <!-- filtro rápido por tipo -->
  <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px" id="hist-filtros">
    ${['Todos','Alocação','Manutenção','Incidente','Insumo','Sistema'].map(f=>
      `<button class="btn btn-sm btn-default" onclick="filtrarHistorico('${f}')" id="hf-${f}">${f}</button>`
    ).join('')}
  </div>

  <!-- linha do tempo -->
  <div style="max-height:52vh;overflow-y:auto;padding-right:4px" id="hist-timeline">
    ${rowHtml}
  </div>
  <div class="modal-footer">
    <button class="btn btn-default" onclick="closeModal()">Fechar</button>
  </div>`, true);

  // guarda os eventos no modal para filtro client-side
  $('modal-box').dataset.histEventos = JSON.stringify(eventos);
  filtrarHistorico('Todos');
}

function filtrarHistorico(filtro) {
  // destaca botão ativo
  ['Todos','Alocação','Manutenção','Incidente','Insumo','Sistema'].forEach(f => {
    const btn = document.getElementById('hf-' + f);
    if (btn) btn.className = 'btn btn-sm ' + (f === filtro ? 'btn-primary' : 'btn-default');
  });
  const eventos = JSON.parse($('modal-box').dataset.histEventos || '[]');
  const mapa = {Todos:null,Alocação:'alocacao',Manutenção:'manutencao',
                Incidente:'incidente',Insumo:'insumo',Sistema:'auditoria'};
  const tipo = mapa[filtro];

  const HIST_COR_MAP2 = {
    green:  ['var(--green-bg)',  'var(--green-text)',  'var(--green-border)'],
    blue:   ['var(--blue-bg)',   'var(--blue-text)',   'var(--blue-border)'],
    amber:  ['var(--amber-bg)',  'var(--amber-text)',  'var(--amber-border)'],
    red:    ['var(--red-bg)',    'var(--red-text)',    'var(--red-border)'],
    purple: ['var(--purple-bg)', 'var(--purple-text)', 'var(--border2)'],
    gray:   ['var(--bg3)',       'var(--text2)',        'var(--border2)'],
  };
  const tipoLabel2 = {auditoria:'Sistema',alocacao:'Alocação',devolucao:'Devolução',
                      manutencao:'Manutenção',incidente:'Incidente',insumo:'Insumo'};
  const fmtEvData2 = iso => {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit'});
  };

  const filtrados = tipo ? eventos.filter(e => e.tipo === tipo || (tipo === 'alocacao' && e.tipo === 'devolucao')) : eventos;
  const tl = $('hist-timeline');
  if (!filtrados.length) {
    tl.innerHTML = '<p style="text-align:center;color:var(--text3);padding:32px 0">Nenhum evento nesta categoria.</p>';
    return;
  }
  tl.innerHTML = filtrados.map((e, i) => {
    const [bg, fg, border] = HIST_COR_MAP2[e.cor] || HIST_COR_MAP2.gray;
    const icone = (e.extra && e.extra.icone) || e.icone || 'clipboard';
    const cor2  = (e.extra && e.extra.cor)   || e.cor  || 'gray';
    const [bg2, fg2] = HIST_COR_MAP2[cor2] || HIST_COR_MAP2.gray;
    let extraHtml = '';
    if (e.extra) {
      if (e.extra.alocacaoId) extraHtml += `<span class="badge badge-gray" style="font-size:10px">${esc(e.extra.alocacaoId)}</span> `;
      if (e.extra.termoStatus) extraHtml += badge(e.extra.termoStatus) + ' ';
      if (e.extra.motivo)      extraHtml += `<span style="font-size:11px;color:var(--text3)">${esc(e.extra.motivo)}</span>`;
      if (e.extra.osId)        extraHtml += `<span class="badge badge-gray" style="font-size:10px">${esc(e.extra.osId)}</span> `;
      if (e.extra.status && e.tipo === 'manutencao') extraHtml += badge(e.extra.status, (typeof MANUT_STATUS_COLOR !== 'undefined' ? MANUT_STATUS_COLOR[e.extra.status] : null)||'gray') + ' ';
      if (e.extra.custoTotal)  extraHtml += `<span style="font-size:11px;color:var(--text2)">${fmtCur(e.extra.custoTotal)}</span>`;
      if (e.extra.incidenteId) extraHtml += `<span class="badge badge-gray" style="font-size:10px">${esc(e.extra.incidenteId)}</span>`;
    }
    return `
    <div style="display:flex;gap:12px;align-items:flex-start;padding:10px 0;border-bottom:1px solid var(--border)">
      <div style="display:flex;flex-direction:column;align-items:center;flex-shrink:0;width:32px">
        <div style="width:32px;height:32px;border-radius:99px;background:${bg2};color:${fg2};display:flex;align-items:center;justify-content:center;font-size:15px">${inlineIcon(icone)}</div>
        ${i < filtrados.length-1 ? `<div style="width:2px;flex:1;background:var(--border);margin-top:4px;min-height:16px"></div>` : ''}
      </div>
      <div style="flex:1;min-width:0">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;flex-wrap:wrap">
          <div>
            <span style="font-size:13px;font-weight:600">${esc(e.descricao)}</span>
            ${e.usuario && e.usuario !== 'sistema' ? `<span style="font-size:11px;color:var(--text3);margin-left:6px">por ${esc(e.usuario)}</span>` : ''}
          </div>
          <div style="font-size:11px;color:var(--text3);white-space:nowrap">${fmtEvData2(e.data)}</div>
        </div>
        ${extraHtml ? `<div style="margin-top:4px;display:flex;flex-wrap:wrap;gap:4px;align-items:center">${extraHtml}</div>` : ''}
        <div style="margin-top:3px">
          <span style="font-size:10px;padding:1px 6px;border-radius:99px;background:${bg};color:${fg};border:1px solid ${border}">${tipoLabel2[e.tipo]||e.tipo}</span>
        </div>
      </div>
    </div>`;
  }).join('');
}

