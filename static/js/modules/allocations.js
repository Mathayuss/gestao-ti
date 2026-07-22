// ══════════════════════════════════════════════════════════════════════════
// ALOCAÇÕES
// ══════════════════════════════════════════════════════════════════════════
let _devCache = {};
let _laudoPendente = null;
let _newTermRowSeq = 0;

async function renderAlocacoes(q=''){
  const [data,assets,devs]=await Promise.all([
    api('/allocations?q='+encodeURIComponent(q)),
    api('/assets'),
    api('/devolucoes').catch(()=>[])
  ]);
  const avail=assets.filter(a=>a.status==='Disponível');

  const pendentes = data.filter(a=>a.termoStatus!=='Assinado');
  const assinados = data.filter(a=>a.termoStatus==='Assinado');

  _devCache = {};
  devs.forEach(d=>{ _devCache[d.id]=d; });

  const laudoBadge = s => {
    if(!s||s==='Aguardando Laudo') return `<span style="display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700;background:var(--amber-bg);color:var(--amber-text);border:1px solid var(--amber-border)">Aguardando Laudo</span>`;
    if(s==='Aguardando RH')        return `<span style="display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700;background:var(--blue-bg);color:var(--blue-text);border:1px solid var(--blue-border)">Aguardando RH</span>`;
    if(s==='Aprovado')             return `<span style="display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700;background:var(--green-bg);color:var(--green-text);border:1px solid var(--green-border)">RH Aprovado</span>`;
    return `<span style="display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700;background:var(--bg3);color:var(--text2)">${esc(s)}</span>`;
  };

  const devStatus = d => {
    if(d.status==='Assinado') return `<span style="display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700;background:var(--green-bg);color:var(--green-text);border:1px solid var(--green-border)">Assinado</span>`;
    return `<span style="display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700;background:var(--bg3);color:var(--text2)">Pendente</span>`;
  };

  const devAcoes = d => {
    const ls = d.laudoStatus||'Aguardando Laudo';
    const btns = [];
    if(ls==='Aguardando Laudo')
      btns.push(`<button class="btn btn-primary btn-sm" onclick="abrirLaudoPorId('${d.id}')">Registrar Laudo</button>`);
    if(ls==='Aguardando RH'){
      btns.push(`<span style="font-size:11px;color:var(--text3)">Aguardando ciência do RH</span>`);
      btns.push(`<button class="btn btn-default btn-sm" onclick="reenviarLaudoRh('${d.id}')" title="Reenviar link de ciência para o RH">Reenviar RH</button>`);
      btns.push(`<button class="btn btn-warning btn-sm" onclick="editarLaudo('${d.id}')" title="Corrigir laudo enviado ao RH">Editar Laudo</button>`);
    }
    if(ls==='Aprovado'){
      btns.push(`<button class="btn btn-warning btn-sm" onclick="editarLaudo('${d.id}')" title="Corrigir laudo após aprovação">Editar Laudo</button>`);
      if(d.status!=='Assinado')
        btns.push(`<button class="btn btn-default btn-sm" onclick="verQrDevolucao('${d.id}')">Enviar link</button>`);
    }
    if(d.status==='Assinado')
      btns.push(`<a class="btn btn-default btn-sm" href="/api/devolucoes/${d.id}/termo.pdf" target="_blank">PDF</a>`);
    return `<div class="flex-gap">${btns.join('')}</div>`;
  };

  const tipoBadge = a => {
    if((a.tipo||'Responsabilidade')==='Empréstimo'){
      const hoje = new Date().toISOString().slice(0,10);
      const venc = a.dataDevolucaoPrevista||'';
      const atrasado = venc && venc < hoje;
      return `<span style="display:inline-block;padding:2px 7px;border-radius:20px;font-size:10px;font-weight:700;
        background:${atrasado?'var(--red-bg)':'var(--amber-bg)'};
        color:${atrasado?'var(--red-text)':'var(--amber-text)'};
        border:1px solid ${atrasado?'var(--red-border)':'var(--amber-border)'}">
        ${atrasado?'Atrasado · ':''}Empréstimo${venc?' · '+venc:''}</span>`;
    }
    return '';
  };
  const ativosResumo = a => {
    const ativos = Array.isArray(a.ativos) && a.ativos.length ? a.ativos : [{nome:a.ativoNome||a.ativo||'—'}];
    const first = ativos[0]?.nome || ativos[0]?.id || '—';
    return ativos.length > 1 ? `${first.split(' ')[0]} + ${ativos.length-1}` : first.split(' ')[0];
  };

  const rowPend = a=>`<tr>
    <td class="mono" style="color:var(--text3);font-size:11px">${esc(a.id)}</td>
    <td style="font-weight:600">${esc(a.colaborador)}${tipoBadge(a)?'<br>'+tipoBadge(a):''}</td>
    <td class="mono" style="font-size:12px">${esc(ativosResumo(a))}</td>
    <td style="font-size:12px">${esc(a.setor)}</td>
    <td style="font-size:12px">${esc(a.unidade)}</td>
    <td style="font-size:12px">${fmtDate(a.dataAloc)}</td>
    <td>${badge(a.status)}</td>
    <td><div class="flex-gap">
      <button class="btn btn-default btn-sm" onclick="verQrTermo('${a.id}')" title="QR Code para assinatura remota">${inlineIcon('qrcode')} QR</button>
      <button class="btn btn-default btn-sm" onclick="viewTermo(${JSON.stringify(a).replace(/"/g,'&quot;')})">Termo</button>
    </div></td>
  </tr>`;

  const rowSign = a=>`<tr>
    <td class="mono" style="color:var(--text3);font-size:11px">${esc(a.id)}</td>
    <td style="font-weight:600">${esc(a.colaborador)}${tipoBadge(a)?'<br>'+tipoBadge(a):''}</td>
    <td class="mono" style="font-size:12px">${esc(ativosResumo(a))}</td>
    <td style="font-size:12px">${esc(a.setor)}</td>
    <td style="font-size:12px">${esc(a.unidade)}</td>
    <td style="font-size:12px">${fmtDate(a.dataAloc)}</td>
    <td>${badge(a.status)}</td>
    <td style="font-size:11px;color:var(--text3)">${fmtDateTime(a.dataAssinatura)||'—'}</td>
    <td><button class="btn btn-default btn-sm" onclick="viewTermo(${JSON.stringify(a).replace(/"/g,'&quot;')})">Termo</button></td>
  </tr>`;

  const rowDev = d=>`<tr>
    <td class="mono" style="color:var(--text3);font-size:11px">${esc(d.id)}</td>
    <td style="font-weight:600">${esc(d.colaborador)}</td>
    <td style="font-size:12px">${esc(d.setor||'—')}</td>
    <td style="font-size:12px">${fmtDate(d.dataDevolucao)}</td>
    <td>${laudoBadge(d.laudoStatus)}</td>
    <td>${devStatus(d)}</td>
    <td style="font-size:11px;color:var(--text3)">${fmtDateTime(d.dataAssinatura)||'—'}</td>
    <td>${devAcoes(d)}</td>
  </tr>`;

  const tabBtn = (id,label,count)=>`<button id="tab-alloc-${id}" onclick="allocTab('${id}')"
    style="padding:8px 18px;font-size:13px;font-weight:600;border:none;background:none;cursor:pointer;
           color:var(--text2);border-bottom:2px solid transparent;margin-bottom:-2px;font-family:inherit">
    ${label} <span style="font-size:11px;font-weight:700;opacity:.7">(${count})</span>
  </button>`;

  const devAguardando = devs.filter(d=>!d.laudoStatus||d.laudoStatus==='Aguardando Laudo').length;

  $('content').innerHTML=`
  <div class="flex-between mb-16">
    <div class="search-wrap"><span class="search-icon">${inlineIcon('search')}</span>
      <input placeholder="Colaborador, ativo, setor..." value="${esc(q)}" onkeyup="debounce(()=>renderAlocacoes(this.value))">
    </div>
    <div class="flex-gap">
      <a class="btn btn-default" href="/api/export/alocacoes.csv" download>Exportar CSV</a>
      <button class="btn btn-primary" onclick="openNewAlloc(${JSON.stringify(avail).replace(/"/g,'&quot;')})">Nova Alocação</button>
    </div>
  </div>

  <div style="display:flex;gap:0;margin-bottom:16px;border-bottom:2px solid var(--border)">
    ${tabBtn('pend','Pendentes',pendentes.length)}
    ${tabBtn('sign','Assinados',assinados.length)}
    ${tabBtn('devol',devAguardando>0?`Devoluções pendentes`:'Devoluções',devs.length)}
    ${tabBtn('avulso','Termos',0)}
  </div>

  <div id="panel-alloc-pend">
    ${pendentes.length===0
      ? `<div class="card" style="text-align:center;padding:28px;color:var(--text3);font-size:13px">
           ${inlineIcon('check')} Nenhum termo pendente — tudo assinado.
         </div>`
      : `<div class="card"><div class="table-wrap"><table>
           <thead><tr><th>ID</th><th>Colaborador</th><th>Ativo</th><th>Setor</th><th>Unidade</th><th>Data</th><th>Status</th><th>Ações</th></tr></thead>
           <tbody>${pendentes.map(rowPend).join('')}</tbody>
         </table></div></div>`}
  </div>

  <div id="panel-alloc-sign" style="display:none">
    ${assinados.length===0
      ? `<div class="card" style="text-align:center;padding:28px;color:var(--text3);font-size:13px">
           Nenhum termo assinado ainda.
         </div>`
      : `<div class="card"><div class="table-wrap"><table>
           <thead><tr><th>ID</th><th>Colaborador</th><th>Ativo</th><th>Setor</th><th>Unidade</th><th>Data Alocação</th><th>Status</th><th>Assinado em</th><th>Ações</th></tr></thead>
           <tbody>${assinados.map(rowSign).join('')}</tbody>
         </table></div></div>`}
  </div>

  <div id="panel-alloc-devol" style="display:none">
    ${devs.length===0
      ? `<div class="card" style="text-align:center;padding:28px;color:var(--text3);font-size:13px">Nenhuma devolução registrada.</div>`
      : `<div class="card"><div class="table-wrap"><table>
           <thead><tr><th>ID</th><th>Colaborador</th><th>Setor</th><th>Data</th><th>Laudo</th><th>Assinatura</th><th>Assinado em</th><th>Ações</th></tr></thead>
           <tbody>${devs.map(rowDev).join('')}</tbody>
         </table></div></div>`}
  </div>

  <div id="panel-alloc-avulso" style="display:none">
    <div id="termos-avulsos-content">
      <div style="text-align:center;padding:28px;color:var(--text3);font-size:13px">Carregando...</div>
    </div>
  </div>`;

  allocTab(_allocTab);
}

