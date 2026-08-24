async function savePrefixoPatrimonio(){
  const v = ($('cfg-pat-prefixo')?.value||'').trim().toUpperCase().replace(/[^A-Z0-9]/g,'');
  if(!v){ toast('Prefixo inválido','error'); return; }
  try{
    await api('/settings','PUT',{'patrimonio.prefixo':v});
    toast(`Prefixo salvo: ${v}`);
    renderConfiguracoes();
  }catch(e){ toast(e.message,'error'); }
}

async function savePublicUrl(){
  const raw = ($('cfg-public-url')?.value||'').trim().replace(/\/+$/, '');
  const statusEl = $('public-url-status');
  if(raw){
    try{ new URL(raw); }
    catch(e){
      if(statusEl) statusEl.innerHTML = '<span style="color:var(--red-text)">URL inválida — use o formato http://... ou https://...</span>';
      return;
    }
  }
  try{
    await api('/settings/public-url','PUT',{url: raw});
    // Atualiza APP_BASE_URL para refletir a mudança imediatamente
    if(raw) APP_BASE_URL = raw;
    if(statusEl) statusEl.innerHTML = raw
      ? `<span style="color:var(--green-text)">Salvo. Links de e-mail usarão: <strong>${raw}</strong></span>`
      : '<span style="color:var(--text3)">Removido — links de e-mail usarão auto-detecção da requisição.</span>';
    toast('URL pública salva');
  }catch(e){ toast(e.message,'error'); }
}

