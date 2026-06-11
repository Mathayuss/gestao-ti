// ══════════════════════════════════════════════════════════════════════════
// COLABORADORES
// ══════════════════════════════════════════════════════════════════════════
const STATUS_COL=['Ativo','Inativo','Férias','Afastado'];
let _colabView='ativos'; // 'ativos' | 'desligados'

function colAvatar(nome,size=36){
  const cols=[['#e8f1fb','#1a4e8a'],['#e6f4ec','#145c34'],['#fdf0e0','#7a3e07'],['#fdecea','#8a1c13'],['#f0ecfe','#4a2ab5'],['#efefed','#2c2c2a']];
  let h=0; for(let i=0;i<(nome||'').length;i++) h=(h*31+nome.charCodeAt(i))&0xfffffff;
  const [bg,fg]=cols[h%cols.length];
  const ini=(nome||'?').trim().split(' ');
  const letters=(ini[0][0]+(ini.length>1?ini[ini.length-1][0]:'')).toUpperCase();
  return `<div style="width:${size}px;height:${size}px;border-radius:99px;background:${bg};color:${fg};display:inline-flex;align-items:center;justify-content:center;font-size:${Math.round(size*.35)}px;font-weight:700;flex-shrink:0">${letters}</div>`;
}

async function renderColaboradores(q='',setor='',status=''){
  const [data,stats]=await Promise.all([api(`/colaboradores?q=${encodeURIComponent(q)}&setor=${encodeURIComponent(setor)}&status=${encodeURIComponent(status)}`),api('/colaboradores/stats')]);
  _colab_cache=data;
  const desligados = data.filter(c=>c.status==='Inativo');
  const ativos     = data.filter(c=>c.status!=='Inativo');
  const lista      = _colabView==='desligados' ? desligados : ativos;
  const setores=['', ...new Set(ativos.map(u=>u.setor).filter(Boolean))];
  $('content').innerHTML=`
  <div class="grid-4 mb-16">
    ${[['Total',stats.total,'','blue'],['Ativos',stats.ativos,'OK','green'],['Afastados / Férias',stats.afastados,'','amber'],['Com Equipamento',stats.comAtivos,'','blue']].map(([l,v,ic,c])=>`
    <div class="stat-card"><div style="display:flex;justify-content:space-between;align-items:flex-start">
      <div><div class="stat-label">${l}</div><div class="stat-value">${v}</div></div>
      <div style="font-size:22px;padding:8px;background:var(--${c}-bg);border-radius:var(--r)">${ic}</div>
    </div></div>`).join('')}
  </div>
  <div class="flex-between mb-16" style="flex-wrap:wrap;gap:8px">
    <div class="flex-gap" style="flex-wrap:wrap">
      <div class="search-wrap"><span class="search-icon">${inlineIcon('search')}</span>
        <input id="cs" placeholder="Nome, e-mail, cargo, matrícula..." value="${esc(q)}"
          onkeyup="debounce(()=>renderColaboradores(this.value,document.getElementById('cst').value,document.getElementById('css').value))">
      </div>
      <select id="cst" style="width:auto" onchange="renderColaboradores(document.getElementById('cs').value,this.value,document.getElementById('css').value)">
        <option value="">Todos os setores</option>
        ${setores.filter(Boolean).map(s=>`<option ${s===setor?'selected':''}>${esc(s)}</option>`).join('')}
      </select>
      <select id="css" style="width:auto" onchange="renderColaboradores(document.getElementById('cs').value,document.getElementById('cst').value,this.value)">
        <option value="">Todos os status</option>
        ${STATUS_COL.map(s=>`<option ${s===status?'selected':''}>${s}</option>`).join('')}
      </select>
    </div>
    <div class="flex-gap">
      ${_colabView==='desligados'
        ? `<button class="btn btn-default" onclick="_colabView='ativos';renderColaboradores()">← Colaboradores Ativos</button>`
        : `<a class="btn btn-default" href="/api/export/colaboradores.csv" download>Exportar CSV</a>
           <button class="btn btn-default" onclick="_colabView='desligados';renderColaboradores()" style="position:relative">
             Desligados <span class="badge badge-red" style="margin-left:4px">${desligados.length}</span>
           </button>
           <button class="btn btn-primary" onclick="openNewColab()">Novo Colaborador</button>`}
    </div>
  </div>
  ${_colabView==='desligados' ? `
  <div class="info-box" style="background:var(--red-bg);border-color:var(--red);color:var(--red-text);margin-bottom:16px">
    Exibindo <strong>${desligados.length}</strong> colaborador(es) desligado(s) / inativo(s). Para reativar um colaborador, clique em <strong>Reativar</strong>.
  </div>` : ''}
  <div style="display:flex;gap:16px;align-items:flex-start">
    <div class="card" style="flex:1;min-width:0">
      <div class="table-wrap"><table>
        <thead><tr><th>Colaborador</th><th>Matrícula</th><th>Cargo</th><th>Setor</th><th>Unidade</th><th>Status</th>
          ${_colabView==='desligados' ? '<th>Desligamento</th>' : '<th>Equipamentos</th>'}
          <th></th></tr></thead>
        <tbody>${lista.map(c=>`<tr>
          <td><div class="flex-gap">${colAvatar(c.nome)}<div>
            <div style="font-weight:600;font-size:13px">${esc(c.nome)}</div>
            <div style="font-size:11px;color:var(--text3)">${esc(c.email)}</div>
          </div></div></td>
          <td class="mono" style="color:var(--text3)">${esc(c.matricula||'—')}</td>
          <td style="font-size:12px">${esc(c.cargo)}</td>
          <td>${esc(c.setor)}</td>
          <td style="font-size:12px">${esc(c.unidade)}</td>
          <td>${badge(c.status,STATUS_COLAB_COLOR[c.status]||'gray')}</td>
          ${_colabView==='desligados'
            ? `<td style="font-size:12px;color:var(--text3)">${c.dataDesligamento?fmtDate(c.dataDesligamento):'—'}</td>`
            : `<td style="text-align:center" id="ca-${c.id}"><span style="color:var(--text3)">…</span></td>`}
          <td><div class="flex-gap">
            <button class="btn btn-default btn-icon btn-sm" onclick="viewColab('${c.id}')">Ver</button>
            ${_colabView==='desligados'
              ? `<button class="btn btn-success btn-sm" onclick="reativarColab('${c.id}','${esc(c.nome)}')">Reativar</button>`
              : `<button class="btn btn-default btn-icon btn-sm" onclick="editColab('${c.id}')">Editar</button>
                 ${c.status==='Ativo'?`<button class="btn btn-danger btn-sm" onclick="confirmOffboarding('${c.id}','${esc(c.nome)}')">Desligar</button>`:''}`}
          </div></td>
        </tr>`).join('')}
        </tbody>
      </table></div>
    </div>
    <div class="card" style="min-width:180px">
      <div style="font-size:13px;font-weight:600;margin-bottom:12px">Por Setor</div>
      ${Object.entries(stats.porSetor).sort((a,b)=>b[1]-a[1]).map(([s,n])=>{
        const p=Math.round(n/stats.total*100);
        return `<div style="margin-bottom:8px">
          <div class="flex-between" style="font-size:12px;margin-bottom:3px"><span>${esc(s)}</span><span style="color:var(--text2)">${n}</span></div>
          <div class="progress-wrap"><div class="progress-bar" style="width:${p}%;background:var(--green-bg)"></div></div>
        </div>`;}).join('')}
    </div>
  </div>`;

  // Busca contagem de ativos em background (só na view de ativos)
  if(_colabView==='ativos'){
    api('/assets').then(assets=>{
      const cnt={};
      assets.forEach(a=>{if(a.colaborador) cnt[a.colaborador]=(cnt[a.colaborador]||0)+1;});
      lista.forEach(c=>{
        const el=$('ca-'+c.id);
        if(el) el.innerHTML=`<span style="font-weight:700;color:var(--blue)">${cnt[c.nome]||0}</span>`;
      });
    });
  }
}

