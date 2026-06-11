// ══════════════════════════════════════════════════════════════════════════
// USUÁRIOS DO SISTEMA
// ══════════════════════════════════════════════════════════════════════════
let PERFIS_SYS=['Administrador','Técnico TI','Gestor','Visualizador'];
const PERFIL_COR={Administrador:'red','Técnico TI':'blue',Gestor:'amber',Visualizador:'gray'};
const MODULO_LABEL={dashboard:'Dashboard',entrada:'Entrada de Itens',ativos:'Ativos de TI',insumos:'Insumos & Periféricos',colaboradores:'Colaboradores',alocacoes:'Alocações',auditorias:'Auditorias',qrcode:'QR Code',licencas:'Licenças',alertas:'Alertas',manutencao:'Manutenção',system_users:'Usuários do Sistema',configuracoes:'Configurações'};

async function renderSystemUsers(){
  const [data, perfisData] = await Promise.all([api('/system-users'), api('/system-users/perfis')]);
  PERFIS_SYS = Object.keys(perfisData);

  $('content').innerHTML=`
  <div class="flex-between mb-16">
    <div style="font-size:13px;color:var(--text2)">${data.length} usuários cadastrados · ${data.filter(u=>u.status==='Ativo').length} ativos</div>
    <button class="btn btn-primary" onclick="openNewSysUser()">Novo Usuário</button>
  </div>
  <div class="card mb-16"><div class="table-wrap"><table>
    <thead><tr><th>Username</th><th>Nome</th><th>E-mail</th><th>Perfil</th><th>Status</th><th>Último Acesso</th><th>Criado em</th><th>Ações</th></tr></thead>
    <tbody>${data.map(u=>`<tr>
      <td class="mono" style="font-weight:700">${esc(u.username)}</td>
      <td style="font-weight:600">${esc(u.nome)}</td>
      <td style="font-size:12px;color:var(--text2)">${esc(u.email)}</td>
      <td>${badge(u.perfil,PERFIL_COR[u.perfil]||'gray')}</td>
      <td>${badge(u.status,u.status==='Ativo'?'green':'red')}</td>
      <td style="font-size:12px;color:var(--text3)">${u.ultimoAcesso?new Date(u.ultimoAcesso).toLocaleString('pt-BR'):'—'}</td>
      <td style="font-size:12px;color:var(--text3)">${fmtDate(u.criadoEm)}</td>
      <td><div class="flex-gap">
        <button class="btn btn-default btn-icon btn-sm" onclick="editSysUser('${u.id}','${esc(u.username)}','${esc(u.nome)}','${esc(u.email)}','${u.perfil}','${u.status}')">Editar</button>
        <button class="btn ${u.status==='Ativo'?'btn-warning':'btn-success'} btn-sm" onclick="toggleSysUser('${u.id}','${esc(u.nome)}')">${u.status==='Ativo'?'Desativar':'Ativar'}</button>
        <button class="btn btn-default btn-sm" onclick="openResetSenha('${u.id}','${esc(u.username)}')">Senha</button>
      </div></td>
    </tr>`).join('')}
    </tbody>
  </table></div></div>`;
}

function openNewSysUser(){
  openModal('Novo Usuário do Sistema',`
  <div class="form-grid-2">
    <div class="form-group span-2"><label>Nome Completo</label><input id="su-nome"></div>
    <div class="form-group"><label>Username</label><input id="su-user" placeholder="ex: joao.silva"></div>
    <div class="form-group"><label>Senha Inicial</label><input id="su-senha" type="password" placeholder="mín. 8 caracteres"></div>
    <div class="form-group"><label>E-mail</label><input id="su-email" type="email"></div>
    <div class="form-group"><label>Perfil de Acesso</label>
      <select id="su-perfil">${PERFIS_SYS.map(p=>`<option>${p}</option>`).join('')}</select>
    </div>
  </div>
  <div class="info-box blue">As permissões são definidas automaticamente pelo perfil selecionado.</div>
  <div class="modal-footer">
    <button class="btn btn-default" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="saveNewSysUser()">Criar Usuário</button>
  </div>`);
}
async function saveNewSysUser(){
  if($('su-senha').value.length<8){toast('Senha deve ter ao menos 8 caracteres','error');return;}
  try{
    await api('/system-users','POST',{nome:$('su-nome').value,username:$('su-user').value,email:$('su-email').value,perfil:$('su-perfil').value,senha:$('su-senha').value});
    toast('Usuário criado');closeModal();renderSystemUsers();
  }catch(e){toast(e.message,'error');}
}