async function saveEmpresa(){
  let logo_base64 = _settings?.empresa?.logo_base64 || '';
  const logoInput = $('cfg-emp-logo');
  if(logoInput?.files?.[0]){
    const file = logoInput.files[0];
    if(file.size > 4 * 1024 * 1024){ toast('Logo muito grande — máx 4 MB', 'error'); return; }
    logo_base64 = await new Promise(res=>{ const r=new FileReader(); r.onload=e=>res(e.target.result); r.readAsDataURL(file); });
  }
  await api('/settings','PUT',{empresa:{nome:$('cfg-emp-nome').value,cnpj:$('cfg-emp-cnpj').value,email:$('cfg-emp-email').value,telefone:$('cfg-emp-tel').value,site:$('cfg-emp-site').value,endereco:$('cfg-emp-end').value,logo_base64}});
  if(_settings.empresa) _settings.empresa.logo_base64 = logo_base64;
  toast('Dados da empresa salvos');
  if(logoInput) logoInput.value='';
  renderConfiguracoes();
}
function previewLogoUpload(input){
  const file=input.files[0];
  if(!file) return;
  if(file.size > 4 * 1024 * 1024){ toast('Logo muito grande — máx 4 MB','error'); input.value=''; return; }
  const r=new FileReader();
  r.onload=e=>{
    const wrap=$('logo-upload-preview');
    if(wrap) wrap.innerHTML=`<div style="font-size:11px;color:var(--text3);margin-bottom:4px">Pré-visualização:</div><div style="padding:6px 10px;background:#fff;border:1px solid var(--border);border-radius:var(--r);display:inline-flex"><img src="${e.target.result}" style="height:28px;object-fit:contain;max-width:120px"></div>`;
  };
  r.readAsDataURL(file);
}
async function removeLogo(){
  await api('/settings','PUT',{empresa:{...(_settings.empresa||{}),logo_base64:''}});
  if(_settings.empresa) _settings.empresa.logo_base64='';
  toast('Logo removido');
  renderConfiguracoes();
}
function previewAparenciaLogo(input, previewId){
  const file = input.files[0];
  if(!file) return;
  const maxBytes = previewId === 'ap-bg-preview' ? AP_BG_MAX_BYTES : AP_LOGO_MAX_BYTES;
  if(file.size > maxBytes){ toast(`Arquivo muito grande (máx ${fmtBytes(maxBytes)})`, 'error'); input.value=''; return; }
  const r = new FileReader();
  r.onload = e => {
    const el = $(previewId);
    if(el) el.innerHTML = `<img src="${e.target.result}" style="max-height:60px;max-width:200px;object-fit:contain;border:1px solid var(--border);border-radius:var(--r);padding:4px">`;
  };
  r.readAsDataURL(file);
}
async function _readFile(inputId){
  const file = $(inputId)?.files[0];
  if(!file) return null;
  return new Promise(res=>{ const r=new FileReader(); r.onload=e=>res(e.target.result); r.readAsDataURL(file); });
}
async function saveAparenciaIdentidade(){
  const favicon = (await _readFile('ap-favicon')) || (_settings?.aparencia?.favicon || '');
  await api('/settings','PUT',{aparencia:{
    ..._settings.aparencia,
    nome_sistema: $('ap-nome')?.value?.trim() || '',
    slogan_sistema: $('ap-slogan')?.value?.trim() || '',
    favicon,
  }});
  const cfg = await api('/settings');
  if(cfg){ _settings = cfg; _applyAparencia(cfg.aparencia||{}, cfg.empresa||{}); }
  toast('Identidade salva');
  if($('ap-favicon')) $('ap-favicon').value='';
  renderConfiguracoes();
}
async function removeFaviconSistema(){
  await api('/settings','PUT',{aparencia:{..._settings.aparencia, favicon:''}});
  if(_settings.aparencia) _settings.aparencia.favicon='';
  _applyAparencia(_settings.aparencia||{}, _settings.empresa||{});
  toast('Favicon removido');
  renderConfiguracoes();
}
async function saveAparenciaLogin(){
  const bg_login = (await _readFile('ap-bg')) || (_settings?.aparencia?.bg_login || '');
  const login_box_transparencia = Math.max(0, Math.min(100, parseInt($('ap-box-transp')?.value || '0') || 0));
  await api('/settings','PUT',{aparencia:{..._settings.aparencia, bg_login, login_box_transparencia}});
  if(_settings.aparencia){ _settings.aparencia.bg_login = bg_login; _settings.aparencia.login_box_transparencia = login_box_transparencia; }
  toast('Configurações de login salvas');
  if($('ap-bg')) $('ap-bg').value='';
  renderConfiguracoes();
}
async function removeBgLogin(){
  await api('/settings','PUT',{aparencia:{..._settings.aparencia, bg_login:''}});
  if(_settings.aparencia) _settings.aparencia.bg_login='';
  _apLoginPreviewBg = '';
  toast('Fundo removido');
  renderConfiguracoes();
}
let _apLoginPreviewBg = '';
function apRangeUpdate(val){
  val = Math.max(0, Math.min(100, +val || 0));
  const range = $('ap-box-transp');
  if(range){ range.value = val; range.style.background = `linear-gradient(to right,#2563eb ${val}%,var(--bg4) ${val}%)`; }
  const num = $('ap-box-transp-num'); if(num) num.value = val;
  const badge = $('ap-box-transp-badge'); if(badge) badge.textContent = val;
  updateLoginPreview();
}
function updateLoginPreview(){
  const pv  = $('ap-login-preview');
  const box = $('ap-login-preview-box');
  if(!pv || !box) return;
  const transp  = parseInt($('ap-box-transp')?.value ? '0') || 0;
  const opacity = ((100 - transp) / 100).toFixed(2);
  const bg = _apLoginPreviewBg || _settings?.aparencia?.bg_login || '';
  pv.style.backgroundImage = bg ? `url(${bg})` : 'none';
  box.style.background = `rgba(255,255,255,${opacity})`;
}
async function saveAparenciaCores(){
  const cor_primaria = $('ap-cor')?.value?.trim() || '';
  const cor_botao    = $('ap-cor-botao')?.value?.trim() || '';
  const cor_hover    = $('ap-cor-hover')?.value?.trim() || '';
  await api('/settings','PUT',{aparencia:{..._settings.aparencia, cor_primaria, cor_botao, cor_hover}});
  if(_settings.aparencia){ _settings.aparencia.cor_primaria=cor_primaria; _settings.aparencia.cor_botao=cor_botao; _settings.aparencia.cor_hover=cor_hover; }
  _applyAparencia(_settings.aparencia||{}, _settings.empresa||{});
  toast('Cores salvas');
  renderConfiguracoes();
}
async function resetAparenciaCores(){
  await api('/settings','PUT',{aparencia:{..._settings.aparencia, cor_primaria:'', cor_botao:'', cor_hover:''}});
  document.documentElement.style.removeProperty('--blue');
  document.documentElement.style.removeProperty('--sb-hover');
  toast('Cores restauradas ao padrão');
  renderConfiguracoes();
}
async function saveAlertas(){
  await api('/settings','PUT',{alertas:{dias_garantia:+$('cfg-al-gar').value,dias_licenca:+$('cfg-al-lic').value,estoque_minimo:$('cfg-al-esq').checked,notif_email:$('cfg-al-email').checked}});
  toast('Configurações de alertas salvas');
}
async function saveRegras(){
  await api('/settings','PUT',{regras_usuario:{exige_termo_alocacao:$('cfg-r-termo').checked,permite_alocar_sem_email:$('cfg-r-email').checked,obriga_vinculo_saida:$('cfg-r-vinculo').checked,max_perifericos_por_colab:+$('cfg-r-maxp').value}});
  toast('Regras salvas');
}