async function viewColab(id){
  const c=await api(`/colaboradores/${id}`);
  const perfHtml=c.perifericos&&c.perifericos.length
    ?c.perifericos.map(p=>`<div class="flex-gap" style="padding:7px;border-bottom:1px solid var(--border)">
        <span></span><span style="flex:1;font-size:13px">${esc(p.nome)}</span>
        <span class="badge badge-blue">${p.quantidade}x</span>
      </div>`).join('')
    :'<p style="font-size:12px;color:var(--text3)">Nenhum periférico vinculado.</p>';
  const ativosHtml=c.ativos&&c.ativos.length
    ?c.ativos.map(a=>`<div class="flex-gap" style="padding:7px;border-bottom:1px solid var(--border)">
        <span></span><div style="flex:1"><div class="mono" style="font-size:12px;font-weight:700">${esc(a.hostname)}</div>
        <div style="font-size:11px;color:var(--text3)">${esc(a.fabricante)} ${esc(a.modelo)}</div></div>${badge(a.status)}</div>`).join('')
    :'<p style="font-size:12px;color:var(--text3)">Nenhum ativo alocado.</p>';
  const termosHtml=c.termos&&c.termos.length
    ?c.termos.map(t=>`<div class="alert-row" style="padding:8px 0;gap:10px">
        <div style="flex:1">
          <div style="font-size:13px;font-weight:700">${esc(t.tipo)} · ${esc(t.referencia)}</div>
          <div style="font-size:11px;color:var(--text3)">${fmtDate(t.data)} · ${badge(t.status)}</div>
        </div>
        <a class="btn btn-default btn-sm" href="${escAttr(t.url)}" target="_blank">PDF</a>
      </div>`).join('')
    :'<p style="font-size:12px;color:var(--text3)">Nenhum termo vinculado.</p>';

  openModal(`Perfil — ${c.nome}`,`
  <div style="display:flex;gap:16px;margin-bottom:18px">
    ${colAvatar(c.nome,60)}
    <div><div style="font-size:17px;font-weight:700;margin-bottom:4px">${esc(c.nome)}</div>
      <div style="font-size:13px;color:var(--text2);margin-bottom:6px">${esc(c.cargo)} · ${esc(c.setor)}</div>
      <div class="flex-gap">${badge(c.status,STATUS_COLAB_COLOR[c.status]||'gray')}</div>
    </div>
  </div>
  <div class="form-grid-2" style="margin-bottom:14px">
    ${[['E-mail',c.email],['Telefone',c.telefone],['Matrícula',c.matricula],['Unidade',c.unidade],['Admissão',fmtDate(c.dataAdmissao)],['Cadastro',fmtDate(c.dataCadastro)]].map(([k,v])=>`
    <div style="background:var(--bg3);border-radius:var(--r);padding:8px 10px">
      <div style="font-size:11px;color:var(--text2);margin-bottom:2px">${k}</div>
      <div style="font-size:13px;font-weight:600">${esc(v)||'—'}</div>
    </div>`).join('')}
    ${c.observacao?`<div style="grid-column:span 2;background:var(--amber-bg);border-radius:var(--r);padding:8px 10px">
      <div style="font-size:11px;color:var(--amber-text);margin-bottom:2px">Observação</div>
      <div style="font-size:13px;color:var(--amber-text)">${esc(c.observacao)}</div>
    </div>`:''}
  </div>
  <div class="grid-2">
    <div><div class="section-title" style="font-size:13px">Ativos (${(c.ativos||[]).length})</div>${ativosHtml}</div>
    <div><div class="section-title" style="font-size:13px">Periféricos (${(c.perifericos||[]).length})</div>${perfHtml}</div>
  </div>
  <div style="margin-top:16px">
    <div class="section-title" style="font-size:13px">Termos (${(c.termos||[]).length})</div>
    ${termosHtml}
  </div>
  <div class="modal-footer">
    <button class="btn btn-default" onclick="editColab('${id}');closeModal()">Editar</button>
    ${c.status==='Ativo'
      ? `<button class="btn btn-danger" onclick="closeModal();confirmOffboarding('${id}','${esc(c.nome)}')">Desligar</button>`
      : c.status==='Inativo'
        ? `<button class="btn btn-success" onclick="closeModal();reativarColab('${id}','${esc(c.nome)}')">Reativar</button>`
        : ''}
  </div>`,true);
}