function editSysUser(id,username,nome,email,perfil,status){
  openModal('Editar Usuário do Sistema',`
  <div class="form-grid-2">
    <div class="form-group span-2"><label>Nome Completo</label><input id="su-nome" value="${esc(nome)}"></div>
    <div class="form-group"><label>Username</label><input id="su-user" value="${esc(username)}" disabled style="background:var(--bg3);color:var(--text3)"></div>
    <div class="form-group"><label>E-mail</label><input id="su-email" type="email" value="${esc(email)}"></div>
    <div class="form-group"><label>Perfil</label>
      <select id="su-perfil">${PERFIS_SYS.map(p=>`<option ${p===perfil?'selected':''}>${p}</option>`).join('')}</select>
    </div>
    <div class="form-group"><label>Status</label>
      <select id="su-status"><option ${status==='Ativo'?'selected':''}>Ativo</option><option ${status==='Inativo'?'selected':''}>Inativo</option></select>
    </div>
  </div>
  <div class="modal-footer">
    <button class="btn btn-default" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="saveEditSysUser('${id}')">Salvar</button>
  </div>`);
}
async function saveEditSysUser(id){
  await api(`/system-users/${id}`,'PUT',{nome:$('su-nome').value,email:$('su-email').value,perfil:$('su-perfil').value,status:$('su-status').value});
  toast('Usuário atualizado');closeModal();renderSystemUsers();
}

async function toggleSysUser(id,nome){
  const r=await api(`/system-users/${id}/toggle`,'POST',{});
  toast(`${nome} → ${r.status}`);renderSystemUsers();
}

function openResetSenha(id,username){
  openModal(`Redefinir Senha — ${username}`,`
  <div class="form-group"><label>Nova Senha</label><input id="rs-nova" type="password" placeholder="mín. 8 caracteres"></div>
  <div class="form-group"><label>Confirmar</label><input id="rs-conf" type="password" placeholder="repita a senha"></div>
  <div class="modal-footer">
    <button class="btn btn-default" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-danger" onclick="doResetSenha('${id}')">Redefinir</button>
  </div>`,false,true);
}
async function doResetSenha(id){
  if($('rs-nova').value.length<8){toast('Mín. 8 caracteres','error');return;}
  if($('rs-nova').value!==$('rs-conf').value){toast('Senhas não coincidem','error');return;}
  await api(`/system-users/${id}/reset-senha`,'POST',{senha:$('rs-nova').value});
  toast('Senha redefinida com sucesso');closeModal();
}

function novoPerfilModal(){
  const ALL_MODS = Object.entries(MODULO_LABEL);
  const moduloChecks = ALL_MODS.map(([k,lbl])=>`
    <label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer;padding:6px 10px;border-radius:var(--r);border:1px solid var(--border);background:var(--bg3)">
      <input type="checkbox" id="ep-mod-${k}" style="width:auto">
      ${lbl}
    </label>`).join('');

  const CORES = ['blue','green','amber','purple','red','gray'];
  const colorOpts = CORES.map((c,i)=>`<option value="${c}" ${i===0?'selected':''}>${c}</option>`).join('');

  openModal('Novo Perfil de Acesso',`
    <div class="info-box blue" style="margin-bottom:14px">
      Defina um nome único para o perfil, suas permissões gerais e os módulos que ele poderá acessar.
    </div>
    <div class="form-grid-2">
      <div class="form-group">
        <label>Nome do Perfil <span style="color:var(--red-text)">*</span></label>
        <input id="ep-nome" placeholder="Ex: Suporte, Analista TI, Auditor…" maxlength="40">
        <div class="hint">Sem espaços especiais. Será exibido na lista de usuários.</div>
      </div>
      <div class="form-group">
        <label>Cor</label>
        <select id="ep-cor">${colorOpts}</select>
      </div>
      <div class="form-group" style="grid-column:span 2">
        <label>Descrição do perfil</label>
        <input id="ep-label" placeholder="Ex: Acesso de suporte ao inventário de TI">
      </div>
    </div>
    <div style="font-size:12px;font-weight:600;color:var(--text2);margin-bottom:8px">PERMISSÕES GERAIS</div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px;margin-bottom:16px">
      <label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer;padding:8px 10px;border-radius:var(--r);border:1px solid var(--border);background:var(--bg3)">
        <input type="checkbox" id="ep-editar" style="width:auto"> Pode Editar
      </label>
      <label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer;padding:8px 10px;border-radius:var(--r);border:1px solid var(--border);background:var(--bg3)">
        <input type="checkbox" id="ep-excluir" style="width:auto"> Pode Excluir
      </label>
      <label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer;padding:8px 10px;border-radius:var(--r);border:1px solid var(--border);background:var(--bg3)">
        <input type="checkbox" id="ep-exportar" style="width:auto"> Pode Exportar
      </label>
    </div>
    <div style="font-size:12px;font-weight:600;color:var(--text2);margin-bottom:8px">MÓDULOS LIBERADOS</div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:6px;margin-bottom:16px">
      ${moduloChecks}
    </div>
    <div class="modal-footer">
      <button class="btn btn-default" onclick="closeModal()">Cancelar</button>
      <button class="btn btn-primary" onclick="criarPerfil()">Criar Perfil</button>
    </div>`,false,true);
}