function allocTab(tab){
  _allocTab = tab;
  ['pend','sign','devol','avulso'].forEach(t=>{
    const btn = document.getElementById('tab-alloc-'+t);
    const panel = document.getElementById('panel-alloc-'+t);
    if(!btn||!panel) return;
    const active = t===tab;
    panel.style.display = active ? '' : 'none';
    btn.style.color = active ? 'var(--blue)' : 'var(--text2)';
    btn.style.borderBottomColor = active ? 'var(--blue)' : 'transparent';
    btn.style.fontWeight = active ? '700' : '600';
  });
  if(tab==='avulso') renderTermosAvulsos();
}

// ── Termos ────────────────────────────────────────────────────────────────

async function renderTermosAvulsos(q=''){
  const wrap = $('termos-avulsos-content');
  if(!wrap) return;
  try {
    const data = await api('/termos' + (q?'?q='+encodeURIComponent(q):''));
    _termoAvulsoTipos = Array.from(new Set([..._termoAvulsoTipos, ...data.map(t=>t.tipo).filter(Boolean)])).sort((a,b)=>a.localeCompare(b));
    const tipoBadgeAv = t => {
      const colors = {VPN:'blue',BYOD:'purple',Confidencialidade:'amber',Outro:'gray'};
      const c = colors[t.tipo] || 'gray';
      return `<span style="display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700;background:var(--${c==='gray'?'bg3':''+c+'-bg'});color:var(--${c==='gray'?'text2':c+'-text'});border:1px solid var(--${c==='gray'?'border':c+'-border'})">${esc(t.tipo)}</span>`;
    };
    const statusBadgeAv = t => t.status==='Assinado'
      ? `<span style="display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700;background:var(--green-bg);color:var(--green-text);border:1px solid var(--green-border)">Assinado</span>`
      : `<span style="display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700;background:var(--amber-bg);color:var(--amber-text);border:1px solid var(--amber-border)">Pendente</span>`;
    const renderedPackages = new Set();
    const termLinkAction = t => {
      if(t.status==='Assinado') return '';
      if(!t.packageId) return `<button class="btn btn-default btn-sm" onclick="gerarLinkTermoAvulso('${t.id}')">Link Assinatura</button>`;
      if(renderedPackages.has(t.packageId)) return '';
      renderedPackages.add(t.packageId);
      return `<button class="btn btn-default btn-sm" onclick="gerarLinkPacoteTermos('${t.packageId}')">Link do pacote</button>`;
    };

    // Update tab count
    const tabBtn = document.getElementById('tab-alloc-avulso');
    if(tabBtn){ const m = tabBtn.innerHTML.match(/^(.*)\s*\((\d+)\)$/s); if(m) tabBtn.innerHTML = tabBtn.innerHTML.replace(/\(\d+\)/,'('+data.length+')'); }

    wrap.innerHTML = `
    <div class="flex-between mb-16">
      <div class="search-wrap"><span class="search-icon">${inlineIcon('search')}</span>
        <input placeholder="Colaborador, tipo..." value="${esc(q)}" onkeyup="debounce(()=>renderTermosAvulsos(this.value))">
      </div>
      <button class="btn btn-primary" onclick="openNewTermoAvulso()">Novo Termo</button>
    </div>
    ${data.length===0
      ? `<div class="card" style="text-align:center;padding:28px;color:var(--text3);font-size:13px">Nenhum termo cadastrado.</div>`
      : `<div class="card"><div class="table-wrap"><table>
           <thead><tr><th>ID</th><th>Tipo</th><th>Colaborador</th><th>Setor</th><th>Validade</th><th>Status</th><th>Criado em</th><th>Ações</th></tr></thead>
           <tbody>${data.map(t=>`<tr>
             <td class="mono" style="color:var(--text3);font-size:11px">${esc(t.id)}</td>
             <td>${tipoBadgeAv(t)}${t.packageId?`<div class="mono" style="font-size:9px;color:var(--text3);margin-top:3px">${esc(t.packageId)}</div>`:''}</td>
             <td style="font-weight:600">${esc(t.colaborador)}</td>
             <td style="font-size:12px">${esc(t.setor||'—')}</td>
             <td style="font-size:12px">${esc(t.validade||'—')}</td>
             <td>${statusBadgeAv(t)}</td>
             <td style="font-size:11px;color:var(--text3)">${fmtDate(t.createdAt?.slice(0,10))}</td>
             <td><div class="flex-gap">
               ${termLinkAction(t)}
               <a class="btn btn-default btn-sm" href="/api/termos/${t.id}/termo.pdf" target="_blank">PDF</a>
               <button class="btn btn-danger btn-sm" onclick="deleteTermoAvulso('${t.id}','${escAttr(t.colaborador)}')">Excluir</button>
             </div></td>
           </tr>`).join('')}</tbody>
         </table></div></div>`}`;
  } catch(e) {
    wrap.innerHTML = `<div class="card" style="color:var(--red-text);padding:20px">Erro ao carregar termos.</div>`;
  }
}