function colabFormHtml(c={}){
  return `<div class="form-grid-2">
    <div class="form-group span-2"><label>Nome Completo</label><input id="fc-nome" value="${esc(c.nome||'')}"></div>
    <div class="form-group"><label>E-mail</label><input id="fc-email" type="email" value="${esc(c.email||'')}"></div>
    <div class="form-group"><label>Telefone</label><input id="fc-tel" value="${esc(c.telefone||'')}"></div>
    <div class="form-group"><label>Cargo</label><input id="fc-cargo" value="${esc(c.cargo||'')}"></div>
    <div class="form-group"><label>Matrícula</label><input id="fc-mat" value="${esc(c.matricula||'')}"></div>
    <div class="form-group"><label>Setor</label>
      <select id="fc-setor"><option value="">—</option>${setorOpts(c.setor||'')}</select>
    </div>
    <div class="form-group"><label>Unidade</label>
      <select id="fc-uni"><option value="">—</option>${unidadeOpts(c.unidade||'')}</select>
    </div>
    <div class="form-group"><label>Status</label>
      <select id="fc-status">${STATUS_COL.map(s=>`<option ${s===c.status?'selected':''}>${s}</option>`).join('')}</select>
    </div>
    <div class="form-group"><label>Data de Admissão</label><input id="fc-adm" type="date" value="${c.dataAdmissao||''}"></div>
  </div>
  <div class="form-group"><label>Observação</label><textarea id="fc-obs" rows="2">${esc(c.observacao||'')}</textarea></div>`;
}
function getColabForm(){
  return {nome:$('fc-nome').value,email:$('fc-email').value,telefone:$('fc-tel').value,cargo:$('fc-cargo').value,matricula:$('fc-mat').value,setor:$('fc-setor').value,unidade:$('fc-uni').value,status:$('fc-status').value,dataAdmissao:$('fc-adm').value,observacao:$('fc-obs').value};
}
function openNewColab(){
  openModal('Novo Colaborador',colabFormHtml()+`<div class="modal-footer"><button class="btn btn-default" onclick="closeModal()">Cancelar</button><button class="btn btn-primary" onclick="saveNewColab()">Cadastrar</button></div>`,true);
}
async function editColab(id){
  const c=await api(`/colaboradores/${id}`);
  openModal('Editar Colaborador',colabFormHtml(c)+`<div class="modal-footer"><button class="btn btn-default" onclick="closeModal()">Cancelar</button><button class="btn btn-primary" onclick="saveEditColab('${id}')">Salvar</button></div>`,true);
}
async function saveNewColab(){if(!$('fc-nome').value){toast('Informe o nome','error');return;}await api('/colaboradores','POST',getColabForm());toast('Colaborador cadastrado');closeModal();renderColaboradores();}
async function saveEditColab(id){await api(`/colaboradores/${id}`,'PUT',getColabForm());toast('Colaborador atualizado');closeModal();renderColaboradores();}

