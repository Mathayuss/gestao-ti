let _purchaseTab = 'solicitacoes';
let _purchaseStatusFilter = '';

const PURCHASE_RECEIPT_STATUSES = ['Pedido de compra emitido','Aguardando entrega','Recebida parcialmente','Recebida'];

function purchaseStatusBadge(status){
  const map = {
    'Rascunho':'gray','Aguardando aprovacao do Gerente de TI':'amber','Aprovada pelo Gerente de TI':'blue',
    'Aguardando aprovacao do Diretor':'amber','Aprovada pelo Diretor':'blue','Aguardando envio para Suprimentos':'blue',
    'Enviada para Suprimentos':'blue','Compra iniciada':'amber','Em cotacao':'amber','Aguardando emissao do pedido':'amber',
    'Pedido de compra emitido':'blue','Aguardando entrega':'amber','Recebida parcialmente':'amber','Recebida':'green',
    'Entrada no estoque realizada':'green','Concluida':'green','Reprovada':'red','Cancelada':'red','Devolvida para correcao':'amber'
  };
  return badge(status || 'Rascunho', map[status] || 'gray');
}

function purchaseTab(tab){ _purchaseTab = tab; renderCompras(); }

async function purchaseSupplies(){
  return api('/supplies').catch(()=>[]);
}

function purchaseSupplyOptions(supplies=[], selected=''){
  return `<option value=""></option>${supplies.map(s=>`<option value="${escAttr(s.id)}" ${selected===s.id?'selected':''}>${esc(s.nome||s.id)}${s.estoque!=null?' · estoque '+esc(s.estoque):''}</option>`).join('')}`;
}

async function renderCompras(){
  const [rows, rules] = await Promise.all([
    api(`/purchases?status=${encodeURIComponent(_purchaseStatusFilter||'')}`),
    api('/purchases/approval-rules').catch(()=>[]),
  ]);
  const tabs = [
    ['solicitacoes','Solicitacoes'], ['suprimentos','Fila Suprimentos'], ['alcadas','Alcadas']
  ];
  const filtered = _purchaseTab === 'suprimentos'
    ? rows.filter(r => ['Enviada para Suprimentos','Em analise por Suprimentos','Compra iniciada','Em cotacao','Aguardando emissao do pedido','Pedido de compra emitido','Aguardando entrega','Recebida parcialmente'].includes(r.status))
    : rows;
  $('content').innerHTML = `
    <div class="flex-between" style="margin-bottom:16px;gap:12px;flex-wrap:wrap">
      <div class="flex-gap" style="flex-wrap:wrap">
        ${tabs.map(([id,label])=>`<button class="btn btn-sm ${_purchaseTab===id?'btn-primary':'btn-default'}" onclick="purchaseTab('${id}')">${label}</button>`).join('')}
      </div>
      <div class="flex-gap" style="flex-wrap:wrap">
        <select style="width:auto" onchange="_purchaseStatusFilter=this.value;renderCompras()">
          <option value="">Todos os status</option>
          ${['Rascunho','Aguardando aprovacao do Gerente de TI','Aguardando aprovacao do Diretor','Aguardando envio para Suprimentos','Enviada para Suprimentos','Compra iniciada','Pedido de compra emitido','Aguardando entrega','Recebida parcialmente','Entrada no estoque realizada','Concluida','Reprovada'].map(s=>`<option ${_purchaseStatusFilter===s?'selected':''}>${s}</option>`).join('')}
        </select>
        <button class="btn btn-primary" onclick="openPurchaseForm()">Nova solicitacao</button>
      </div>
    </div>
    ${_purchaseTab === 'alcadas' ? purchaseRulesHtml(rules, false) : purchaseListHtml(filtered)}
  `;
}