async function openNewTermoAvulso(){
  const [colabs,cfg]=await Promise.all([
    _colab_cache.length?Promise.resolve(_colab_cache):api('/colaboradores').catch(()=>[]),
    api('/settings').catch(()=>({})),
  ]);
  _colab_cache=colabs;
  const modelTypes=Object.keys(cfg.termos_avulsos_modelos||{});
  _termoAvulsoTipos=Array.from(new Set([...(cfg.termos_avulsos_tipos||[]),...modelTypes])).filter(Boolean).sort((a,b)=>a.localeCompare(b));
  if(!_termoAvulsoTipos.length){ toast('Cadastre um modelo em Configurações > Termos.','warn'); return; }
  const colabOpts = _colab_cache.filter(c=>c.status==='Ativo'||c.status==='Férias');
  _newTermRowSeq=0;
  openModal('Novo Termo', `
  <div class="form-group"><label>Colaborador</label>
    <select id="tav-colab-sel" onchange="preencheColabAvulso(this.value)">
      <option value="">Selecione o colaborador...</option>
      ${colabOpts.map(c=>`<option value="${c.id}" data-nome="${escAttr(c.nome)}" data-setor="${escAttr(c.setor)}" data-uni="${escAttr(c.unidade)}" data-email="${escAttr(c.email)}">${esc(c.nome)} — ${esc(c.setor)}</option>`).join('')}
    </select>
  </div>
  <div class="form-grid-2">
    <div class="form-group"><label>Nome (confirmação)</label><input id="tav-colab" placeholder="Preenchido ao selecionar"></div>
    <div class="form-group"><label>Setor</label><input id="tav-setor"></div>
  </div>
  <div class="form-grid-2">
    <div class="form-group"><label>Unidade</label><input id="tav-uni"></div>
    <div class="form-group"><label>E-mail</label><input id="tav-email" type="email"></div>
  </div>
  <div style="border-top:1px solid var(--border);padding-top:14px">
    <div class="flex-between" style="margin-bottom:10px">
      <div><div style="font-size:13px;font-weight:800">Termos do pacote</div><div style="font-size:11px;color:var(--text3)">Modelos cadastrados em Configurações > Termos</div></div>
      <button class="btn btn-default btn-sm" type="button" onclick="addOutroTermoAvulso()">${inlineIcon('plus')} Adicionar outro termo</button>
    </div>
    <div id="tav-terms-list" style="display:grid;gap:8px"></div>
  </div>
  <div class="modal-footer">
    <button class="btn btn-default" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="saveNewTermoAvulso()">Criar e enviar</button>
  </div>`,true);
  addOutroTermoAvulso();
}

function preencheColabAvulso(id){
  const sel = $('tav-colab-sel');
  const opt = sel.options[sel.selectedIndex];
  if(!id) return;
  $('tav-colab').value = opt.dataset.nome||'';
  $('tav-setor').value = opt.dataset.setor||'';
  $('tav-uni').value   = opt.dataset.uni||'';
  $('tav-email').value = opt.dataset.email||'';
}

function addOutroTermoAvulso(){
  const list=$('tav-terms-list');
  if(!list) return;
  if(list.querySelectorAll('[data-term-row]').length>=_termoAvulsoTipos.length){ toast('Todos os modelos disponíveis já foram adicionados.','warn'); return; }
  const id=++_newTermRowSeq;
  const row=document.createElement('div');
  row.dataset.termRow=String(id);
  row.className='new-term-package-row';
  row.innerHTML=`
    <div class="form-group"><label>Modelo do termo</label><select data-term-type>${_termoAvulsoTipos.map(t=>`<option value="${escAttr(t)}">${esc(t)}</option>`).join('')}</select></div>
    <div class="form-group"><label>Validade</label><input data-term-validade type="date"></div>
    <button class="btn btn-danger btn-sm btn-icon" type="button" onclick="removeOutroTermoAvulso(this)" title="Remover termo" aria-label="Remover termo">${inlineIcon('trash')}</button>`;
  list.appendChild(row);
  const selects=[...list.querySelectorAll('[data-term-type]')];
  const used=new Set(selects.slice(0,-1).map(el=>el.value));
  selects.at(-1).value=_termoAvulsoTipos.find(t=>!used.has(t))||_termoAvulsoTipos[0];
}

function removeOutroTermoAvulso(button){
  const list=$('tav-terms-list');
  if(!list) return;
  if(list.querySelectorAll('[data-term-row]').length<=1){ toast('Mantenha ao menos um termo no pacote.','warn'); return; }
  button.closest('[data-term-row]')?.remove();
}

async function saveNewTermoAvulso(){
  const colab = $('tav-colab')?.value?.trim();
  if(!colab){ toast('Informe o colaborador','error'); return; }
  const termos=[...document.querySelectorAll('#tav-terms-list [data-term-row]')].map(row=>({
    tipo:row.querySelector('[data-term-type]')?.value||'',
    validade:row.querySelector('[data-term-validade]')?.value||null,
  }));
  if(new Set(termos.map(t=>t.tipo)).size!==termos.length){ toast('Não repita o mesmo termo no pacote.','error'); return; }
  try {
    const result=await api('/termos/pacotes','POST',{
      termos,
      colaborador: colab,
      setor: $('tav-setor').value,
      unidade: $('tav-uni').value,
      email: $('tav-email').value,
    });
    closeModal();
    showTermPackageLink(result,'Pacote criado');
    toast(`${termos.length} termo(s) criado(s)`);
    renderTermosAvulsos();
  } catch(e){ toast(e.message,'error'); }
}

function showTermPackageLink(result,title='Link do pacote'){
  openModal(title,`
    <div style="display:grid;gap:14px;padding:4px 0">
      <div class="info-box ${result.emailEnviado?'green':'blue'}" style="margin:0">${result.emailEnviado?'Um único e-mail foi enviado ao colaborador.':'O pacote foi criado. Compartilhe o link abaixo.'}</div>
      <div class="form-group" style="margin:0"><label>Central de Assinaturas</label><div style="display:flex;gap:8px"><input id="tav-package-url" value="${escAttr(result.url||'')}" readonly class="mono"><button class="btn btn-primary btn-sm" onclick="navigator.clipboard.writeText($('tav-package-url').value).then(()=>toast('Link copiado'))">Copiar</button></div></div>
      <div style="font-size:11px;color:var(--text3)">Expira em ${result.expiry?fmtDateTime(result.expiry):'7 dias'}.</div>
    </div>
    <div class="modal-footer"><button class="btn btn-primary" onclick="closeModal()">Concluir</button></div>`,true);
}

async function gerarLinkPacoteTermos(packageId){
  try{
    const result=await api(`/termos/pacotes/${encodeURIComponent(packageId)}/sign-link`,'POST',{});
    showTermPackageLink(result);
  }catch(e){ toast(e.message,'error'); }
}

async function deleteTermoAvulso(id, nome){
  if(!confirm(`Excluir termo de ${nome}?`)) return;
  try {
    await api(`/termos/${id}`,'DELETE',{});
    toast('Termo excluído');
    renderTermosAvulsos();
  } catch(e){ toast(e.message,'error'); }
}

async function gerarLinkTermoAvulso(id){
  try {
    const r = await api(`/termos/${id}/sign-link`,'POST',{});
    openModal('Link de Assinatura — Termo', `
    <div style="display:flex;flex-direction:column;gap:14px;align-items:center;padding:8px 0">
      <div style="font-size:13px;color:var(--text2)">Envie este link para o colaborador assinar:</div>
      <div style="width:100%;display:flex;gap:8px;align-items:center">
        <input id="tav-link-url" value="${esc(r.url)}" readonly
          style="flex:1;padding:9px 12px;border:1px solid var(--border);border-radius:var(--r);
                 font-size:11px;font-family:var(--mono);color:var(--text);background:var(--bg3)">
        <button class="btn btn-primary btn-sm" onclick="navigator.clipboard.writeText($('tav-link-url').value).then(()=>toast('Link copiado'))">Copiar</button>
      </div>
      <div style="font-size:11px;color:var(--text3)">Expira em: ${r.expiry?.slice(0,10)||'7 dias'}</div>
      ${r.emailEnviado?`<div style="font-size:12px;color:var(--green-text)">Link também enviado por e-mail ao colaborador.</div>`:''}
    </div>
    <div class="modal-footer">
      <button class="btn btn-default" onclick="closeModal()">Fechar</button>
    </div>`, false, true);
  } catch(e){ toast(e.message,'error'); }
}