async function criarPerfil(){
  const nome = ($('ep-nome').value||'').trim();
  if(!nome){ toast('Informe o nome do perfil','error'); return; }
  if(PERFIS_SYS.map(p=>p.toLowerCase()).includes(nome.toLowerCase())){
    toast('Já existe um perfil com este nome','error'); return;
  }
  const modulos = Object.keys(MODULO_LABEL).filter(k=>document.getElementById('ep-mod-'+k)?.checked);
  const body = {
    label:         ($('ep-label').value||'').trim() || nome,
    cor:           $('ep-cor').value,
    pode_editar:   $('ep-editar').checked,
    pode_excluir:  $('ep-excluir').checked,
    pode_exportar: $('ep-exportar').checked,
    modulos,
  };
  await api(`/system-users/perfis/${encodeURIComponent(nome)}`,'PUT',body);
  toast(`Perfil "${nome}" criado com sucesso`,'success');
  closeModal();
  renderConfiguracoes();
}

function editPerfilPerms(perfil, info){
  const ALL_MODS = Object.entries(MODULO_LABEL);
  const moduloChecks = ALL_MODS.map(([k,lbl])=>`
    <label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer;padding:6px 10px;border-radius:var(--r);border:1px solid var(--border);background:var(--bg3)">
      <input type="checkbox" id="ep-mod-${k}" ${(info.modulos||[]).includes(k)?'checked':''} style="width:auto">
      ${lbl}
    </label>`).join('');

  const CORES = ['red','blue','amber','green','purple','gray'];
  const colorOpts = CORES.map(c=>`<option value="${c}" ${info.cor===c?'selected':''}>${c}</option>`).join('');

  openModal(`Editar Perfil — ${perfil}`,`
    <div class="info-box blue" style="margin-bottom:14px">
      As alterações afetam imediatamente os usuários com este perfil. O perfil <strong>Administrador</strong> tem acesso total garantido pelo sistema.
    </div>
    <div class="form-grid-2">
      <div class="form-group" style="grid-column:span 2">
        <label>Descrição do perfil</label>
        <input id="ep-label" value="${esc(info.label||'')}">
      </div>
      <div class="form-group">
        <label>Cor</label>
        <select id="ep-cor">${colorOpts}</select>
      </div>
    </div>
    <div style="font-size:12px;font-weight:600;color:var(--text2);margin-bottom:8px">PERMISSÕES GERAIS</div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px;margin-bottom:16px">
      <label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer;padding:8px 10px;border-radius:var(--r);border:1px solid var(--border);background:var(--bg3)">
        <input type="checkbox" id="ep-editar" ${info.pode_editar?'checked':''} style="width:auto"> Pode Editar
      </label>
      <label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer;padding:8px 10px;border-radius:var(--r);border:1px solid var(--border);background:var(--bg3)">
        <input type="checkbox" id="ep-excluir" ${info.pode_excluir?'checked':''} style="width:auto"> Pode Excluir
      </label>
      <label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer;padding:8px 10px;border-radius:var(--r);border:1px solid var(--border);background:var(--bg3)">
        <input type="checkbox" id="ep-exportar" ${info.pode_exportar?'checked':''} style="width:auto"> Pode Exportar
      </label>
    </div>
    <div style="font-size:12px;font-weight:600;color:var(--text2);margin-bottom:8px">MÓDULOS LIBERADOS</div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:6px;margin-bottom:16px">
      ${moduloChecks}
    </div>
    <div class="modal-footer">
      <button class="btn btn-default" onclick="closeModal()">Cancelar</button>
      <button class="btn btn-primary" onclick="savePerfilPerms('${perfil}')">Salvar Alterações</button>
    </div>`,false,true);
}

async function savePerfilPerms(perfil){
  const modulos = Object.keys(MODULO_LABEL).filter(k=>document.getElementById('ep-mod-'+k)?.checked);
  const body = {
    label:         $('ep-label').value.trim(),
    cor:           $('ep-cor').value,
    pode_editar:   $('ep-editar').checked,
    pode_excluir:  $('ep-excluir').checked,
    pode_exportar: $('ep-exportar').checked,
    modulos,
  };
  if(!body.label){ toast('Informe a descrição do perfil','error'); return; }
  await api(`/system-users/perfis/${encodeURIComponent(perfil)}`,'PUT',body);
  toast(`Perfil "${perfil}" atualizado com sucesso`,'success');
  closeModal();
  renderConfiguracoes();
}