function purchaseListHtml(rows){
  if(!rows.length) return `<div class="card"><p style="color:var(--text3);margin:0">Nenhuma solicitacao encontrada.</p></div>`;
  return `<div class="card" style="padding:0;overflow:hidden">
    <table><thead><tr><th>Solicitacao</th><th>Solicitante</th><th>Unidade</th><th>Valor</th><th>Status</th><th>Itens</th><th>Acoes</th></tr></thead><tbody>
      ${rows.map(r=>`<tr>
        <td><strong>${esc(r.numero)}</strong><div style="font-size:11px;color:var(--text3)">${fmtDateTime(r.createdAt)}</div></td>
        <td>${esc(r.solicitante)}</td>
        <td>${esc(r.unidade||'-')}<div style="font-size:11px;color:var(--text3)">${esc(r.centroCusto||'')}</div></td>
        <td>${fmtCur(r.valorAprovado || r.valorEstimado)}</td>
        <td>${purchaseStatusBadge(r.status)}</td>
        <td>${r.itemCount||0}</td>
        <td><div class="flex-gap" style="flex-wrap:wrap">
          <button class="btn btn-default btn-sm" onclick="openPurchaseDetail('${r.id}')">Abrir</button>
          ${r.status==='Rascunho'||r.status==='Devolvida para correcao'?`<button class="btn btn-primary btn-sm" onclick="submitPurchase('${r.id}')">Enviar</button>`:''}
          ${r.status&&r.status.startsWith('Aguardando aprovacao')?`<button class="btn btn-success btn-sm" onclick="openApprovePurchase('${r.id}')">Aprovar</button>`:''}
          ${r.status==='Aguardando envio para Suprimentos'?`<button class="btn btn-primary btn-sm" onclick="sendPurchaseProcurement('${r.id}')">Suprimentos</button>`:''}
          ${['Enviada para Suprimentos','Em analise por Suprimentos','Compra iniciada','Em cotacao','Aguardando emissao do pedido','Pedido de compra emitido','Aguardando entrega','Recebida parcialmente'].includes(r.status)?`<button class="btn btn-warning btn-sm" onclick="openProcurementAction('${r.id}')">Atualizar</button>`:''}
          ${PURCHASE_RECEIPT_STATUSES.includes(r.status)?`<button class="btn btn-success btn-sm" onclick="openReceiptPurchase('${r.id}')">Receber</button>`:''}
        </div></td>
      </tr>`).join('')}
    </tbody></table>
  </div>`;
}

function purchaseRulesHtml(rules, compact=true){
  const list = rules.length ? rules.map(rule=>`
    <div class="alert-row" style="align-items:flex-start;padding:10px 0;gap:12px">
      <div style="flex:1;min-width:220px">
        <div style="font-size:13px;font-weight:700;color:var(--text)">${esc(rule.nome)}</div>
        <div style="font-size:11px;color:var(--text3);margin-top:3px">
          ${fmtCur(rule.valorMinimo)} ate ${rule.valorMaximo==null?'sem limite':fmtCur(rule.valorMaximo)} · ordem ${rule.ordemAprovacao} · ${esc(rule.permissionCode||rule.perfilAprovador||rule.usuarioAprovadorId||'-')}
        </div>
        <div style="font-size:11px;color:var(--text3);margin-top:3px">${rule.obrigatoria?'Obrigatoria':'Opcional'} · ${rule.ativa?'Ativa':'Inativa'}</div>
      </div>
      <div class="flex-gap">
        <button class="btn btn-default btn-sm" onclick='openPurchaseRule(${JSON.stringify(rule).replace(/'/g,"&#39;")})'>Editar</button>
        <button class="btn btn-danger btn-sm" onclick="deletePurchaseRule('${rule.id}')">Excluir</button>
      </div>
    </div>`).join('') : `<div style="font-size:12px;color:var(--text3);padding:8px 0">Nenhuma regra cadastrada.</div>`;
  return `<div class="card">
    <div class="flex-between" style="margin-bottom:12px;gap:12px;flex-wrap:wrap">
      <div><div class="section-title" style="margin-bottom:4px">Alcadas de aprovacao</div>
      <div style="font-size:12px;color:var(--text3)">As regras sao configuraveis e congeladas na solicitacao quando ela e enviada.</div></div>
      <button class="btn btn-primary btn-sm" onclick="openPurchaseRule()">Nova regra</button>
    </div>
    ${list}
  </div>`;
}