function confirmOffboarding(id,nome){
  openModal('Confirmar Desligamento',`
  <div style="text-align:center;padding:10px 0 20px">
    <div style="font-size:40px;margin-bottom:12px">Atenção</div>
    <div style="font-size:15px;font-weight:700;margin-bottom:8px">Desligar ${esc(nome)}?</div>
    <div style="font-size:13px;color:var(--text2);line-height:1.8">Esta ação irá:<br>
    • Devolver todos os <strong>ativos de TI</strong> ao estoque<br>
    • Devolver todos os <strong>periféricos</strong> ao estoque<br>
    • Encerrar <strong>alocações ativas</strong><br>
    • Marcar o colaborador como <strong>Inativo</strong></div>
  </div>
  <div class="modal-footer" style="justify-content:center">
    <button class="btn btn-default" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-danger" onclick="executeOffboarding('${id}')">Confirmar Desligamento</button>
  </div>`,false,true);
}

async function executeOffboarding(id){
  let r;
  try{ r=await api(`/colaboradores/${id}/offboarding`,'POST',{}); }
  catch(e){ toast(e.message||'Erro ao realizar desligamento.','error'); return; }
  closeModal();
  const temItens = (r.ativosDevolvidos||[]).length||(r.perifericosDevolvidos||[]).length;
  if(temItens) _laudoPendente = {devId:r.devolucaoId, colaborador:r.colaborador, ativos:r.ativosDevolvidos||[], perifs:r.perifericosDevolvidos||[]};
  openModal('Desligamento Concluído',`
  <div style="text-align:center;padding:8px 0 14px">
    <div style="font-size:40px;margin-bottom:10px">✓</div>
    <div style="font-size:15px;font-weight:700;margin-bottom:4px">Desligamento realizado</div>
    <div style="font-size:12px;color:var(--text2)">${esc(r.colaborador)} · ${r.dataDesligamento}</div>
    <div style="font-size:12px;color:var(--text2)">${esc(r.setor||'')} ${r.unidade?'· '+esc(r.unidade):''}</div>
  </div>
  ${r.ativosDevolvidos.length?`<div class="info-box green"><strong>Ativos devolvidos:</strong><br>${r.ativosDevolvidos.map(h=>`• ${esc(h)}`).join('<br>')}</div>`:''}
  ${r.perifericosDevolvidos.length?`<div class="info-box green"><strong>Periféricos devolvidos:</strong><br>${r.perifericosDevolvidos.map(p=>`• ${esc(p)}`).join('<br>')}</div>`:''}
  ${temItens?'<div class="info-box amber" style="margin-top:8px"><strong>Próximo passo: Laudo Técnico</strong><br>Registre a avaliação dos equipamentos para que o RH possa dar ciência e o termo seja gerado.</div>':''}
  <div class="modal-footer" style="justify-content:center">
    ${temItens?'<button class="btn btn-primary" onclick="closeModal();abrirLaudo()">Registrar Laudo Técnico</button>':''}
    <button class="btn btn-default" onclick="closeModal()">Fechar</button>
  </div>`,false,true);
  renderColaboradores();
}

