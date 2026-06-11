// ══════════════════════════════════════════════════════════════════════════
// INSUMOS
// ══════════════════════════════════════════════════════════════════════════
async function renderInsumos(q=''){
  const data=await api('/supplies?q='+encodeURIComponent(q));
  $('content').innerHTML=`
  <div class="flex-between mb-16">
    <div class="search-wrap"><span class="search-icon">${inlineIcon('search')}</span>
      <input placeholder="Buscar insumo..." value="${esc(q)}" onkeyup="debounce(()=>renderInsumos(this.value))">
    </div>
    <button class="btn btn-primary" onclick="openNewSupply()">Novo Item</button>
  </div>
  <div class="card">
    <div class="table-wrap"><table>
      <thead><tr><th>ID</th><th>Nome</th><th>Categoria</th><th>Unidade</th><th>Estoque</th><th>Mínimo</th><th>Situação</th><th>Preço</th><th>Ações</th></tr></thead>
      <tbody>${data.map(s=>{
        const sit=s.estoque===0?'red':s.estoque<=s.minimo?'amber':'green';
        const sitTxt=s.estoque===0?'Esgotado':s.estoque<=s.minimo?'Baixo':'OK';
        return `<tr>
          <td class="mono" style="color:var(--text3)">${esc(s.id)}</td>
          <td style="font-weight:600">${esc(s.nome)}</td>
          <td>${badge(s.categoria,'gray')}</td>
          <td>${esc(s.unidade)}</td>
          <td style="font-weight:700">${s.estoque}</td>
          <td>${s.minimo}</td>
          <td>${badge(sitTxt,sit)}</td>
          <td>${fmtCur(s.preco)}</td>
          <td><div class="flex-gap">
            <button class="btn btn-success btn-sm" onclick="openEntrada('${s.id}','${esc(s.nome)}')">Entrada</button>
            <button class="btn btn-danger btn-sm" onclick="openSaida('${s.id}','${esc(s.nome)}')">Saída</button>
            <button class="btn btn-default btn-icon btn-sm" onclick="openEditSupply(${JSON.stringify(s).replace(/"/g,'&quot;')})">Editar</button>
          </div></td>
        </tr>`;}).join('')}
      </tbody>
    </table></div>
  </div>`;
}

// ── Entrada modal ──────────────────────────────────────────────────────────
function openEntrada(id, nome){
  openModal('Entrada de Estoque', `
  <p style="font-size:13px;font-weight:600;margin-bottom:14px;color:var(--text2)">${esc(nome)}</p>
  <div class="form-group"><label>Quantidade</label><input id="e-qty" type="number" min="1" value="1"></div>
  <div class="form-group"><label>Motivo</label>
    <select id="e-motivo"><option>Compra</option><option>Devolução</option><option>Ajuste</option><option>Outro</option></select>
  </div>
  <div class="modal-footer">
    <button class="btn btn-default" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-success" onclick="doEntrada('${id}')">Confirmar Entrada</button>
  </div>`,false,true);
}
async function doEntrada(id){
  try{
    await api(`/supplies/${id}/entrada`,'POST',{quantidade:+$('e-qty').value,motivo:$('e-motivo').value});
    toast('Entrada registrada'); closeModal(); renderInsumos();
  }catch(e){toast(e.message,'error');}
}