function purchaseItemFormHtml(idx=1, supplies=[]){
  return `<div class="card purchase-item-form" style="margin-top:10px;background:var(--bg3)">
    <div class="form-grid-2">
      <div class="form-group"><label>Produto</label><input data-pf="produto" placeholder="Notebook Dell Latitude"></div>
      <div class="form-group"><label>Tipo de item</label><select data-pf="tipoItem"><option>INSUMO</option><option>PATRIMONIAL</option><option>LICENCA</option><option>SERVICO</option></select></div>
      <div class="form-group"><label>Categoria</label><input data-pf="categoria" placeholder="Notebook"></div>
      <div class="form-group"><label>Insumo vinculado</label><select data-pf="supplyId">${purchaseSupplyOptions(supplies)}</select></div>
      <div class="form-group"><label>Quantidade</label><input data-pf="quantidadeSolicitada" type="number" min="1" value="1"></div>
      <div class="form-group"><label>Valor unitario estimado</label><input data-pf="valorUnitarioEstimado" type="number" min="0" step="0.01" value="0"></div>
      <div class="form-group"><label>Marca sugerida</label><input data-pf="marcaSugerida"></div>
      <div class="form-group"><label>Modelo sugerido</label><input data-pf="modeloSugerido"></div>
      <div class="form-group" style="grid-column:span 2"><label>Especificacao tecnica</label><textarea data-pf="especificacao" style="min-height:70px;resize:vertical"></textarea></div>
      <div class="form-group" style="grid-column:span 2"><label>Link principal de referencia (HTTPS)</label><input data-pf="linkUrl" placeholder="https://..."></div>
      <div class="form-group"><label>Descricao do link</label><input data-pf="linkDescricao" placeholder="Pagina do fabricante, fornecedor A..."></div>
      <div class="form-group"><label>Fornecedor/site</label><input data-pf="linkFornecedor"></div>
      <div class="form-group" style="grid-column:span 2"><label>Justificativa</label><textarea data-pf="justificativa" style="min-height:60px;resize:vertical"></textarea></div>
    </div>
  </div>`;
}

async function openPurchaseForm(){
  const supplies = await purchaseSupplies();
  window._purchaseFormSupplies = supplies;
  const unidades = (_settings.unidades||[]).map(u=>typeof u==='string'?u:u.nome).filter(Boolean);
  const centers = (_settings.compras?.default_cost_centers||[]);
  openModal('Nova solicitacao de compra', `
    <div class="form-grid-2">
      <div class="form-group"><label>Solicitante</label><input id="pc-solicitante" value="${escAttr(_currentUser?.nome||'')}"></div>
      <div class="form-group"><label>Prioridade</label><select id="pc-prioridade"><option>Normal</option><option>Alta</option><option>Urgente</option><option>Baixa</option></select></div>
      <div class="form-group"><label>Unidade</label><select id="pc-unidade"><option value=""></option>${unidades.map(u=>`<option>${esc(u)}</option>`).join('')}</select></div>
      <div class="form-group"><label>Centro de custo</label><select id="pc-centro"><option value=""></option>${centers.map(c=>`<option>${esc(c)}</option>`).join('')}</select></div>
      <div class="form-group"><label>Categoria de compra</label><input id="pc-categoria" placeholder="TI, Perifericos, Licencas..."></div>
      <div class="form-group"><label>Prazo desejado</label><input id="pc-prazo" type="date"></div>
      <div class="form-group" style="grid-column:span 2"><label>Justificativa geral</label><textarea id="pc-just" style="min-height:80px;resize:vertical"></textarea></div>
    </div>
    <div class="flex-between" style="margin-top:8px"><div class="section-title" style="margin:0">Itens</div><button class="btn btn-default btn-sm" onclick="addPurchaseItemForm()" type="button">Adicionar item</button></div>
    <div id="pc-items">${purchaseItemFormHtml(1, supplies)}</div>
    <div id="pc-feedback" class="info-box red" style="display:none;margin-top:12px"></div>
    <div class="modal-footer"><button class="btn btn-default" onclick="closeModal()">Cancelar</button><button id="pc-save-btn" class="btn btn-primary" onclick="savePurchase()">Criar solicitacao</button></div>
  `, true);
}

