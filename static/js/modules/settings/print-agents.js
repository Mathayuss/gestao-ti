let _settingsPrintAgents = [];

function renderPrintAgentsPanel(printers){
  _settingsPrintAgents = Array.isArray(printers) ? printers : [];
  const cards = _settingsPrintAgents.length ? _settingsPrintAgents.map(printer=>{
    const online = printer.status === 'Online';
    return `
      <div class="card" style="padding:16px;display:flex;flex-direction:column;gap:14px">
        <div class="flex-between" style="gap:12px;align-items:flex-start">
          <div style="display:flex;gap:12px;min-width:0">
            <div style="width:38px;height:38px;flex:0 0 38px;border-radius:8px;background:var(--blue-bg);color:var(--blue);display:grid;place-items:center">
              ${inlineIcon('printer')}
            </div>
            <div style="min-width:0">
              <div style="font-size:14px;font-weight:750;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(printer.name||printer.id)}</div>
              <div class="mono" style="font-size:11px;color:var(--text3);margin-top:2px">${esc(printer.id)}</div>
            </div>
          </div>
          ${badge(online?'Online':'Offline',online?'green':'gray')}
        </div>
        <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;font-size:12px">
          <div><span style="display:block;color:var(--text3);font-size:10px;font-weight:700;text-transform:uppercase">Impressora</span><strong>${esc(printer.windowsName||'-')}</strong></div>
          <div><span style="display:block;color:var(--text3);font-size:10px;font-weight:700;text-transform:uppercase">Resolução</span><strong>${esc(printer.dpi||203)} DPI</strong></div>
          <div><span style="display:block;color:var(--text3);font-size:10px;font-weight:700;text-transform:uppercase">Local</span><strong>${esc(printer.location||'-')}</strong></div>
          <div><span style="display:block;color:var(--text3);font-size:10px;font-weight:700;text-transform:uppercase">Último contato</span><strong>${printer.lastSeen?fmtDateTime(printer.lastSeen):'Nunca'}</strong></div>
        </div>
        <div style="display:flex;gap:6px;justify-content:flex-end;border-top:1px solid var(--border);padding-top:12px">
          <a class="btn btn-default btn-sm btn-icon" href="${printAgentDownloadUrl(printer)}" title="Baixar pacote do agente" aria-label="Baixar pacote do agente">${inlineIcon('download')}</a>
          <button class="btn btn-default btn-sm btn-icon" onclick="openPrinterAgentModal('${escAttr(printer.id)}')" title="Editar agente" aria-label="Editar agente">${inlineIcon('edit')}</button>
          <button class="btn btn-default btn-sm" onclick="renewPrinterAgentToken('${escAttr(printer.id)}')" title="Renovar token">Renovar token</button>
          <button class="btn btn-danger btn-sm btn-icon" onclick="deletePrinterAgent('${escAttr(printer.id)}')" title="Remover agente" aria-label="Remover agente">${inlineIcon('trash')}</button>
        </div>
      </div>`;
  }).join('') : `
    <div style="border:1px dashed var(--border);border-radius:var(--r);padding:36px 20px;text-align:center;color:var(--text3)">
      <div style="width:42px;height:42px;margin:0 auto 10px;color:var(--text3)">${svgIcon('printer')}</div>
      <div style="font-size:13px;font-weight:700;color:var(--text2)">Nenhum agente cadastrado</div>
    </div>`;

  return `<div id="cfg-panel-agentes" style="display:none">
    <div class="flex-between" style="margin-bottom:16px;gap:12px;align-items:flex-start;flex-wrap:wrap">
      <div>
        <div class="section-title" style="margin-bottom:4px">Agentes de impressão</div>
        <div style="font-size:12px;color:var(--text3)">Impressoras locais disponíveis para etiquetas.</div>
      </div>
      <button class="btn btn-primary btn-sm" onclick="openPrinterAgentModal()">${inlineIcon('plus')} Novo agente</button>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:12px">
      ${cards}
    </div>
  </div>`;
}

function printAgentDownloadUrl(printer){
  const params = new URLSearchParams({
    printer_id: printer?.id || 'ETIQUETAS-01',
    windows_printer: printer?.windowsName || 'Impressora de Etiquetas',
  });
  return `/api/print-agent/download?${params.toString()}`;
}