async function addSetor(){
  const nome = $('novo-setor').value.trim();
  if(!nome){toast('Informe o nome do setor','error');return;}
  try{
    await api('/settings/setores','POST',{nome});
    toast('Setor adicionado'); $('novo-setor').value=''; renderConfiguracoes();
  }catch(e){toast(e.message,'error');}
}
async function delSetor(nome){
  await api('/settings/setores/'+encodeURIComponent(nome),'DELETE');
  toast('Setor removido'); renderConfiguracoes();
}

function onlyCepDigits(value){
  return String(value||'').replace(/\D/g,'').slice(0,8);
}
function maskCep(value){
  const digits = onlyCepDigits(value);
  return digits.length > 5 ? digits.slice(0,5) + '-' + digits.slice(5) : digits;
}
function formatUnidadeCep(input){
  input.value = maskCep(input.value);
}
function getUnidadePayload(){
  return {
    nome: $('nu-nome').value,
    tipo: $('nu-tipo').value,
    cep: maskCep($('nu-cep')?.value || ''),
    cidade: $('nu-cidade').value,
    estado: $('nu-estado').value
  };
}
async function lookupUnidadeCep(){
  const cepInput = $('nu-cep');
  const cep = onlyCepDigits(cepInput?.value || '');
  if(!cep) return;
  if(cep.length !== 8){ toast('Informe um CEP com 8 digitos','error'); return; }
  if(cepInput) cepInput.value = maskCep(cep);
  try{
    const data = await api(`/settings/cep/${cep}`);
    if(!data) return;
    if($('nu-cep')) $('nu-cep').value = data.cep || maskCep(cep);
    if($('nu-cidade')) $('nu-cidade').value = data.cidade || '';
    if($('nu-estado')) $('nu-estado').value = data.estado || '';
    toast('Cidade e estado preenchidos pelo CEP');
  }catch(e){
    toast(e.message || 'Nao foi possivel consultar o CEP','error');
  }
}

function openNewUnidade(){
  openModal('Nova Unidade',`
  <div class="form-grid-2">
    <div class="form-group"><label>Nome</label><input id="nu-nome" placeholder="Ex: Filial SP Interior"></div>
    <div class="form-group"><label>Tipo</label>
      <select id="nu-tipo"><option>Sede</option><option>Filial</option><option>Depósito</option><option>Escritório</option><option>DataCenter</option></select>
    </div>
    <div class="form-group"><label>CEP</label>
      <div style="display:flex;gap:8px">
        <input id="nu-cep" inputmode="numeric" maxlength="9" placeholder="00000-000" oninput="formatUnidadeCep(this)" onblur="lookupUnidadeCep()">
        <button class="btn btn-default btn-sm" type="button" onclick="lookupUnidadeCep()">Buscar</button>
      </div>
    </div>
    <div class="form-group"><label>Cidade</label><input id="nu-cidade"></div>
    <div class="form-group"><label>Estado</label><input id="nu-estado" placeholder="SP"></div>
  </div>
  <div class="modal-footer">
    <button class="btn btn-default" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="saveNewUnidade()">Salvar</button>
  </div>`,false,true);
}
async function saveNewUnidade(){
  await api('/settings/unidades','POST',getUnidadePayload());
  toast('Unidade criada');closeModal();renderConfiguracoes();
}
function editUnidade(u){
  openModal('Editar Unidade',`
  <div class="form-grid-2">
    <div class="form-group"><label>Nome</label><input id="nu-nome" value="${escAttr(u.nome)}"></div>
    <div class="form-group"><label>Tipo</label>
      <select id="nu-tipo">${['Sede','Filial','Depósito','Escritório','DataCenter'].map(t=>`<option ${t===u.tipo?'selected':''}>${t}</option>`).join('')}</select>
    </div>
    <div class="form-group"><label>CEP</label>
      <div style="display:flex;gap:8px">
        <input id="nu-cep" inputmode="numeric" maxlength="9" placeholder="00000-000" value="${escAttr(u.cep||'')}" oninput="formatUnidadeCep(this)" onblur="lookupUnidadeCep()">
        <button class="btn btn-default btn-sm" type="button" onclick="lookupUnidadeCep()">Buscar</button>
      </div>
    </div>
    <div class="form-group"><label>Cidade</label><input id="nu-cidade" value="${escAttr(u.cidade)}"></div>
    <div class="form-group"><label>Estado</label><input id="nu-estado" value="${escAttr(u.estado)}"></div>
  </div>
  <div class="modal-footer">
    <button class="btn btn-default" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-primary" onclick="saveEditUnidade('${u.id}')">Salvar</button>
  </div>`,false,true);
}
async function saveEditUnidade(id){
  await api('/settings/unidades/'+id,'PUT',getUnidadePayload());
  toast('Unidade atualizada');closeModal();renderConfiguracoes();
}
async function delUnidade(id){
  await api('/settings/unidades/'+id,'DELETE');
  toast('Unidade removida'); renderConfiguracoes();
}