function addPurchaseItemForm(){ $('pc-items').insertAdjacentHTML('beforeend', purchaseItemFormHtml(document.querySelectorAll('.purchase-item-form').length+1, window._purchaseFormSupplies||[])); }

function getPurchasePayload(){
  const items = Array.from(document.querySelectorAll('.purchase-item-form')).map(box=>{
    const val = f => box.querySelector(`[data-pf="${f}"]`)?.value || '';
    const linkUrl = val('linkUrl').trim();
    return {
      produto: val('produto'), tipoItem: val('tipoItem'), supplyId: val('supplyId'), categoria: val('categoria'), quantidadeSolicitada: Number(val('quantidadeSolicitada')||1),
      valorUnitarioEstimado: Number(val('valorUnitarioEstimado')||0), marcaSugerida: val('marcaSugerida'), modeloSugerido: val('modeloSugerido'),
      especificacao: val('especificacao'), justificativa: val('justificativa'),
      links: linkUrl ? [{url:linkUrl, descricao:val('linkDescricao'), fornecedor:val('linkFornecedor'), linkPrincipal:true}] : []
    };
  });
  return {solicitante:$('pc-solicitante').value, prioridade:$('pc-prioridade').value, unidade:$('pc-unidade').value,
    centroCusto:$('pc-centro').value, categoria:$('pc-categoria').value, prazoDesejado:$('pc-prazo').value,
    justificativa:$('pc-just').value, items};
}

async function savePurchase(){
  const btn = $('pc-save-btn');
  const feedback = $('pc-feedback');
  const showError = (msg, notify=true) => {
    if(feedback){
      feedback.style.display = 'block';
      feedback.textContent = msg;
    }
    if(notify) toast(msg, 'error');
  };
  if(feedback){
    feedback.style.display = 'none';
    feedback.textContent = '';
  }
  const payload = getPurchasePayload();
  const firstEmptyItem = (payload.items || []).findIndex(i=>!String(i.produto||'').trim());
  if(!String(payload.solicitante||'').trim()){
    showError('Informe o solicitante.');
    $('pc-solicitante')?.focus();
    return;
  }
  if(firstEmptyItem >= 0){
    showError(`Item ${firstEmptyItem+1}: informe o produto.`);
    document.querySelectorAll('.purchase-item-form')[firstEmptyItem]?.querySelector('[data-pf="produto"]')?.focus();
    return;
  }
  try{
    if(btn){
      btn.disabled = true;
      btn.dataset.originalText = btn.textContent;
      btn.textContent = 'Criando...';
    }
    await api('/purchases','POST',payload);
    toast('Solicitacao criada');
    closeModal();
    await renderCompras();
  }catch(e){
    showError(e.message || 'Nao foi possivel criar a solicitacao.', false);
  }finally{
    if(btn){
      btn.disabled = false;
      btn.textContent = btn.dataset.originalText || 'Criar solicitacao';
    }
  }
}
async function submitPurchase(id){ await api(`/purchases/${id}/submit`,'POST',{}); toast('Enviada para aprovacao'); renderCompras(); }
async function sendPurchaseProcurement(id){ await api(`/purchases/${id}/send-procurement`,'POST',{}); toast('Enviada para Suprimentos'); renderCompras(); }