function openPrinterAgentModal(printerId=''){
  const printer = _settingsPrintAgents.find(item=>item.id===printerId) || null;
  openModal(printer ? 'Editar agente de impressão' : 'Novo agente de impressão',`
    <div class="form-grid-2">
      <div class="form-group">
        <label>ID do agente</label>
        <input id="pa-id" value="${escAttr(printer?.id||'')}" placeholder="ETIQUETAS-01" ${printer?'disabled':''} maxlength="60">
      </div>
      <div class="form-group">
        <label>Nome amigável</label>
        <input id="pa-name" value="${escAttr(printer?.name||'')}" placeholder="Recepção" maxlength="120">
      </div>
      <div class="form-group">
        <label>Nome da impressora no Windows</label>
        <input id="pa-win" value="${escAttr(printer?.windowsName||'')}" placeholder="ELGIN L42Pro" maxlength="120">
      </div>
      <div class="form-group">
        <label>Local</label>
        <input id="pa-location" value="${escAttr(printer?.location||'')}" placeholder="Almoxarifado" maxlength="120">
      </div>
      <div class="form-group">
        <label>Resolução</label>
        <select id="pa-dpi">
          <option value="203" ${(printer?.dpi||203)===203?'selected':''}>203 DPI</option>
          <option value="300" ${printer?.dpi===300?'selected':''}>300 DPI</option>
          <option value="600" ${printer?.dpi===600?'selected':''}>600 DPI</option>
        </select>
      </div>
      <div class="form-group">
        <label>Linguagem</label>
        <select id="pa-type" disabled><option>USB / ZPL</option></select>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-default" onclick="closeModal()">Cancelar</button>
      <button class="btn btn-primary" onclick="savePrinterAgent('${escAttr(printer?.id||'')}')">Salvar</button>
    </div>`,true);
}

async function savePrinterAgent(existingId=''){
  const id = existingId || ($('pa-id')?.value||'').trim();
  if(!id){ toast('Informe o ID do agente.','error'); return; }
  const payload = {
    id,
    name: $('pa-name')?.value || id,
    location: $('pa-location')?.value || '',
    windowsName: $('pa-win')?.value || 'Impressora de Etiquetas',
    dpi: Number($('pa-dpi')?.value) || 203,
    type: 'USB/ZPL',
  };
  try{
    const printer = await api(existingId?`/print-printers/${encodeURIComponent(existingId)}`:'/print-printers',existingId?'PUT':'POST',payload);
    closeModal();
    if(printer.token) showPrinterAgentToken(printer);
    else{
      toast('Agente atualizado.');
      renderConfiguracoes();
    }
  }catch(err){ toast(err.message||'Falha ao salvar agente.','error'); }
}

function showPrinterAgentToken(printer){
  openModal('Credencial do agente',`
    <div class="info-box amber" style="font-size:12px;line-height:1.6;margin-bottom:14px">
      O token será exibido somente agora. A renovação invalida a credencial anterior.
    </div>
    <div class="form-group"><label>ID do agente</label><input value="${escAttr(printer.id)}" readonly class="mono"></div>
    <div class="form-group"><label>Token</label><textarea id="pa-token-result" readonly rows="4" class="mono" style="width:100%;font-size:12px">${esc(printer.token)}</textarea></div>
    <div class="modal-footer">
      <button class="btn btn-default" onclick="copyPrinterAgentToken()">Copiar token</button>
      <a class="btn btn-default" href="${printAgentDownloadUrl(printer)}">${inlineIcon('download')} Baixar agente</a>
      <button class="btn btn-primary" onclick="closeModal();renderConfiguracoes()">Concluir</button>
    </div>`,true);
}

async function copyPrinterAgentToken(){
  const field = $('pa-token-result');
  if(!field) return;
  try{
    await navigator.clipboard.writeText(field.value);
    toast('Token copiado.');
  }catch(e){
    field.select();
    document.execCommand('copy');
    toast('Token copiado.');
  }
}

async function renewPrinterAgentToken(printerId){
  if(!confirm(`Renovar o token do agente ${printerId}? O token atual deixará de funcionar.`)) return;
  try{
    const printer = await api(`/print-printers/${encodeURIComponent(printerId)}/token`,'POST',{});
    showPrinterAgentToken(printer);
  }catch(err){ toast(err.message||'Falha ao renovar token.','error'); }
}

async function deletePrinterAgent(printerId){
  if(!confirm(`Remover o agente ${printerId}?`)) return;
  try{
    await api(`/print-printers/${encodeURIComponent(printerId)}`,'DELETE');
    toast('Agente removido.');
    renderConfiguracoes();
  }catch(err){ toast(err.message||'Falha ao remover agente.','error'); }
}