function abrirLaudo(){
  if(!_laudoPendente){return;}
  const {devId, colaborador, ativos, perifs} = _laudoPendente;
  const itens = [...ativos, ...perifs];
  const itensHtml = itens.map((item,i)=>`
    <div style="background:var(--bg3);border-radius:var(--r);padding:10px 12px;margin-bottom:8px">
      <div style="font-size:12px;font-weight:600;color:var(--text2);margin-bottom:6px">${esc(item)}</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:6px">
        <label style="display:flex;align-items:center;gap:4px;font-size:12px;cursor:pointer">
          <input type="radio" name="estado_${i}" value="Bom estado" checked> Bom estado
        </label>
        <label style="display:flex;align-items:center;gap:4px;font-size:12px;cursor:pointer">
          <input type="radio" name="estado_${i}" value="Dano"> Dano
        </label>
        <label style="display:flex;align-items:center;gap:4px;font-size:12px;cursor:pointer">
          <input type="radio" name="estado_${i}" value="Mau uso"> Mau uso
        </label>
        <label style="display:flex;align-items:center;gap:4px;font-size:12px;cursor:pointer">
          <input type="radio" name="estado_${i}" value="Perda"> Perda
        </label>
      </div>
      <input type="text" id="obs_item_${i}" placeholder="Observação (opcional)" style="width:100%;padding:6px 8px;border:1px solid var(--border);border-radius:var(--r);font-size:12px;background:var(--bg2);color:var(--text)">
    </div>`).join('');

  openModal(`Laudo Técnico — ${colaborador}`,`
  <div style="max-height:60vh;overflow-y:auto;padding-right:4px">
    <div class="form-group" style="margin-bottom:12px">
      <label style="font-size:12px;font-weight:600;color:var(--text2);display:block;margin-bottom:4px">E-mail do RH (receberá o laudo para ciência) <span style="color:var(--red)">*</span></label>
      <input type="email" id="laudo-rh-email" placeholder="rh@empresa.com" autocomplete="off" style="width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:var(--r);font-size:13px;background:var(--bg2);color:var(--text)">
    </div>
    <div class="form-group" style="margin-bottom:12px">
      <label style="font-size:12px;font-weight:600;color:var(--text2);display:block;margin-bottom:4px">Confirmar e-mail do RH <span style="color:var(--red)">*</span></label>
      <input type="email" id="laudo-rh-email-confirm" placeholder="rh@empresa.com" autocomplete="off" style="width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:var(--r);font-size:13px;background:var(--bg2);color:var(--text)">
    </div>
    ${itens.length?`<div style="font-size:12px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px">Avaliação por item</div>${itensHtml}`:'<p style="font-size:13px;color:var(--text3);text-align:center;margin-bottom:12px">Nenhum item para avaliar.</p>'}
    <div class="form-group" style="margin-bottom:12px">
      <label style="font-size:12px;font-weight:600;color:var(--text2);display:block;margin-bottom:4px">Observação geral</label>
      <textarea id="laudo-obs" rows="2" placeholder="Condições gerais, pendências..." style="width:100%;padding:8px 10px;border:1px solid var(--border);border-radius:var(--r);font-size:13px;background:var(--bg2);color:var(--text);resize:vertical"></textarea>
    </div>
    <div style="background:var(--amber-bg);border:1px solid var(--amber-border);border-radius:var(--r);padding:10px 12px;margin-bottom:12px">
      <label style="display:flex;align-items:center;gap:8px;font-size:13px;font-weight:600;cursor:pointer">
        <input type="checkbox" id="laudo-tem-cobranca"> Recomendar cobrança ao colaborador
      </label>
      <div id="laudo-cobranca-box" style="display:none;margin-top:8px">
        <label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px">Valor sugerido (R$)</label>
        <input type="number" id="laudo-valor" min="0" step="0.01" placeholder="0,00" style="width:140px;padding:6px 8px;border:1px solid var(--border);border-radius:var(--r);font-size:13px;background:var(--bg2);color:var(--text)">
      </div>
    </div>
  </div>
  <div class="modal-footer">
    <button class="btn btn-default" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="enviarLaudo()">Enviar Laudo ao RH</button>
  </div>`,false,true);

  document.getElementById('laudo-tem-cobranca').addEventListener('change',function(){
    document.getElementById('laudo-cobranca-box').style.display=this.checked?'block':'none';
  });
}