async function openPurchaseDetail(id){
  const r = await api(`/purchases/${id}`);
  openModal(`${r.numero} · ${r.status}`, `
    <div class="grid-3" style="margin-bottom:14px">
      <div class="card"><div style="font-size:11px;color:var(--text3)">Solicitante</div><strong>${esc(r.solicitante)}</strong></div>
      <div class="card"><div style="font-size:11px;color:var(--text3)">Valor aprovado</div><strong>${fmtCur(r.valorAprovado||r.valorEstimado)}</strong></div>
      <div class="card"><div style="font-size:11px;color:var(--text3)">Status</div>${purchaseStatusBadge(r.status)}</div>
    </div>
    <div class="section-title">Itens</div>
    ${(r.items||[]).map(i=>`<div class="card" style="margin-bottom:10px"><strong>${esc(i.produto)}</strong><div style="font-size:12px;color:var(--text2);margin-top:4px">${esc(i.tipoItem||'INSUMO')} · Qtd ${i.quantidadeSolicitada} · recebido ${i.quantidadeRecebida||0} · ${fmtCur(i.valorTotalEstimado)}</div><div style="font-size:12px;color:var(--text3);margin-top:4px">${esc(i.especificacao||i.justificativa||'')}</div>${(i.links||[]).map(l=>`<a class="btn btn-default btn-sm" href="${escAttr(l.url)}" target="_blank" rel="noopener noreferrer" style="margin-top:8px">Abrir referencia</a>`).join('')}</div>`).join('')}
    <div class="section-title">Historico</div>
    ${[...(r.approvalSteps||[]),...(r.approvals||[]),...(r.actions||[]),...(r.receipts||[])].map(h=>`<div class="alert-row" style="padding:8px 0"><div style="flex:1"><strong>${esc(h.decisao||h.acao||h.status||('Recebimento '+(h.quantidade||'')))}</strong><div style="font-size:11px;color:var(--text3)">${fmtDateTime(h.decidedAt||h.approvedAt||h.createdAt||h.receivedAt)} · ${esc(h.aprovadorNome||h.responsavelNome||h.recebidoPorNome||'')}</div></div></div>`).join('')||'<div style="font-size:12px;color:var(--text3)">Sem historico.</div>'}
    <div class="modal-footer"><button class="btn btn-default" onclick="closeModal()">Fechar</button></div>
  `, true);
}

function openApprovePurchase(id){
  openModal('Aprovar solicitacao', `
    <div class="form-group"><label>Decisao</label><select id="pa-decisao"><option>Aprovada</option><option>Aprovada parcialmente</option><option>Reprovada</option><option>Devolvida para correcao</option></select></div>
    <div class="form-group"><label>Valor aprovado (opcional)</label><input id="pa-valor" type="number" min="0" step="0.01"></div>
    <div class="form-group"><label>Justificativa / parecer</label><textarea id="pa-just" style="min-height:90px;resize:vertical"></textarea></div>
    <div class="modal-footer"><button class="btn btn-default" onclick="closeModal()">Cancelar</button><button class="btn btn-primary" onclick="approvePurchase('${id}')">Salvar decisao</button></div>
  `, false, true);
}
async function approvePurchase(id){ await api(`/purchases/${id}/approve`,'POST',{decisao:$('pa-decisao').value,valorAprovado:$('pa-valor').value,justificativa:$('pa-just').value}); toast('Decisao registrada'); closeModal(); renderCompras(); }