// ── End Termos ────────────────────────────────────────────────────────────

async function abrirLaudoPorId(devId){
  let d = _devCache[devId];
  if(!d){
    d = await api(`/devolucoes/${devId}`).catch(()=>null);
    if(!d) return;
    _devCache[d.id] = d;
  }
  _laudoPendente = {devId:d.id, colaborador:d.colaborador, ativos:d.ativosDevolvidos||[], perifs:d.perifericosDevolvidos||[]};
  abrirLaudo();
}

async function editarLaudo(devId){
  // Sempre busca dado fresco para ter os dados do laudo incluídos
  const d = await api(`/devolucoes/${devId}`).catch(()=>null);
  if(!d) return;
  _devCache[d.id] = d;

  const laudoExistente = d.laudo;
  const laudoItensMap = {};
  if(laudoExistente){
    (laudoExistente.avaliacaoItens||[]).forEach(it=>{ laudoItensMap[it.ativo] = it; });
  }

  const todosItens = [...(d.ativosDevolvidos||[]), ...(d.perifericosDevolvidos||[])];
  const itens = todosItens.map(nome => {
    const prev = laudoItensMap[nome] || {};
    const estadoOpts = ['Bom estado','Dano','Mau uso','Perda'].map(op =>
      `<option value="${op}"${prev.estado===op?' selected':''}>${op}</option>`
    ).join('');
    return `<div style="display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid var(--border)">
      <span style="flex:1;font-size:13px">${esc(nome)}</span>
      <select data-ativo="${escAttr(nome)}" style="width:auto;font-size:12px;border:1px solid var(--border2);padding:3px 8px;border-radius:5px">
        ${estadoOpts}
      </select>
      <input placeholder="Observação" data-obs="${escAttr(nome)}" value="${escAttr(prev.observacao||'')}" style="width:160px;font-size:12px">
    </div>`;
  }).join('');

  openModal(`Editar Laudo — ${esc(d.colaborador)}`, `
    <div style="font-size:12px;color:var(--amber-text);background:var(--amber-bg);border:1px solid var(--amber-border);border-radius:var(--r);padding:10px 14px;margin-bottom:14px">
      <strong>Atenção:</strong> Esta ação corrige o laudo já enviado ao RH. A alteração será registrada com data, usuário e motivo.
    </div>
    <div class="form-group"><label>Avaliação dos Equipamentos</label>${itens || '<div style="color:var(--text3);font-size:12px">Nenhum item listado nesta devolução.</div>'}</div>
    <div class="form-group" style="margin-top:12px"><label>Observação geral</label>
      <textarea id="edit-laudo-obs" style="width:100%;min-height:70px;resize:vertical;padding:8px;border:1px solid var(--border);border-radius:var(--r);font-family:inherit;background:var(--bg2);color:var(--text)">${esc(laudoExistente?.observacaoGeral||'')}</textarea>
    </div>
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
      <input type="checkbox" id="edit-laudo-cobranca" style="width:auto"${laudoExistente?.temCobranca?' checked':''}>
      <label for="edit-laudo-cobranca" style="margin:0;font-size:13px">Recomendação de cobrança</label>
    </div>
    <div class="form-group"><label>Valor (R$)</label>
      <input id="edit-laudo-valor" type="number" step="0.01" min="0" value="${laudoExistente?.valorCobranca||0}" style="width:160px">
    </div>
    <div class="form-group"><label>Motivo da Correção <span style="color:var(--red-text)">*</span></label>
      <input id="edit-laudo-motivo" placeholder="Descreva o motivo da correção..." required>
    </div>
    <div class="modal-footer">
      <button class="btn btn-default" onclick="closeModal()">Cancelar</button>
      <button class="btn btn-warning" onclick="salvarEdicaoLaudo('${devId}')">Salvar Correção</button>
    </div>`, true);
}

async function salvarEdicaoLaudo(devId){
  const motivo = $('edit-laudo-motivo')?.value?.trim();
  if(!motivo){ toast('Motivo da correção é obrigatório','error'); return; }
  const temCobranca = $('edit-laudo-cobranca')?.checked || false;
  const valorCobranca = parseFloat($('edit-laudo-valor')?.value || 0);
  const obs = $('edit-laudo-obs')?.value?.trim() || '';
  const selects = document.querySelectorAll('[data-ativo]');
  const avaliacaoItens = Array.from(selects).map(sel => ({
    ativo: sel.dataset.ativo,
    estado: sel.value,
    observacao: document.querySelector(`[data-obs="${sel.dataset.ativo.replace(/"/g,'&quot;')}"]`)?.value || ''
  }));
  try{
    const r = await api(`/devolucoes/${devId}/laudo`, 'PUT', {
      avaliacaoItens, observacaoGeral: obs, temCobranca, valorCobranca, motivoCorrecao: motivo
    });
    const emailInfo = [];
    if(r.emailRHEnviado)    emailInfo.push('RH notificado');
    if(r.emailColabEnviado) emailInfo.push('colaborador notificado');
    const extra = emailInfo.length ? ` — ${emailInfo.join(' e ')} por e-mail` : (r.emailRHEnviado===false||r.emailColabEnviado===false?' — falha ao enviar e-mails':'');
    toast('Laudo corrigido com sucesso' + extra, 'success');
    closeModal();
    renderAlocacoes();
  }catch(e){ toast(e.message,'error'); }
}

async function reenviarLaudoRh(devId){
  const d = _devCache[devId] || await api(`/devolucoes/${devId}`).catch(()=>null);
  if(!d) return;
  const atual = d.rhEmail || '';
  openModal('Reenviar laudo para RH', `
    <div style="display:flex;flex-direction:column;gap:14px">
      <div class="info-box blue" style="margin:0">
        Confirme o e-mail do RH. Se o envio automático falhar, o sistema exibirá um link de backup para cópia manual.
      </div>
      <div class="form-group">
        <label>E-mail do RH</label>
        <input id="rh-resend-email" type="email" value="${escAttr(atual)}" placeholder="rh@empresa.com">
      </div>
      <div style="font-size:12px;color:var(--text3)">
        Devolução: <strong>${esc(d.colaborador)}</strong> · ${esc(d.setor||'—')} · ${fmtDate(d.dataDevolucao)}
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-default" onclick="closeModal()">Cancelar</button>
      <button id="btn-rh-resend" class="btn btn-primary" onclick="confirmarReenvioLaudoRh('${devId}')">Reenviar para RH</button>
    </div>`, false, true);
  setTimeout(()=>$('rh-resend-email')?.focus(),0);
}

