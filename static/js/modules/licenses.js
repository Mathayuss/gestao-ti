// ══════════════════════════════════════════════════════════════════════════
// LICENÇAS
// ══════════════════════════════════════════════════════════════════════════
function licenseUnitCost(l){return Number(l.custoUnitario ?? l.custo ?? 0);}
function licenseTotalCost(l){return Number(l.custoTotal ?? (licenseUnitCost(l) * Number(l.total || 0)));}
function licenseMonthlyCost(l){
  if(l.custoMensal !== undefined) return Number(l.custoMensal || 0);
  return (l.tipo === 'Assinatura mensal' || l.tipo === 'Assinatura') ? licenseTotalCost(l) : 0;
}
function licenseAnnualCost(l){
  if(l.custoAnual !== undefined) return Number(l.custoAnual || 0);
  if(l.tipo === 'Assinatura mensal' || l.tipo === 'Assinatura') return licenseMonthlyCost(l) * 12;
  if(l.tipo === 'Anual') return licenseTotalCost(l);
  return 0;
}
function fmtOptionalCur(v){return Number(v || 0) > 0 ? fmtCur(v) : '—';}
async function renderLicencas(){
  const data=await api('/licenses');
  $('content').innerHTML=`
  <div class="flex-between mb-16"><div></div><button class="btn btn-primary" onclick="openNewLicense()">Nova Licença</button></div>
  <div class="card mb-16"><div class="table-wrap"><table>
    <thead><tr><th>Software</th><th>Fornecedor</th><th>Tipo</th><th>Quantidade</th><th>Atribuídas</th><th>Saldo</th><th>Vencimento</th><th>Custo Unit.</th><th>Custo Mensal</th><th>Custo Anual</th><th>Situação</th><th></th></tr></thead>
    <tbody>${data.map(l=>{
      const saldo=l.total-l.atribuidas; const d=daysUntil(l.vencimento); const wV=d>=0&&d<=60;
      const sit=l.atribuidas>l.total?['Excedido','red']:wV?['Vence em breve','amber']:saldo===0?['Sem saldo','amber']:['Regular','green'];
      return `<tr>
        <td style="font-weight:600">${esc(l.software)}</td>
        <td>${esc(l.fornecedor)}</td>
        <td>${badge(l.tipo,'gray')}</td>
        <td>${l.total}</td><td>${l.atribuidas}</td>
        <td style="font-weight:700;color:${saldo<0?'var(--red)':saldo===0?'var(--amber)':'var(--green)'}">${saldo<0?'−'+Math.abs(saldo):saldo}</td>
        <td style="font-size:12px;color:${wV?'var(--amber)':'inherit'}">${fmtDate(l.vencimento)}${wV?` <small>(${d}d)</small>`:''}</td>
        <td>${fmtCur(licenseUnitCost(l))}</td>
        <td>${fmtOptionalCur(licenseMonthlyCost(l))}</td>
        <td>${fmtOptionalCur(licenseAnnualCost(l))}</td>
        <td>${badge(...sit)}</td>
        <td><button class="btn btn-default btn-sm" onclick='viewLicense(${JSON.stringify(l).replace(/"/g,'&quot;')})'>Detalhes</button></td>
      </tr>`;}).join('')}
    </tbody>
  </table></div></div>
  <div class="grid-4">
    <div class="stat-card"><div class="stat-label">Total de Licenças</div><div class="stat-value">${data.reduce((s,l)=>s+l.total,0)}</div></div>
    <div class="stat-card"><div class="stat-label">Custo Mensal Total</div><div class="stat-value" style="font-size:20px">${fmtCur(data.reduce((s,l)=>s+licenseMonthlyCost(l),0))}</div></div>
    <div class="stat-card"><div class="stat-label">Custo Anual Total</div><div class="stat-value" style="font-size:20px">${fmtCur(data.reduce((s,l)=>s+licenseAnnualCost(l),0))}</div></div>
    <div class="stat-card"><div class="stat-label">Vencendo em 60 dias</div><div class="stat-value" style="color:var(--amber)">${data.filter(l=>{const d=daysUntil(l.vencimento);return d>=0&&d<=60}).length}</div></div>
  </div>`;
}
function viewLicense(l){
  const saldo = l.total - l.atribuidas;
  openModal('Detalhes da Licença',`
    <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:16px">
      <div>
        <div style="font-size:18px;font-weight:800">${esc(l.software)}</div>
        <div style="font-size:13px;color:var(--text2)">${esc(l.fornecedor)} · ${esc(l.tipo)}</div>
      </div>
      ${badge(saldo<0?'Excedido':saldo===0?'Sem saldo':'Regular',saldo<0?'red':saldo===0?'amber':'green')}
    </div>
    <div class="grid-4 mb-16">
      <div class="stat-card"><div class="stat-label">Quantidade</div><div class="stat-value">${l.total}</div></div>
      <div class="stat-card"><div class="stat-label">Atribuídas</div><div class="stat-value">${l.atribuidas}</div></div>
      <div class="stat-card"><div class="stat-label">Saldo</div><div class="stat-value" style="color:var(--${saldo<0?'red':saldo===0?'amber':'green'})">${saldo}</div></div>
      <div class="stat-card"><div class="stat-label">Custo unitário</div><div class="stat-value" style="font-size:18px">${fmtCur(licenseUnitCost(l))}</div></div>
      <div class="stat-card"><div class="stat-label">Custo total</div><div class="stat-value" style="font-size:18px">${fmtCur(licenseTotalCost(l))}</div></div>
      <div class="stat-card"><div class="stat-label">Custo mensal</div><div class="stat-value" style="font-size:18px">${fmtOptionalCur(licenseMonthlyCost(l))}</div></div>
      <div class="stat-card"><div class="stat-label">Custo anual</div><div class="stat-value" style="font-size:18px">${fmtOptionalCur(licenseAnnualCost(l))}</div></div>
    </div>
    <div style="background:var(--bg3);border:1px solid var(--border);border-radius:var(--r);padding:10px 12px">
      <div style="font-size:11px;color:var(--text3);font-weight:700;text-transform:uppercase;margin-bottom:3px">Vencimento</div>
      <div style="font-size:14px;font-weight:700">${fmtDate(l.vencimento)}</div>
    </div>
    ${attachmentPanel('license', l.id, 'Anexos da Licença')}
    <div class="modal-footer"><button class="btn btn-default" onclick="closeModal()">Fechar</button></div>
  `,true);
  loadAttachments('license', l.id);
}
function openNewLicense(){
  openModal('Nova Licença',`
  <div class="form-group"><label>Software</label><input id="fl-sw"></div>
  <div class="form-grid-2">
    <div class="form-group"><label>Fornecedor</label><input id="fl-forn"></div>
    <div class="form-group"><label>Tipo</label><select id="fl-tipo" onchange="updateLicenseCostLabel()"><option>Assinatura mensal</option><option>Anual</option><option>Perpétua</option><option>Por uso</option></select></div>
    <div class="form-group"><label>Quantidade</label><input id="fl-tot" type="number" min="0" value="10"></div>
    <div class="form-group"><label>Atribuídas</label><input id="fl-atr" type="number" value="0"></div>
    <div class="form-group"><label id="fl-custo-label">Custo unitário mensal (R$)</label><input id="fl-custo" type="number" step="0.01" min="0" value="0"></div>
    <div class="form-group"><label>Vencimento</label><input id="fl-venc" type="date"></div>
  </div>
  <div class="modal-footer"><button class="btn btn-default" onclick="closeModal()">Cancelar</button><button class="btn btn-primary" onclick="saveLicense()">Salvar</button></div>`);
  updateLicenseCostLabel();
}
function updateLicenseCostLabel(){
  const label=$('fl-custo-label'); if(!label || !$('fl-tipo')) return;
  const tipo=$('fl-tipo').value;
  label.textContent = tipo === 'Assinatura mensal' ? 'Custo unitário mensal (R$)' :
    tipo === 'Anual' ? 'Custo unitário anual (R$)' : 'Custo unitário (R$)';
}
async function saveLicense(){
  await api('/licenses','POST',{software:$('fl-sw').value,fornecedor:$('fl-forn').value,tipo:$('fl-tipo').value,total:$('fl-tot').value,atribuidas:$('fl-atr').value,custo:$('fl-custo').value,vencimento:$('fl-venc').value});
  toast('Licença cadastrada');closeModal();renderLicencas();
}