function openProcurementAction(id){
  openModal('Atualizar Suprimentos', `
    <div class="form-grid-2">
      <div class="form-group"><label>Novo status</label><select id="ps-status">${['Compra iniciada','Em cotacao','Aguardando emissao do pedido','Pedido de compra emitido','Aguardando entrega','Recebida parcialmente','Recebida','Entrada no estoque realizada','Concluida','Devolvida para correcao','Cancelada'].map(s=>`<option>${s}</option>`).join('')}</select></div>
      <div class="form-group"><label>Responsavel pela compra</label><input id="ps-resp" value="${escAttr(_currentUser?.nome||'')}"></div>
      <div class="form-group"><label>Fornecedor</label><input id="ps-forn"></div>
      <div class="form-group"><label>Numero da compra</label><input id="ps-num"></div>
      <div class="form-group"><label>Numero do pedido</label><input id="ps-pedido"></div>
      <div class="form-group"><label>Previsao de entrega</label><input id="ps-entrega" type="date"></div>
      <div class="form-group"><label>Valor final</label><input id="ps-valor" type="number" min="0" step="0.01"></div>
      <div class="form-group" style="grid-column:span 2"><label>Observacao</label><textarea id="ps-obs" style="min-height:80px;resize:vertical"></textarea></div>
    </div>
    <div class="modal-footer"><button class="btn btn-default" onclick="closeModal()">Cancelar</button><button class="btn btn-primary" onclick="saveProcurementAction('${id}')">Salvar</button></div>
  `, true);
}
async function saveProcurementAction(id){
  await api(`/purchases/${id}/procurement-action`,'POST',{status:$('ps-status').value,responsavelCompra:$('ps-resp').value,fornecedorFinal:$('ps-forn').value,numeroCompra:$('ps-num').value,numeroPedido:$('ps-pedido').value,previsaoEntrega:$('ps-entrega').value,valorReal:$('ps-valor').value,observacao:$('ps-obs').value});
  toast('Suprimentos atualizado'); closeModal(); renderCompras();
}

async function openReceiptPurchase(id){
  const [r, supplies] = await Promise.all([api(`/purchases/${id}`), purchaseSupplies()]);
  const rows = (r.items||[]).map(i=>{
    const limit = Number(i.quantidadeAprovada || i.quantidadeSolicitada || 0);
    const received = Number(i.quantidadeRecebida || 0);
    const pending = Math.max(0, limit - received);
    return `<div class="card purchase-receipt-row" style="margin-bottom:10px;background:var(--bg3)" data-item-id="${escAttr(i.id)}">
      <div class="form-grid-2">
        <div><strong>${esc(i.produto)}</strong><div style="font-size:11px;color:var(--text3);margin-top:3px">${esc(i.tipoItem||'INSUMO')} · pendente ${pending}</div></div>
        <div class="form-group"><label>Quantidade recebida</label><input data-pr="quantidade" type="number" min="0" max="${pending}" value="${pending}"></div>
        <div class="form-group"><label>Insumo no estoque</label><select data-pr="supplyId">${purchaseSupplyOptions(supplies, i.supplyId||'')}</select></div>
        <div class="form-group"><label>Valor unitario real</label><input data-pr="valorUnitario" type="number" min="0" step="0.01" value="${i.valorUnitarioReal || i.valorUnitarioAprovado || i.valorUnitarioEstimado || 0}"></div>
      </div>
    </div>`;
  }).join('');
  openModal(`Receber ${r.numero}`, `
    <div class="form-grid-2">
      <div class="form-group"><label>Numero da nota</label><input id="rc-nota"></div>
      <div class="form-group"><label>Numero da compra</label><input id="rc-compra" value="${escAttr(r.numeroCompra||'')}"></div>
      <div class="form-group" style="grid-column:span 2"><label>Observacao</label><textarea id="rc-obs" style="min-height:70px;resize:vertical"></textarea></div>
    </div>
    <div class="section-title" style="margin-top:10px">Itens recebidos</div>
    ${rows || '<div style="font-size:12px;color:var(--text3)">Nenhum item encontrado.</div>'}
    <div class="modal-footer"><button class="btn btn-default" onclick="closeModal()">Cancelar</button><button class="btn btn-success" onclick="saveReceiptPurchase('${id}')">Registrar entrada</button></div>
  `, true);
}