async function confirmarReenvioLaudoRh(devId){
  const rhEmail = $('rh-resend-email')?.value?.trim() || '';
  if(!rhEmail){ toast('Informe o e-mail do RH.','error'); return; }
  const d = _devCache[devId] || {};
  const btn = $('btn-rh-resend');
  const emailInput = $('rh-resend-email');
  let loading = $('rh-resend-loading');
  if(!loading && emailInput){
    loading = document.createElement('div');
    loading.id = 'rh-resend-loading';
    loading.className = 'info-box blue';
    loading.style.margin = '0';
    loading.innerHTML = 'Enviando e-mail para o RH... aguarde alguns instantes.';
    emailInput.closest('.form-group')?.after(loading);
  }
  if(btn){
    btn.disabled = true;
    btn.textContent = 'Enviando...';
  }
  if(emailInput) emailInput.disabled = true;
  try{
    const r = await api(`/devolucoes/${devId}/reenviar-rh`, 'POST', {rhEmail});
    const expiry = r.expiry ? new Date(r.expiry).toLocaleDateString('pt-BR') : '7 dias';
    const statusHtml = r.emailEnviado
      ? `<div class="info-box green" style="margin:0">E-mail reenviado para <strong>${esc(r.rhEmail)}</strong>.</div>`
      : `<div class="info-box amber" style="margin:0">Não foi possível confirmar o envio por e-mail${r.emailErro?`: ${esc(r.emailErro)}`:''}. Use o link abaixo como backup.</div>`;
    openModal('Reenvio para RH', `
      <div style="display:flex;flex-direction:column;gap:14px">
        ${statusHtml}
        <div style="font-size:13px;color:var(--text2)">
          Link de ciência do RH válido até <strong>${expiry}</strong>.
        </div>
        <div style="width:100%;display:flex;gap:8px;align-items:center">
          <input id="rh-link-url" value="${esc(r.url)}" readonly
            style="flex:1;padding:9px 12px;border:1px solid var(--border);border-radius:var(--r);
                   font-size:11px;font-family:var(--mono);color:var(--text);background:var(--bg3)">
          <button class="btn btn-primary btn-sm" onclick="navigator.clipboard.writeText($('rh-link-url').value).then(()=>toast('Link copiado'))">Copiar</button>
        </div>
        <a href="${escAttr(r.url)}" target="_blank" style="font-size:12px;color:var(--blue)">Abrir link do RH em nova aba</a>
      </div>
      <div class="modal-footer">
        <button class="btn btn-default" onclick="closeModal()">Fechar</button>
      </div>`, false, true);
    _devCache[devId] = {...d, rhEmail: r.rhEmail};
    renderAlocacoes();
  }catch(e){
    toast(e.message,'error');
    if(loading) loading.remove();
    if(btn){
      btn.disabled = false;
      btn.textContent = 'Reenviar para RH';
    }
    if(emailInput) emailInput.disabled = false;
  }
}

async function verQrDevolucao(devId){
  const r = await api(`/devolucoes/${devId}/sign-link`,'POST',{});
  if(!r||r.error){toast('Erro: '+(r?.error||'falha ao gerar link'),'error');return;}
  openModal('Link de Assinatura — Devolução',`
    <div style="display:flex;flex-direction:column;align-items:center;gap:14px;padding:4px 0">
      <div style="font-size:13px;color:var(--text2);text-align:center">
        Compartilhe o link abaixo com o colaborador para assinar o termo de devolução.
      </div>
      <div style="width:100%;display:flex;gap:8px;align-items:center">
        <input id="devol-link-url" value="${esc(r.url)}" readonly
          style="flex:1;padding:9px 12px;border:1px solid var(--border);border-radius:var(--r);
                 font-size:11px;font-family:var(--mono);color:var(--text);background:var(--bg3)">
        <button class="btn btn-primary btn-sm" onclick="navigator.clipboard.writeText(document.getElementById('devol-link-url').value);toast('Link copiado!')">Copiar</button>
      </div>
      ${r.emailEnviado?'<div style="font-size:12px;color:var(--green-text)">Link enviado por e-mail ao colaborador.</div>':''}
    </div>
    <div class="modal-footer"><button class="btn btn-default" onclick="closeModal()">Fechar</button></div>`,false,true);
}

async function verQrTermo(aid){
  const r = await api(`/allocations/${aid}/sign-link`,'POST',{});
  if(!r||r.error){toast('Erro: '+(r?.error||'falha ao gerar link'),'error');return;}
  const expiry = r.expiry ? new Date(r.expiry).toLocaleDateString('pt-BR') : '';
  openModal('QR Code — Assinatura do Termo',`
    <div style="display:flex;flex-direction:column;align-items:center;gap:16px;padding:4px 0">
      <div style="font-size:13px;color:var(--text2);text-align:center">
        Mostre este QR para o colaborador assinar o termo pelo celular.
        ${expiry?`<br><strong style="color:var(--text)">Válido até ${expiry}.</strong>`:''}
      </div>
      <div style="background:#fff;padding:14px;border-radius:12px;border:1px solid var(--border);box-shadow:0 2px 8px rgba(0,0,0,.08)">
        <img src="/api/allocations/${aid}/qrcode-termo" width="200" height="200" alt="QR Code para assinatura" style="display:block">
      </div>
      <div style="width:100%;display:flex;gap:8px;align-items:center">
        <input id="sign-link-url" value="${esc(r.url)}" readonly
          style="flex:1;padding:9px 12px;border:1px solid var(--border);border-radius:var(--r);
                 font-size:11px;font-family:var(--mono);color:var(--text);background:var(--bg3)">
        <button class="btn btn-primary btn-sm" onclick="copiarLink()">Copiar</button>
      </div>
      ${r.emailEnviado?`<div style="font-size:12px;color:var(--green-text)">Link também enviado por e-mail ao colaborador.</div>`:''}
    </div>
    <div class="modal-footer">
      <button class="btn btn-default" onclick="closeModal()">Fechar</button>
    </div>`,false,true);
}

let _allocPerifs = []; // periféricos selecionados na modal de alocação
let _allocAssets = []; // ativos patrimoniais selecionados na modal de alocação
let _allAllocSupplies = []; // todos os periféricos/insumos com estoque (para filtro dinâmico)
let _allAllocAssets = []; // ativos disponíveis para seleção múltipla

async function openNewAlloc(avail){
  const supplies = await api('/supplies');
  _allAllocSupplies = (supplies || []).filter(s => s.estoque > 0);
  const colabOpts = _colab_cache.filter(c=>c.status==='Ativo'||c.status==='Férias');
  _allocPerifs = [];
  _allocAssets = [];
  _allAllocAssets = avail || [];

  openModal('Nova Alocação', `
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">

    <!-- Coluna esquerda: ativo + colaborador -->
    <div>
      <div class="section-title" style="font-size:13px">Ativos a Alocar <span id="al-asset-count" class="badge badge-blue" style="display:none">0</span></div>
      <div class="info-box blue" style="margin-bottom:10px;font-size:12px">Selecione todos os ativos que sairão no mesmo termo: notebook, desktop, monitor, smartphone, tablet ou outros patrimônios.</div>
      <div class="form-group"><label>Buscar ativo disponível</label>
        <input id="al-asset-search" placeholder="Hostname, patrimônio, categoria..." onkeyup="renderAllocAssetPicker(this.value)">
      </div>
      <div id="al-selected-assets" style="display:flex;flex-direction:column;gap:6px;margin-bottom:10px"></div>
      <div id="al-asset-picker" style="display:flex;flex-direction:column;gap:4px;max-height:210px;overflow-y:auto"></div>
      <input type="hidden" id="al-ativo">
      </div>

      <hr class="divider">
      <div class="section-title" style="font-size:13px">Colaborador</div>
      <div class="form-group"><label>Selecionar Colaborador</label>
        <select id="al-colab-sel" onchange="preencheColab(this.value)">
          <option value="">Selecione o colaborador...</option>
          ${colabOpts.map(c=>`<option value="${c.id}" data-nome="${esc(c.nome)}" data-setor="${esc(c.setor)}" data-uni="${esc(c.unidade)}" data-email="${esc(c.email)}" data-cargo="${esc(c.cargo)}">${esc(c.nome)} — ${esc(c.setor)}</option>`).join('')}
        </select>
      </div>
      <div id="colab-preview" style="display:none;padding:10px 12px;background:var(--blue-bg);border-radius:var(--r);margin-bottom:10px;font-size:12px;color:var(--blue-text)"></div>
      <div class="form-group"><label>Nome (confirmação)</label><input id="al-colab" placeholder="Preenchido ao selecionar acima"></div>
      <div class="form-grid-2">
        <div class="form-group"><label>Setor</label><input id="al-setor"></div>
        <div class="form-group"><label>Unidade</label><input id="al-uni" value="Sede SP"></div>
      </div>
      <div class="form-group"><label>E-mail</label><input id="al-email" type="email"></div>
      <div class="form-group"><label>Tipo de Termo</label>
        <select id="al-tipo" onchange="onAllocTipoChange()">
          <option value="Responsabilidade">Responsabilidade (uso contínuo)</option>
          <option value="Empréstimo">Empréstimo (temporário)</option>
        </select>
      </div>
      <div class="form-group" id="al-devol-wrap" style="display:none">
        <label>Data de Devolução Prevista</label>
        <input id="al-devol-data" type="date">
        <div style="font-size:11px;color:var(--text3);margin-top:3px">Obrigatória para termos de empréstimo</div>
      </div>
    </div>

    <!-- Coluna direita: periféricos compatíveis -->
    <div>
      <div class="section-title" style="font-size:13px">Periféricos no Termo <span id="al-perf-count" class="badge badge-blue" style="display:none">0</span></div>
      <div class="info-box blue" style="margin-bottom:10px;font-size:12px">Opcional. Os itens selecionados serão entregues e incluídos no termo.</div>
      <div style="display:flex;flex-direction:column;gap:4px;max-height:320px;overflow-y:auto" id="perf-list">
        <p style="font-size:12px;color:var(--text3);text-align:center;padding:20px">Adicione ao menos um ativo para ver os periféricos compatíveis.</p>
      </div>
    </div>
  </div>

  <div class="modal-footer">
    <button class="btn btn-default" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="saveNewAlloc()">Criar Alocação + Termo</button>
  </div>`, true);
  renderAllocAssetPicker('');
  renderSelectedAllocAssets();
}