// ── Saída modal (OBRIGATÓRIO colaborador ou ativo) ─────────────────────────
async function openSaida(id, nome){
  const [colabs,assets]=await Promise.all([api('/colaboradores'),api('/assets')]);
  openModal(`Saída: ${nome}`, `
  <div class="info-box amber">Atenção: Toda saída deve ser vinculada a um <strong>colaborador</strong> ou a um <strong>ativo de TI</strong>.</div>
  <div class="form-group"><label>Quantidade</label><input id="s-qty" type="number" min="1" value="1"></div>
  <div class="form-group"><label>Motivo</label>
    <select id="s-motivo"><option>Uso</option><option>Admissão</option><option>Manutenção</option><option>Substituição</option><option>Outro</option></select>
  </div>
  <hr class="divider">
  <div style="font-size:12px;font-weight:600;color:var(--text2);margin-bottom:10px">VINCULAR A: (preencha um dos campos abaixo)</div>
  <div class="form-group">
    <label>Colaborador</label>
    <select id="s-colab">
      <option value="">— Selecione um colaborador —</option>
      ${colabs.filter(c=>c.status==='Ativo'||c.status==='Férias').map(c=>`<option value="${esc(c.nome)}">${esc(c.nome)} (${esc(c.setor)})</option>`).join('')}
    </select>
  </div>
  <div style="text-align:center;font-size:12px;color:var(--text3);margin:-6px 0 8px">— ou —</div>
  <div class="form-group">
    <label>Ativo de TI</label>
    <select id="s-ativo">
      <option value="">— Selecione um ativo —</option>
      ${assets.map(a=>`<option value="${a.id}">${esc(a.hostname)} — ${esc(a.fabricante)} ${esc(a.modelo)}</option>`).join('')}
    </select>
  </div>
  <div class="modal-footer">
    <button class="btn btn-default" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-danger" onclick="doSaida('${id}')">Confirmar Saída</button>
  </div>`,true);
}
async function doSaida(id){
  const colab=$('s-colab').value; const ativo=$('s-ativo').value;
  if(!colab&&!ativo){ toast('Vincule a um colaborador ou ativo','error'); return; }
  try{
    await api(`/supplies/${id}/saida`,'POST',{quantidade:+$('s-qty').value,motivo:$('s-motivo').value,colaborador:colab,ativoId:ativo});
    toast('Saída registrada'); closeModal(); renderInsumos();
  }catch(e){toast(e.message,'error');}
}

function _supplyCatOpts(sel=''){
  const cats = (_settings.categorias_insumos && _settings.categorias_insumos.length)
    ? _settings.categorias_insumos
    : ['Periférico','Cabo','Insumo','Componente','Toner','Papel','Bateria','Adaptador'];
  return cats.map(c=>`<option ${c===sel?'selected':''}>${esc(c)}</option>`).join('');
}
function openNewSupply(){
  openModal('Novo Insumo / Periférico',`
  <div class="form-group"><label>Nome do Item</label><input id="f-nome" placeholder="Ex: Mouse USB Logitech M90"></div>
  <div class="form-grid-2">
    <div class="form-group"><label>Categoria</label>
      <select id="f-cat">${_supplyCatOpts()}</select>
    </div>
    <div class="form-group"><label>Unidade</label><input id="f-unidade" placeholder="Ex: Sede SP"></div>
    <div class="form-group"><label>Estoque Atual</label><input id="f-estoque" type="number" value="0"></div>
    <div class="form-group"><label>Estoque Mínimo</label><input id="f-minimo" type="number" value="2"></div>
    <div class="form-group span-2"><label>Preço (R$)</label><input id="f-preco" type="number" step="0.01" value="0"></div>
  </div>
  <div class="modal-footer">
    <button class="btn btn-default" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="saveNewSupply()">Salvar Item</button>
  </div>`);
}
function openEditSupply(s){
  openModal('Editar Item',`
  <div class="form-group"><label>Nome</label><input id="f-nome" value="${esc(s.nome)}"></div>
  <div class="form-grid-2">
    <div class="form-group"><label>Categoria</label>
      <select id="f-cat">${_supplyCatOpts(s.categoria)}</select>
    </div>
    <div class="form-group"><label>Unidade</label><input id="f-unidade" value="${esc(s.unidade)}"></div>
    <div class="form-group"><label>Estoque</label><input id="f-estoque" type="number" value="${s.estoque}"></div>
    <div class="form-group"><label>Mínimo</label><input id="f-minimo" type="number" value="${s.minimo}"></div>
    <div class="form-group span-2"><label>Preço</label><input id="f-preco" type="number" step="0.01" value="${s.preco}"></div>
  </div>
  <div class="modal-footer">
    <button class="btn btn-default" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="saveEditSupply('${s.id}')">Salvar</button>
  </div>`);
}
async function saveNewSupply(){
  await api('/supplies','POST',{nome:$('f-nome').value,categoria:$('f-cat').value,unidade:$('f-unidade').value,estoque:$('f-estoque').value,minimo:$('f-minimo').value,preco:$('f-preco').value});
  toast('Item cadastrado'); closeModal(); renderInsumos();
}
async function saveEditSupply(id){
  await api(`/supplies/${id}`,'PUT',{nome:$('f-nome').value,categoria:$('f-cat').value,unidade:$('f-unidade').value,estoque:$('f-estoque').value,minimo:$('f-minimo').value,preco:$('f-preco').value});
  toast('Item atualizado'); closeModal(); renderInsumos();
}