async function saveReceiptPurchase(id){
  const items = Array.from(document.querySelectorAll('.purchase-receipt-row')).map(row=>({
    itemId: row.dataset.itemId,
    quantidade: Number(row.querySelector('[data-pr="quantidade"]')?.value || 0),
    supplyId: row.querySelector('[data-pr="supplyId"]')?.value || '',
    valorUnitario: row.querySelector('[data-pr="valorUnitario"]')?.value || '',
  })).filter(i=>i.quantidade>0);
  await api(`/purchases/${id}/receipts`,'POST',{numeroNota:$('rc-nota').value,numeroCompra:$('rc-compra').value,observacao:$('rc-obs').value,items});
  toast('Recebimento registrado'); closeModal(); renderCompras();
}

function openPurchaseRule(rule=null){
  rule = rule || {nome:'',valorMinimo:0,valorMaximo:'',ordemAprovacao:1,permissionCode:'compras.aprovar_gerente',perfilAprovador:'',obrigatoria:true,ativa:true};
  openModal(rule.id?'Editar alcada':'Nova alcada', `
    <div class="form-grid-2">
      <div class="form-group" style="grid-column:span 2"><label>Nome da regra</label><input id="pr-nome" value="${escAttr(rule.nome||'')}"></div>
      <div class="form-group"><label>Valor inicial</label><input id="pr-min" type="number" step="0.01" value="${rule.valorMinimo||0}"></div>
      <div class="form-group"><label>Valor final</label><input id="pr-max" type="number" step="0.01" value="${escAttr(rule.valorMaximo ?? '')}" placeholder="Sem limite"></div>
      <div class="form-group"><label>Ordem</label><input id="pr-ordem" type="number" min="1" value="${rule.ordemAprovacao||1}"></div>
      <div class="form-group"><label>Permissao</label><select id="pr-perm"><option value="compras.aprovar_gerente" ${rule.permissionCode==='compras.aprovar_gerente'?'selected':''}>compras.aprovar_gerente</option><option value="compras.aprovar_diretor" ${rule.permissionCode==='compras.aprovar_diretor'?'selected':''}>compras.aprovar_diretor</option></select></div>
      <div class="form-group"><label>Perfil aprovador</label><input id="pr-perfil" value="${escAttr(rule.perfilAprovador||'')}"></div>
      <div class="form-group"><label>Unidade</label><input id="pr-unidade" value="${escAttr(rule.unidade||'')}"></div>
      <div class="form-group"><label>Centro de custo</label><input id="pr-centro" value="${escAttr(rule.centroCusto||'')}"></div>
      <div class="form-group"><label>Categoria</label><input id="pr-cat" value="${escAttr(rule.categoria||'')}"></div>
      <div style="display:flex;align-items:center;gap:10px"><input id="pr-obg" type="checkbox" ${rule.obrigatoria?'checked':''} style="width:auto"><label for="pr-obg" style="margin:0">Obrigatoria</label></div>
      <div style="display:flex;align-items:center;gap:10px"><input id="pr-ativa" type="checkbox" ${rule.ativa?'checked':''} style="width:auto"><label for="pr-ativa" style="margin:0">Ativa</label></div>
      <div class="form-group" style="grid-column:span 2"><label>Observacoes</label><textarea id="pr-obs" style="min-height:70px;resize:vertical">${esc(rule.observacao||'')}</textarea></div>
    </div>
    <div class="modal-footer"><button class="btn btn-default" onclick="closeModal()">Cancelar</button><button class="btn btn-primary" onclick="savePurchaseRule('${rule.id||''}')">Salvar</button></div>
  `, true);
}