function assetLabel(a){
  return `${a.hostname||a.id} — ${a.fabricante||''} ${a.modelo||''} (${a.categoria||'Ativo'})`.replace(/\s+/g,' ').trim();
}

function renderSelectedAllocAssets(){
  const wrap = $('al-selected-assets');
  const cnt = $('al-asset-count');
  if(!wrap) return;
  if(cnt){
    cnt.style.display = _allocAssets.length ? '' : 'none';
    cnt.textContent = _allocAssets.length;
  }
  $('al-ativo').value = _allocAssets[0]?.id || '';
  wrap.innerHTML = _allocAssets.length
    ? _allocAssets.map((a,i)=>`
      <div style="display:flex;align-items:center;gap:8px;padding:8px 10px;border:1px solid var(--blue-border);border-radius:var(--r);background:var(--blue-bg)">
        <div style="flex:1;min-width:0">
          <div style="font-size:12px;font-weight:700;color:var(--blue-text)">${i===0?'Principal · ':''}${esc(a.hostname||a.id)}</div>
          <div style="font-size:11px;color:var(--blue-text);opacity:.82">${esc(a.categoria||'')} ${a.patrimonio?'· '+esc(a.patrimonio):''}</div>
        </div>
        <button class="btn btn-default btn-sm" onclick="removeAllocAsset('${a.id}')">Remover</button>
      </div>`).join('')
    : `<div style="font-size:12px;color:var(--text3);padding:10px;border:1px dashed var(--border);border-radius:var(--r);text-align:center">Nenhum ativo selecionado.</div>`;
  onAllocAtivoChange();
}

function renderAllocAssetPicker(q=''){
  const wrap = $('al-asset-picker');
  if(!wrap) return;
  const term = (q||'').toLowerCase();
  const selected = new Set(_allocAssets.map(a=>a.id));
  const list = _allAllocAssets
    .filter(a=>!selected.has(a.id))
    .filter(a=>{
      const hay = `${a.hostname||''} ${a.fabricante||''} ${a.modelo||''} ${a.categoria||''} ${a.patrimonio||''} ${a.serviceTag||''}`.toLowerCase();
      return !term || hay.includes(term);
    })
    .slice(0, 40);
  wrap.innerHTML = list.length ? list.map(a=>`
    <div style="display:flex;align-items:center;gap:8px;padding:8px 10px;border:1px solid var(--border);border-radius:var(--r);background:var(--bg3)">
      <div style="flex:1;min-width:0">
        <div style="font-size:12px;font-weight:700">${esc(a.hostname||a.id)}</div>
        <div style="font-size:11px;color:var(--text3)">${esc(a.fabricante||'')} ${esc(a.modelo||'')} · ${esc(a.categoria||'')} ${a.patrimonio?'· '+esc(a.patrimonio):''}</div>
      </div>
      <button class="btn btn-primary btn-sm" onclick="addAllocAsset('${a.id}')">Adicionar</button>
    </div>`).join('')
    : `<div style="font-size:12px;color:var(--text3);text-align:center;padding:14px">Nenhum ativo disponível encontrado.</div>`;
}

function addAllocAsset(id){
  const a = _allAllocAssets.find(x=>x.id===id);
  if(!a || _allocAssets.some(x=>x.id===id)) return;
  _allocAssets.push(a);
  renderSelectedAllocAssets();
  renderAllocAssetPicker($('al-asset-search')?.value || '');
}

function removeAllocAsset(id){
  _allocAssets = _allocAssets.filter(a=>a.id!==id);
  renderSelectedAllocAssets();
  renderAllocAssetPicker($('al-asset-search')?.value || '');
}

function preencheColab(id){
  const sel = $('al-colab-sel');
  const opt = sel.options[sel.selectedIndex];
  if(!id){ $('colab-preview').style.display='none'; return; }
  $('al-colab').value = opt.dataset.nome||'';
  $('al-setor').value = opt.dataset.setor||'';
  $('al-uni').value   = opt.dataset.uni||'';
  $('al-email').value = opt.dataset.email||'';
  $('colab-preview').style.display='block';
  $('colab-preview').innerHTML = `<strong>${opt.dataset.nome}</strong> · ${opt.dataset.cargo} · ${opt.dataset.setor} · ${opt.dataset.uni}<br><span style="opacity:.7">${opt.dataset.email||'Sem e-mail cadastrado'}</span>`;
}

function togglePerif(id, nome, maxQty){
  const idx = _allocPerifs.findIndex(p=>p.supplyId===id);
  if(idx>=0){
    _allocPerifs.splice(idx,1);
    $('perf-chk-'+id).textContent='-';
    $('perf-qty-wrap-'+id).style.display='none';
    $('perf-row-'+id).classList.remove('on');
  } else {
    _allocPerifs.push({supplyId:id,nome,quantidade:1,maxQty});
    $('perf-chk-'+id).textContent='OK';
    $('perf-qty-wrap-'+id).style.display='flex';
    $('perf-row-'+id).classList.add('on');
  }
  const cnt = $('al-perf-count');
  cnt.style.display = _allocPerifs.length?'':'none';
  cnt.textContent = _allocPerifs.length;
}

function changeQty(id, delta, max=99){
  const p = _allocPerifs.find(x=>x.supplyId===id);
  if(!p) return;
  p.quantidade = Math.min(max, Math.max(1, p.quantidade+delta));
  $('perf-qty-'+id).textContent = p.quantidade;
}

function onAllocTipoChange(){
  const tipo = $('al-tipo')?.value;
  const wrap = $('al-devol-wrap');
  if(wrap) wrap.style.display = tipo==='Empréstimo' ? '' : 'none';
}

async function saveNewAlloc(){
  if(!_allocAssets.length){toast('Selecione ao menos um ativo','error');return;}
  if(!$('al-colab').value){toast('Informe o colaborador','error');return;}
  const tipo = $('al-tipo')?.value || 'Responsabilidade';
  const dataDev = $('al-devol-data')?.value || '';
  if(tipo==='Empréstimo' && !dataDev){
    toast('Informe a data de devolução prevista para empréstimos','error');
    return;
  }
  try{
    const ativoId = _allocAssets[0].id;
    const ativoNome = _allocAssets.map(assetLabel).join(', ');
    const r = await api('/allocations','POST',{
      ativo:ativoId, ativos:_allocAssets.map(a=>a.id), colaborador:$('al-colab').value,
      setor:$('al-setor').value, unidade:$('al-uni').value,
      email:$('al-email').value, perifericos:_allocPerifs,
      tipo, dataDevolucaoPrevista: dataDev || null,
    });
    const nPerifs = (r.perifericosAlocados||[]).length;
    closeModal();
    renderAlocacoes();
    // Verificação de etiqueta patrimonial
    perguntarEtiqueta(_allocAssets.map(a=>a.id), ativoNome, nPerifs);
  }catch(e){toast(e.message,'error');}
}