async function enviarLaudo(){
  if(!_laudoPendente) return;
  const {devId, ativos, perifs} = _laudoPendente;
  const itens = [...ativos, ...perifs];
  const rhEmail = document.getElementById('laudo-rh-email').value.trim();
  const rhEmailConfirm = document.getElementById('laudo-rh-email-confirm').value.trim();
  if(!rhEmail){toast('Informe o e-mail do RH.','error');return;}
  if(!rhEmailConfirm){toast('Confirme o e-mail do RH.','error');return;}
  if(rhEmail.toLowerCase()!==rhEmailConfirm.toLowerCase()){toast('Os e-mails do RH não conferem.','error');return;}
  const avaliacaoItens = itens.map((ativo,i)=>({
    ativo,
    estado: document.querySelector(`input[name="estado_${i}"]:checked`)?.value||'Bom estado',
    observacao: document.getElementById(`obs_item_${i}`)?.value||''
  }));
  const temCobranca = document.getElementById('laudo-tem-cobranca').checked;
  const valorCobranca = parseFloat(document.getElementById('laudo-valor')?.value||0)||0;
  const obs = document.getElementById('laudo-obs').value;

  try{
    const r = await api(`/devolucoes/${devId}/laudo`,'POST',{
      rhEmail, avaliacaoItens, observacaoGeral:obs, temCobranca, valorCobranca
    });
    _laudoPendente = null;
    closeModal();
    toast(r.emailRHEnviado
      ? 'Laudo enviado! RH receberá o e-mail para ciência.'
      : 'Laudo registrado. E-mail ao RH falhou — verifique as configurações de SMTP.',
      r.emailRHEnviado?'success':'warn');
  }catch(e){ toast(e.message||'Erro ao enviar laudo.','error'); }
}

function reativarColab(id, nome){
  openModal(`Reativar Colaborador — ${nome}`,`
  <div class="info-box green" style="margin-bottom:16px">
    O colaborador será reativado com status <strong>Ativo</strong> e poderá receber alocações novamente.
  </div>
  <div class="form-grid-2">
    <div class="form-group">
      <label>Data de Readmissão</label>
      <input type="date" id="re-adm" value="${new Date().toISOString().slice(0,10)}">
    </div>
    <div class="form-group">
      <label>Setor</label>
      <select id="re-setor"><option value="">— manter atual —</option>${setorOpts('')}</select>
    </div>
  </div>
  <div class="modal-footer">
    <button class="btn btn-default" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-success" onclick="confirmaReativacao('${id}')">Confirmar Reativação</button>
  </div>`,false,true);
}
async function confirmaReativacao(id){
  const c = await api(`/colaboradores/${id}`);
  const setor = $('re-setor').value || c.setor;
  const adm   = $('re-adm').value   || c.dataAdmissao;
  await api(`/colaboradores/${id}`,'PUT',{...c,status:'Ativo',dataAdmissao:adm,setor});
  toast(`${c.nome} reativado com sucesso`,'success');
  closeModal();
  _colabView='ativos';
  renderColaboradores();
}