function getPurchaseRulePayload(){ return {nome:$('pr-nome').value,valorMinimo:$('pr-min').value,valorMaximo:$('pr-max').value,ordemAprovacao:$('pr-ordem').value,permissionCode:$('pr-perm').value,perfilAprovador:$('pr-perfil').value,unidade:$('pr-unidade').value,centroCusto:$('pr-centro').value,categoria:$('pr-cat').value,obrigatoria:$('pr-obg').checked,ativa:$('pr-ativa').checked,observacao:$('pr-obs').value}; }
async function savePurchaseRule(id){ await api(id?`/purchases/approval-rules/${id}`:'/purchases/approval-rules', id?'PUT':'POST', getPurchaseRulePayload()); toast('Alcada salva'); closeModal(); if(_currentModuleIsConfig()) renderConfiguracoes(); else renderCompras(); }
async function deletePurchaseRule(id){ if(!confirm('Excluir esta regra?')) return; await api(`/purchases/approval-rules/${id}`,'DELETE'); toast('Regra excluida'); if(_currentModuleIsConfig()) renderConfiguracoes(); else renderCompras(); }
function _currentModuleIsConfig(){ return localStorage.getItem('ticontrol-current-module') === 'configuracoes'; }

async function renderPurchaseSettingsPanel(cfg={}){
  const el = $('purchase-settings-panel');
  if(!el) return;
  const rules = await api('/purchases/approval-rules').catch(()=>[]);
  const centers = (cfg.default_cost_centers||[]).join('\n');
  el.innerHTML = `
    <div class="card">
      <div class="flex-between" style="gap:14px;align-items:flex-start;flex-wrap:wrap;margin-bottom:16px">
        <div><div class="section-title" style="margin-bottom:4px">Modulo de Compras e Reposicao</div><div style="font-size:12px;color:var(--text3)">Habilite o menu independente e configure o fluxo inicial de alcadas.</div></div>
        <label class="switch-control" for="compras-enabled"><input type="checkbox" id="compras-enabled" ${cfg.enabled?'checked':''}><span class="switch-slider"></span><span><span class="switch-title">${cfg.enabled?'Ativo':'Inativo'}</span><span class="switch-sub">Menu Compras</span></span></label>
      </div>
      <div class="form-grid-2">
        <div style="display:flex;align-items:center;gap:10px"><input id="compras-auto" type="checkbox" ${cfg.auto_send_to_procurement?'checked':''} style="width:auto"><label for="compras-auto" style="margin:0">Enviar automaticamente para Suprimentos apos ultima aprovacao</label></div>
        <div style="display:flex;align-items:center;gap:10px"><input id="compras-email" type="checkbox" ${cfg.notify_email?'checked':''} style="width:auto"><label for="compras-email" style="margin:0">Notificar por e-mail quando houver SMTP ativo</label></div>
        <div class="form-group" style="grid-column:span 2"><label>Centros de custo padrao (um por linha)</label><textarea id="compras-centers" style="min-height:90px;resize:vertical">${esc(centers)}</textarea></div>
      </div>
      <button class="btn btn-primary btn-sm" onclick="savePurchaseSettings()">Salvar configuracao de Compras</button>
    </div>
    ${purchaseRulesHtml(rules, true)}
  `;
}

async function savePurchaseSettings(){
  const centers = ($('compras-centers')?.value||'').split('\n').map(s=>s.trim()).filter(Boolean);
  const enabled = $('compras-enabled').checked;
  const compras = {
    enabled,
    auto_send_to_procurement: $('compras-auto').checked,
    notify_email: $('compras-email').checked,
    default_cost_centers: centers,
  };
  await api('/settings','PUT',{compras});
  _settings.compras = compras;
  if(_currentUser?.perfil === 'Administrador' && _allowedModules){
    if(enabled) _allowedModules.add('compras'); else _allowedModules.delete('compras');
    applyProfileNavigation({..._currentUser, uiModules:Array.from(_allowedModules)});
  }
  toast('Configuracao de compras salva');
  renderConfiguracoes();
}