function perguntarEtiqueta(ativoIds, ativoNome, nPerifs){
  const ids = Array.isArray(ativoIds) ? ativoIds : [ativoIds];
  const msg = nPerifs ? ` + ${nPerifs} periférico(s)` : '';
  openModal('Alocação Criada', `
  <div style="text-align:center;padding:10px 0 18px">
    <div style="font-size:36px;margin-bottom:10px"></div>
    <div style="font-size:15px;font-weight:700;margin-bottom:6px">Alocação registrada com sucesso${msg}!</div>
    <div style="font-size:13px;color:var(--text2);margin-bottom:24px">${esc(ativoNome)}</div>
    <div style="background:var(--amber-bg);border:1px solid var(--amber-border);border-radius:var(--r);padding:14px 18px;margin-bottom:20px;text-align:left">
      <div style="font-size:13px;font-weight:700;color:var(--amber-text);margin-bottom:6px">${inlineIcon('warning')} O ativo possui etiqueta patrimonial?</div>
      <div style="font-size:12px;color:var(--amber-text);line-height:1.6">A etiqueta garante rastreabilidade e permite auditorias por QR Code. Recomendamos colar antes da entrega ao colaborador.</div>
    </div>
    <div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap">
      <button class="btn btn-default" onclick="closeModal()">Sim, já possui etiqueta</button>
      <button class="btn btn-primary" onclick="closeModal();irParaEtiqueta('${ids[0]}')">
        ${inlineIcon('qrcode')} Gerar Etiqueta do Principal
      </button>
    </div>
  </div>
  `, false, true);
}

function irParaEtiqueta(ativoId){
  _qrSel = ativoId;
  navigateTo('qrcode');
  setTimeout(()=>{ qrTab('etq'); }, 400);
}

async function viewTermo(a){
  const perifericos=await api(`/allocations/${a.id}/perifericos`);
  const podeTrocar=a.status==='Ativo';
  const ativos = Array.isArray(a.ativos) && a.ativos.length ? a.ativos : [{nome:a.ativoNome, categoria:'Ativo'}];
  const ativosList = ativos.map(item=>`
    <div style="margin-bottom:6px;padding:8px 10px;background:var(--blue-bg);border-radius:var(--r);font-family:var(--mono);font-size:12px;font-weight:700;color:var(--blue-text)">
      [${esc(item.categoria||'ATIVO')}] ${esc(item.nome||item.id||'—')}
      ${item.patrimonio?`<span style="font-family:inherit;font-weight:600;opacity:.75"> · ${esc(item.patrimonio)}</span>`:''}
    </div>`).join('');
  const perfList=perifericos.length
    ? perifericos.map(p=>`<div style="display:flex;gap:10px;align-items:center;padding:6px 10px;background:var(--bg3);border-radius:var(--r);margin-bottom:4px;font-size:13px">
        <span style="font-size:16px"></span>
        <span style="flex:1">${esc(p.nome)}</span>
        <span class="badge badge-blue">${p.quantidade}x</span>
        ${podeTrocar?`<button class="btn btn-default btn-sm"
          data-allocation-id="${escAttr(a.id)}"
          data-item-id="${escAttr(p.id)}"
          data-supply-id="${escAttr(p.supplyId)}"
          data-nome="${escAttr(p.nome)}"
          data-quantidade="${escAttr(p.quantidade)}"
          onclick="openTrocaPeriferico(this)">Trocar</button>`:''}
      </div>`).join('')
    : '<p style="font-size:12px;color:var(--text3)">Nenhum periférico vinculado a este colaborador.</p>';

  openModal('Termo de Responsabilidade',`
  <div style="border:1px solid var(--border2);border-radius:var(--r);padding:22px;font-size:13px;line-height:1.8">
    <div style="text-align:center;margin-bottom:16px">
      <div style="font-size:15px;font-weight:700">TERMO DE RESPONSABILIDADE DE EQUIPAMENTO</div>
      <div style="font-size:12px;color:var(--text2)">Nº ${esc(a.termo)} — ${fmtDate(a.dataAloc)}</div>
    </div>
    <p>Eu, <strong>${esc(a.colaborador)}</strong>, lotado(a) no setor de <strong>${esc(a.setor)}</strong>, unidade <strong>${esc(a.unidade)}</strong>, declaro ter recebido:</p>
    <div style="margin:12px 0">${ativosList}</div>
    ${perifericos.length?`<div style="margin-bottom:10px"><div style="font-size:12px;font-weight:700;color:var(--text2);margin-bottom:6px">PERIFÉRICOS VINCULADOS:</div>${perfList}</div>`:''}
    <p>Comprometo-me a utilizar exclusivamente para fins profissionais, zelar pela conservação, comunicar danos/perdas e devolver ao encerramento do vínculo.</p>
    <div style="display:flex;gap:16px;margin-top:22px;flex-wrap:wrap">
      <!-- Assinatura colaborador -->
      <div style="flex:1;min-width:200px">
        <div style="font-size:11px;font-weight:600;color:var(--text2);margin-bottom:6px;text-transform:uppercase;letter-spacing:.04em">Assinatura — ${esc(a.colaborador)}</div>
        ${a.hasSignImg
          ? `<div style="border:1px solid var(--border2);border-radius:var(--r);padding:6px;background:#fff">
               <img src="/api/allocations/${a.id}/assinatura.png" style="max-height:72px;max-width:100%;display:block" alt="Assinatura">
             </div>`
          : `<div style="border-top:2px solid var(--text);margin-top:36px"></div>`
        }
        ${a.termoStatus==='Assinado'
          ? `<div style="font-size:11px;color:var(--text3);margin-top:4px">
               Assinado em ${fmtDateTime(a.dataAssinatura)}
               ${a.assinaturaIp?`<span style="font-family:var(--mono)">&nbsp;·&nbsp;IP: ${esc(a.assinaturaIp)}</span>`:''}
             </div>`
          : `<div style="font-size:11px;color:var(--amber,#d97706);margin-top:4px">Pendente de assinatura</div>`
        }
      </div>
      <!-- Assinatura Responsável TI -->
      <div style="flex:1;min-width:200px">
        <div style="font-size:11px;font-weight:600;color:var(--text2);margin-bottom:6px;text-transform:uppercase;letter-spacing:.04em">Responsável TI</div>
        ${a.hasSignTiImg
          ? `<div style="border:1px solid var(--border2);border-radius:var(--r);padding:6px;background:#fff">
               <img src="/api/allocations/${a.id}/assinatura-ti.png" style="max-height:72px;max-width:100%;display:block" alt="Assinatura TI">
             </div>
             <div style="font-size:11px;color:var(--text3);margin-top:4px">
               Assinado por ${esc(a.assinaturaTiNome||'')} · ${fmtDateTime(a.dataAssinaturaTi)}
             </div>`
          : `<div style="border-top:2px solid var(--text);margin-top:36px"></div>
             <div style="margin-top:8px">
               <button class="btn btn-default btn-sm" onclick="openSignTi('${a.id}')">Assinar como TI</button>
             </div>`
        }
      </div>
    </div>
  </div>
  <div class="modal-footer">
    <a href="/api/allocations/${a.id}/termo.pdf" class="btn btn-primary" download>Baixar PDF</a>
    ${a.termoStatus!=='Assinado'?`
      <button class="btn btn-success" onclick="signTermo('${a.id}')">Marcar Assinado</button>
      <button class="btn btn-default" onclick="gerarLinkAssinatura('${a.id}')">Link p/ Assinar</button>
    `:''}
  </div>`,true);
}
async function signTermo(id){await api(`/allocations/${id}/sign`,'POST',{});toast('Termo assinado');closeModal();renderAlocacoes();}

async function openTrocaPeriferico(btn){
  const allocationId=btn.dataset.allocationId;
  const itemId=btn.dataset.itemId;
  const supplyId=btn.dataset.supplyId;
  const nome=btn.dataset.nome||'Periférico';
  const quantidade=Math.max(1,parseInt(btn.dataset.quantidade||'1',10)||1);
  const supplies=await api('/supplies');
  const perifericos=supplies.filter(s=>['Periférico','PerifÃ©rico'].includes(s.categoria));
  const opts=perifericos.length ? perifericos.map(s=>`
    <option value="${escAttr(s.id)}" ${s.id===supplyId?'selected':''}>
      ${esc(s.nome)} - estoque: ${s.estoque}
    </option>`).join('') : '<option value="">Nenhum periférico cadastrado</option>';

  openModal('Trocar periférico com defeito',`
    <div class="info-box amber">
      <strong>Item atual:</strong> ${esc(nome)}<br>
      O item defeituoso será registrado no histórico e o substituto sairá do estoque.
    </div>
    <div class="form-grid-2">
      <div class="form-group">
        <label>Quantidade</label>
        <input id="tp-qty" type="number" min="1" max="${quantidade}" value="1">
      </div>
      <div class="form-group">
        <label>Motivo</label>
        <select id="tp-motivo">
          <option>Defeito</option>
          <option>Dano físico</option>
          <option>Mau funcionamento</option>
          <option>Perda de funcionalidade</option>
        </select>
      </div>
    </div>
    <div class="form-group">
      <label>Periférico substituto</label>
      <select id="tp-supply">${opts}</select>
    </div>
    <div class="form-group">
      <label>Observação</label>
      <textarea id="tp-obs" style="min-height:80px;resize:vertical" placeholder="Ex: mouse sem clique, teclado com tecla quebrada..."></textarea>
    </div>
    <div class="modal-footer">
      <button class="btn btn-default" onclick="closeModal()">Cancelar</button>
      <button class="btn btn-primary" ${perifericos.length?'':'disabled'} onclick="confirmarTrocaPeriferico('${escAttr(allocationId)}','${escAttr(itemId)}')">Registrar Troca</button>
    </div>
  `,false,true);
}

async function confirmarTrocaPeriferico(allocationId,itemId){
  if(!$('tp-supply').value){toast('Selecione um periférico substituto.','error');return;}
  const quantidade=parseInt($('tp-qty').value,10)||1;
  await api(`/allocations/${allocationId}/perifericos/${itemId}/troca`,'POST',{
    novoSupplyId:$('tp-supply').value,
    quantidade,
    motivo:$('tp-motivo').value,
    observacao:$('tp-obs').value
  });
  toast('Troca registrada com sucesso');
  closeModal();
  renderAlocacoes();
}

async function gerarLinkAssinatura(aid){
  const r = await api(`/allocations/${aid}/sign-link`,'POST',{});
  if(!r||r.error){toast('Erro: '+(r?.error||'falha'),'error');return;}
  const expiry = r.expiry ? new Date(r.expiry).toLocaleDateString('pt-BR') : '';
  openModal(' Link de Assinatura Remota',`
    <div style="display:flex;flex-direction:column;gap:14px">
      <div style="font-size:13px;color:var(--text2)">
        Compartilhe o link abaixo com o colaborador. Ele poderá acessar pelo celular,
        ler o termo e assinar digitalmente com o dedo.
        ${expiry?`<br><br><strong>Válido até ${expiry}.</strong>`:''}
      </div>
      <div style="display:flex;gap:8px;align-items:center">
        <input id="sign-link-url" value="${esc(r.url)}" readonly
          style="flex:1;padding:10px 12px;border:1px solid var(--border2);border-radius:var(--r);
                 font-size:12px;font-family:var(--mono);color:var(--text);background:var(--bg3)">
        <button class="btn btn-primary btn-sm" onclick="copiarLink()">Copiar</button>
      </div>
      <a href="${esc(r.url)}" target="_blank" style="font-size:12px;color:var(--blue)">
        Abrir em nova aba para testar →
      </a>
    </div>
    <div class="modal-footer">
      <button class="btn btn-default" onclick="closeModal()">Fechar</button>
    </div>
  `,true);
}
function copiarLink(){
  const el=document.getElementById('sign-link-url');
  if(!el)return;
  navigator.clipboard.writeText(el.value).then(()=>toast('Link copiado!'));
}

function openSignTi(aid){
  openModal(' Assinatura do Responsável TI',`
    <div style="display:flex;flex-direction:column;gap:14px">
      <div style="font-size:13px;color:var(--text2)">Desenhe sua assinatura abaixo para registrar como responsável TI neste termo.</div>
      <div>
        <div style="font-size:12px;font-weight:600;color:var(--text2);margin-bottom:6px">Nome do responsável</div>
        <input id="ti-nome" placeholder="Seu nome completo" value=""
          style="width:100%;padding:9px 12px;border:1px solid var(--border2);border-radius:var(--r);font-size:13px;font-family:inherit">
      </div>
      <div>
        <div style="font-size:12px;font-weight:600;color:var(--text2);margin-bottom:6px">Assinatura</div>
        <canvas id="ti-canvas" style="width:100%;height:140px;background:#fff;border:2px dashed var(--border2);border-radius:var(--r);display:block;touch-action:none;cursor:crosshair"></canvas>
        <button type="button" onclick="tiClearCanvas()" class="btn btn-default btn-sm" style="margin-top:6px">Limpar</button>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-default" onclick="closeModal()">Cancelar</button>
      <button class="btn btn-success" onclick="saveSignTi('${aid}')">Salvar Assinatura</button>
    </div>
  `,true);
  // Inicializa canvas após o modal abrir
  requestAnimationFrame(()=>tiInitCanvas());
}

let _tiCtx=null, _tiDrawing=false, _tiHasSig=false;
function tiInitCanvas(){
  const cv=document.getElementById('ti-canvas');
  if(!cv)return;
  const rect=cv.getBoundingClientRect();
  cv.width=rect.width*devicePixelRatio; cv.height=rect.height*devicePixelRatio;
  _tiCtx=cv.getContext('2d');
  _tiCtx.scale(devicePixelRatio,devicePixelRatio);
  _tiCtx.lineWidth=2.5; _tiCtx.lineCap='round'; _tiCtx.lineJoin='round'; _tiCtx.strokeStyle='#1a1917';
  _tiHasSig=false;
  function pos(e){const r=cv.getBoundingClientRect(),s=e.touches?e.touches[0]:e;return{x:s.clientX-r.left,y:s.clientY-r.top};}
  cv.onmousedown=cv.ontouchstart=e=>{e.preventDefault();_tiDrawing=true;const p=pos(e);_tiCtx.beginPath();_tiCtx.moveTo(p.x,p.y);};
  cv.onmousemove=cv.ontouchmove=e=>{if(!_tiDrawing)return;e.preventDefault();const p=pos(e);_tiCtx.lineTo(p.x,p.y);_tiCtx.stroke();_tiHasSig=true;cv.style.borderStyle='solid';cv.style.borderColor='var(--blue)';};
  cv.onmouseup=cv.onmouseleave=cv.ontouchend=()=>{_tiDrawing=false;};
}
function tiClearCanvas(){
  const cv=document.getElementById('ti-canvas');
  if(!cv||!_tiCtx)return;
  _tiCtx.clearRect(0,0,cv.width/devicePixelRatio,cv.height/devicePixelRatio);
  _tiHasSig=false; cv.style.borderStyle='dashed'; cv.style.borderColor='var(--border2)';
}
async function saveSignTi(aid){
  if(!_tiHasSig){toast('Desenhe a assinatura antes de salvar.','error');return;}
  const nome=document.getElementById('ti-nome')?.value.trim();
  if(!nome){toast('Informe o nome do responsável.','error');return;}
  const cv=document.getElementById('ti-canvas');
  const sigData=cv.toDataURL('image/png');
  await api(`/allocations/${aid}/sign-ti`,'POST',{assinatura:sigData,nomeTi:nome});
  toast('Assinatura TI salva!');
  closeModal();
  renderAlocacoes();
}
