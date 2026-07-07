// ─── Globals ───────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const fmtDate = s => s ? new Date(s.length===10 ? s+'T00:00:00' : s).toLocaleDateString('pt-BR') : '—';
const fmtDateTime = s => s ? new Date(s).toLocaleString('pt-BR',{dateStyle:'short',timeStyle:'short'}) : '—';
// URL base: usa window.location.origin (sempre correto) e atualiza com o valor
// detectado pelo servidor ao carregar as configurações (via /api/settings)
let APP_BASE_URL = window.location.origin;
const fmtCur = v => (v||0).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
const fmtBytes = v => {
  const n = Number(v) || 0;
  if(n < 1024) return n + ' B';
  if(n < 1048576) return (n / 1024).toFixed(1) + ' KB';
  return (n / 1048576).toFixed(1) + ' MB';
};
const AP_LOGO_MAX_BYTES = 4 * 1024 * 1024;
const AP_BG_MAX_BYTES = 8 * 1024 * 1024;
const ASSET_CATEGORY_IMAGE_MAX_BYTES = 1024 * 1024;
const daysUntil = d => { if(!d) return 9999; return Math.ceil((new Date(d+'T00:00:00')-new Date())/86400000); };
const esc = s => String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const escAttr = s => esc(s);
const jsArg = s => escAttr(JSON.stringify(String(s||'')));

const ICONS = {
  sun:'<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>',
  moon:'<path d="M12 3a6 6 0 0 0 9 7.5A9 9 0 1 1 12 3Z"/>',
  app:'<rect x="2" y="4" width="20" height="6" rx="2"/><rect x="2" y="14" width="20" height="6" rx="2"/><circle cx="6" cy="7" r="1.5" fill="currentColor" stroke="none"/><circle cx="6" cy="17" r="1.5" fill="currentColor" stroke="none"/><path d="M10 7h5M10 17h5"/>',
  dashboard:'<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 22V12h6v10"/>',
  alertas:'<path d="M10.3 21a2 2 0 0 0 3.4 0"/><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/>',
  insumos:'<path d="m7.5 4.27 9 5.15"/><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="M3.3 7l8.7 5 8.7-5M12 22V12"/>',
  ativos:'<rect width="20" height="14" x="2" y="3" rx="2"/><path d="M12 17v4"/><path d="M8 21h8"/><path d="M7 8h2M11 8h6M7 12h4"/>',
  alocacoes:'<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><circle cx="12" cy="12" r="2"/><path d="M8 20c0-2.2 1.8-4 4-4s4 1.8 4 4"/>',
  qrcode:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3h-3zM20 14h1M14 20h1M18 20h3v1"/>',
  image:'<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="8.5" cy="10" r="1.5"/><path d="m21 15-5-5L5 19"/>',
  upload:'<path d="M12 16V4"/><path d="m7 9 5-5 5 5"/><path d="M20 16v3a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-3"/>',
  auditorias:'<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
  manutencao:'<path d="M14.7 6.3a4 4 0 0 0-5 5L3 18v3h3l6.7-6.7a4 4 0 0 0 5-5l-2.4 2.4-2.6-2.6 2.4-2.4Z"/><circle cx="19" cy="5" r="3"/>',
  licencas:'<path d="m21 2-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0 3 3L22 7l-3-3m-3.5 3.5L19 4"/>',
  colaboradores:'<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
  system_users:'<path d="M20 13c0 5-3.5 7.5-8 9-4.5-1.5-8-4-8-9V5l8-3 8 3v8Z"/><path d="M9 12l2 2 4-4"/>',
  configuracoes:'<path d="M12 15.5A3.5 3.5 0 1 0 12 8a3.5 3.5 0 0 0 0 7.5Z"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6V20a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1-.6 1.7 1.7 0 0 0-1.88.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1H4a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 .6-1 1.7 1.7 0 0 0-.34-1.88l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6V4a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 .6 1.7 1.7 0 0 0 1.88-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9c.2.38.4.74.6 1H20a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-.51 1Z"/>',
  entrada:'<path d="M3 9h18v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9z"/><path d="M3 9l2-5h14l2 5"/><path d="M12 12v4M9.5 14.5 12 17l2.5-2.5"/>',
  search:'<circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  download:'<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/>',
  save:'<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2Z"/><path d="M17 21v-8H7v8M7 3v5h8"/>',
  edit:'<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
  eye:'<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
  warning:'<path d="m21.73 18-8-14a2 2 0 0 0-3.46 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4M12 17h.01"/>',
  clipboard:'<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>',
  printer:'<path d="M6 9V2h12v7"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><path d="M6 14h12v8H6z"/>',
  mapPin:'<path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="3"/>',
  smartphone:'<rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/>',
  undo:'<path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-15-6.7L3 13"/>',
  check:'<path d="M20 6 9 17l-5-5"/>',
  x:'<path d="M18 6 6 18M6 6l12 12"/>',
  square:'<rect x="5" y="5" width="14" height="14" rx="2"/>',
  flag:'<path d="M4 22V4"/><path d="M4 4h12l-1 4 1 4H4"/>',
  trash:'<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/>',
  menu:'<line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/>',
};

function svgIcon(name){
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor">${ICONS[name]||ICONS.app}</svg>`;
}
function inlineIcon(name){
  return `<svg class="inline-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">${ICONS[name]||ICONS.app}</svg>`;
}

function applyTheme(theme){
  document.documentElement.dataset.theme = theme;
  localStorage.setItem('ticontrol-theme', theme);
  const icon = $('theme-icon');
  const label = $('theme-label');
  if(icon) icon.innerHTML = theme === 'dark' ? ICONS.sun : ICONS.moon;
  if(label) label.textContent = theme === 'dark' ? 'Claro' : 'Escuro';
}

function toggleTheme(){
  applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
}

applyTheme(localStorage.getItem('ticontrol-theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));
document.querySelector('.sb-logo-icon').innerHTML = svgIcon('app');
const sbToggleIcon = $('sb-toggle-icon');
if(sbToggleIcon) sbToggleIcon.innerHTML = ICONS.menu;
const hdrBellIcon = $('hdr-bell-icon');
if(hdrBellIcon) hdrBellIcon.innerHTML = ICONS.alertas;
document.querySelectorAll('.nav-item').forEach(btn => {
  const icon = btn.querySelector('.icon');
  if(icon) icon.innerHTML = svgIcon(btn.dataset.module);
});

function toggleSidebar(){
  const sb=$('sidebar'), ov=$('sb-overlay');
  if(window.innerWidth<=768){
    sb.classList.toggle('sb-open');
    if(ov) ov.classList.toggle('show');
  } else {
    sb.classList.toggle('sb-collapsed');
  }
}

const BADGE_STATUS = {Alocado:'blue',Disponível:'green',Ativo:'green',Manutenção:'amber','Em manutenção':'amber',Inativo:'red',
                     Assinado:'green',Pendente:'amber','Não gerado':'gray',Encerrado:'gray',
                     Férias:'blue',Afastado:'amber'};
const badge = (txt,type) => `<span class="badge badge-${type||(BADGE_STATUS[txt]||'gray')}">${esc(txt)}</span>`;

const PERFIL_COLOR = {Administrador:'red','Técnico TI':'blue',Gestor:'amber',Visualizador:'gray'};
const STATUS_COLAB_COLOR = {Ativo:'green',Inativo:'red',Férias:'blue',Afastado:'amber'};

let _colab_cache = [];
let _termoAvulsoTipos = ['VPN','BYOD','Confidencialidade','Outro'];
let _termoAvulsoModelos = {};
let _activeTermAvulsoTipo = '';
let _settings  = { setores:[], unidades:[], categorias_config:{}, categorias:[] };
const APP_VERSION = window.TICONTROL_BOOT?.buildVersion || 'dev';
let _pendingDeleteBackup = null;
let _assetViewMode = localStorage.getItem('ticontrol-assets-view') || 'cards';
if(!['cards','table'].includes(_assetViewMode)) _assetViewMode = 'cards';
let _srchTimer = null;
function debounce(fn, ms=300){ clearTimeout(_srchTimer); _srchTimer=setTimeout(fn,ms); }

function _applyAparencia(aparencia, empresa){
  const nomeSistema = aparencia.nome_sistema || 'TI Control';
  const sloganSistema = aparencia.slogan_sistema || 'Gestão de Ativos';
  const logoSistema = aparencia.logo_sistema || empresa.logo_base64 || '';
  const favicon = aparencia.favicon || '';
  const nomeEmpresa = empresa.nome || '';

  // Título da aba
  document.title = nomeSistema;
  const titleEl = document.getElementById('app-title');
  if(titleEl) titleEl.textContent = nomeSistema;
  let favEl = document.getElementById('app-favicon');
  if(!favEl){
    favEl = document.createElement('link');
    favEl.id = 'app-favicon';
    favEl.rel = 'icon';
    document.head.appendChild(favEl);
  }
  favEl.href = favicon || '/static/bg.png';

  // Sidebar logo
  const sbIcon = document.getElementById('sb-logo-icon');
  const sbNome = document.getElementById('sb-logo-nome');
  const sbSub  = document.getElementById('sb-logo-sub');
  if(sbNome) sbNome.textContent = nomeSistema;
  if(sbSub)  sbSub.textContent  = sloganSistema;
  if(sbIcon){
    if(logoSistema){
      sbIcon.innerHTML = `<img src="${logoSistema}" style="width:30px;height:30px;object-fit:contain;border-radius:6px">`;
      sbIcon.style.background = 'transparent';
      sbIcon.style.border = 'none';
    } else {
      sbIcon.innerHTML = svgIcon('app');
    }
  }

  // Footer
  const footerSistema  = document.getElementById('footer-sistema');
  const footerEmpresa  = document.getElementById('footer-empresa');
  if(footerSistema) footerSistema.textContent = `${nomeSistema} · v${APP_VERSION}`;
  if(footerEmpresa) footerEmpresa.textContent = nomeEmpresa;

  // Auto-preenche empresa na etiqueta se ainda não foi preenchido pelo usuário
  if(nomeEmpresa && !_lblCfg.empresa) _lblCfg.empresa = nomeEmpresa;

  // Cores customizadas via CSS variables
  ['--blue','--blue-hover','--button-primary','--button-primary-hover','--sb-hover'].forEach(prop=>document.documentElement.style.removeProperty(prop));
  if(aparencia.cor_primaria){
    document.documentElement.style.setProperty('--blue', aparencia.cor_primaria);
    document.documentElement.style.setProperty('--blue-hover', aparencia.cor_primaria);
    document.documentElement.style.setProperty('--button-primary', aparencia.cor_botao || aparencia.cor_primaria);
    document.documentElement.style.setProperty('--button-primary-hover', aparencia.cor_botao || aparencia.cor_primaria);
  }
  if(aparencia.cor_botao){
    document.documentElement.style.setProperty('--button-primary', aparencia.cor_botao);
    document.documentElement.style.setProperty('--button-primary-hover', aparencia.cor_botao);
  }
  if(aparencia.cor_hover){
    document.documentElement.style.setProperty('--sb-hover', aparencia.cor_hover);
  }
}

// Helpers para selects de setor/unidade
function setorOpts(sel=''){
  return _settings.setores.map(s=>`<option ${s===sel?'selected':''}>${esc(s)}</option>`).join('');
}
function unidadeOpts(sel=''){
  return _settings.unidades.map(u=>`<option ${u.nome===sel?'selected':''}>${esc(u.nome)}</option>`).join('');
}

// Retorna true se a categoria deve alocar para UNIDADE (não colaborador)
function catIsUnidade(cat){
  const cfg = _settings.categorias_config[cat];
  return cfg && cfg.tipo_alocacao === 'unidade';
}
function assetCategoryConfig(cat){
  return (_settings.categorias_config && _settings.categorias_config[cat]) || {};
}
function assetCategoryImage(cat){
  return assetCategoryConfig(cat).image || '';
}

// ─── API ──────────────────────────────────────────────────────────────────
let _redirectingToLogin = false;

function showSessionExpired(){
  const content = $('content');
  if(content){
    content.innerHTML = `
      <div class="card" style="padding:20px;max-width:520px;margin:64px auto;text-align:center">
        <h3 style="margin:0 0 8px">Sessão expirada</h3>
        <p style="margin:0 0 16px;color:var(--text2)">Entre novamente para carregar os dados do sistema.</p>
        <button class="btn btn-primary" onclick="window.location.href='/login'">Entrar novamente</button>
      </div>`;
  }
}

async function api(path, method='GET', body=null) {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const isFormData = body instanceof FormData;
  const opts = {
    method,
    credentials: 'include',  // garante envio do cookie de sessão
    headers: isFormData ? {} : {'Content-Type':'application/json'}
  };
  if (csrf && method !== 'GET') opts.headers['X-CSRFToken'] = csrf;
  if (body) opts.body = isFormData ? body : JSON.stringify(body);
  let r;
  try {
    r = await fetch('/api'+path, opts);
  } catch(networkErr) {
    toast('Erro de rede: ' + networkErr.message, 'error');
    throw networkErr;
  }
  if (r.status === 401) {
    if (!_redirectingToLogin) {
      _redirectingToLogin = true;
      showSessionExpired();
      toast('Sessão expirada — redirecionando para login...', 'error');
      setTimeout(() => { window.location.replace('/login'); }, 1200);
    }
    return null;
  }
  if (r.status === 403) {
    const j = await r.json().catch(() => ({}));
    toast(j.error || 'Sem permissão para esta ação', 'error');
    throw new Error(j.error || '403');
  }
  let json;
  try { json = await r.json(); } catch(e) { throw new Error('Resposta inválida do servidor'); }
  if (r.status === 400 && json.code === 'csrf_expired') {
    toast(json.error || 'Sessão expirada. Recarregando...', 'error');
    setTimeout(() => window.location.reload(), 900);
    throw new Error(json.error || 'CSRF expirado');
  }
  if (!r.ok) throw new Error(json.error || `Erro ${r.status}`);
  return json;
}

function toast(msg,type='success'){
  const t=$('toast'); t.textContent=msg; t.className=`show ${type}`;
  setTimeout(()=>t.className='',2600);
}

// ─── Anexos ───────────────────────────────────────────────────────────────
const ATTACH_ENTITY_LABEL = {asset:'ativo', maintenance:'OS', license:'licença'};
const ATTACH_CATEGORIES = ['Documento','Nota Fiscal','Contrato','Foto','Laudo','Orçamento','Comprovante'];

function attachmentPanel(entityType, entityId, title='Anexos'){
  return `<div style="margin-top:16px" id="attach-panel-${entityType}-${entityId}">
    <div class="flex-between" style="margin-bottom:10px;gap:10px;flex-wrap:wrap">
      <div class="section-title" style="margin-bottom:0">${title}</div>
      <button class="btn btn-default btn-sm" onclick="openAttachmentUpload('${entityType}','${entityId}')">Adicionar anexo</button>
    </div>
    <div id="attach-list-${entityType}-${entityId}" style="font-size:13px;color:var(--text3)">Carregando anexos...</div>
  </div>`;
}

async function loadAttachments(entityType, entityId){
  const el = document.getElementById(`attach-list-${entityType}-${entityId}`);
  if(!el) return;
  try{
    const data = await api(`/attachments/${entityType}/${entityId}`);
    if(!data.length){
      el.innerHTML = `<div style="padding:10px 0;color:var(--text3)">Nenhum anexo cadastrado.</div>`;
      return;
    }
    el.innerHTML = data.map(a=>`
      <div class="alert-row" style="padding:9px 0;gap:10px;align-items:flex-start">
        <div style="flex:1;min-width:0">
          <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
            ${badge(a.category||'Documento','gray')}
            <strong style="font-size:13px;word-break:break-word">${esc(a.originalName)}</strong>
          </div>
          <div style="font-size:11px;color:var(--text3);margin-top:3px">
            ${fmtBytes(a.size)} · ${esc(a.uploadedBy||'sistema')} · ${fmtDateTime(a.uploadedAt)}
          </div>
          ${a.description?`<div style="font-size:12px;color:var(--text2);margin-top:4px">${esc(a.description)}</div>`:''}
        </div>
        <div class="flex-gap" style="flex-wrap:wrap;justify-content:flex-end">
          <a class="btn btn-default btn-sm" href="/api/attachments/files/${a.id}" download>Baixar</a>
          <button class="btn btn-danger btn-sm" onclick="deleteAttachment('${a.id}','${entityType}','${entityId}')">Excluir</button>
        </div>
      </div>`).join('');
  }catch(e){
    el.innerHTML = `<div style="color:var(--red-text)">Falha ao carregar anexos: ${esc(e.message)}</div>`;
  }
}

function openAttachmentUpload(entityType, entityId){
  openModal(`Adicionar anexo — ${ATTACH_ENTITY_LABEL[entityType]||entityType}`,`
    <div class="form-group"><label>Arquivo</label><input id="att-file" type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.txt,.csv,.doc,.docx,.xls,.xlsx"></div>
    <div class="form-grid-2">
      <div class="form-group"><label>Categoria</label><select id="att-cat">${ATTACH_CATEGORIES.map(c=>`<option>${c}</option>`).join('')}</select></div>
      <div class="form-group"><label>Limite</label><input value="8 MB" disabled></div>
    </div>
    <div class="form-group"><label>Descrição</label><textarea id="att-desc" style="min-height:80px;resize:vertical" placeholder="Ex: NF de compra, contrato de garantia, foto do estado físico..."></textarea></div>
    <div class="modal-footer"><button class="btn btn-default" onclick="closeModal()">Cancelar</button><button class="btn btn-primary" onclick="uploadAttachment('${entityType}','${entityId}')">Enviar Anexo</button></div>
  `);
}

async function uploadAttachment(entityType, entityId){
  const file = $('att-file')?.files?.[0];
  if(!file){toast('Selecione um arquivo.','error');return;}
  if(file.size > 8 * 1024 * 1024){toast('Arquivo maior que 8 MB.','error');return;}
  const fd = new FormData();
  fd.append('file', file);
  fd.append('category', $('att-cat').value);
  fd.append('description', $('att-desc').value);
  await api(`/attachments/${entityType}/${entityId}`,'POST',fd);
  toast('Anexo enviado');
  closeModal();
  await loadAttachments(entityType, entityId);
}

async function deleteAttachment(id, entityType, entityId){
  if(!confirm('Excluir este anexo?')) return;
  await api(`/attachments/files/${id}`,'DELETE');
  toast('Anexo removido');
  await loadAttachments(entityType, entityId);
}

// ─── Modal ────────────────────────────────────────────────────────────────
function openModal(title,html,wide=false,narrow=false){
  $('modal-title').textContent=title;
  $('modal-body').innerHTML=html;
  $('modal-box').className='modal-box'+(wide?' wide':narrow?' narrow':'');
  $('modal-overlay').style.display='flex';
}
function closeModal(){ $('modal-overlay').style.display='none'; }
$('modal-overlay').addEventListener('click',e=>{ if(e.target===$('modal-overlay')) closeModal(); });

// ─── Nav ──────────────────────────────────────────────────────────────────
const PAGE_TITLES = {dashboard:'Dashboard',alertas:'Central de Alertas',insumos:'Insumos & Periféricos',
  entrada:'Entrada de Itens',
  ativos:'Ativos de TI',alocacoes:'Alocações & Termos Digitais',qrcode:'QR Code & Etiquetas',
  auditorias:'Campanhas de Auditoria',
  manutencao:'Manutenção de Ativos',
  licencas:'Controle de Licenças',colaboradores:'Colaboradores',system_users:'Usuários do Sistema',configuracoes:'Configurações'};
const NAV_STORAGE_KEY = 'ticontrol-current-module';
let _currentUser = null;
let _allowedModules = null;

function isValidModule(mod){
  return Object.prototype.hasOwnProperty.call(PAGE_TITLES, mod);
}

function isAllowedModule(mod){
  return isValidModule(mod) && (!_allowedModules || _allowedModules.has(mod));
}

function firstAllowedModule(){
  if(isAllowedModule('dashboard')) return 'dashboard';
  return Array.from(_allowedModules || []).find(isValidModule) || 'dashboard';
}

function moduleFromHash(){
  const mod = decodeURIComponent((window.location.hash || '').replace(/^#/, ''));
  return isAllowedModule(mod) ? mod : null;
}

function moduleFromStorage(){
  const mod = localStorage.getItem(NAV_STORAGE_KEY);
  return isAllowedModule(mod) ? mod : null;
}

function applyProfileNavigation(me){
  _currentUser = me || null;
  const modules = Array.isArray(me?.uiModules) ? me.uiModules.filter(isValidModule) : Object.keys(PAGE_TITLES);
  _allowedModules = new Set(modules.length ? modules : ['dashboard']);
  document.body.dataset.perfil = me?.perfil || '';

  document.querySelectorAll('.nav-item').forEach(btn=>{
    btn.hidden = !isAllowedModule(btn.dataset.module);
  });

  document.querySelectorAll('.sb-section').forEach(section=>{
    let node = section.nextElementSibling;
    let hasVisibleItem = false;
    while(node && !node.classList.contains('sb-section')){
      if(node.classList.contains('nav-item') && !node.hidden){
        hasVisibleItem = true;
        break;
      }
      node = node.nextElementSibling;
    }
    section.hidden = !hasVisibleItem;
  });

  if(!moduleFromStorage()) localStorage.removeItem(NAV_STORAGE_KEY);
}

function setActiveModule(mod){
  document.querySelectorAll('.nav-item').forEach(btn=>{
    btn.classList.toggle('active', btn.dataset.module === mod);
  });
  $('page-title').textContent = PAGE_TITLES[mod] || '';
}

async function navigateTo(mod, {updateHash=true}={}){
  const next = isAllowedModule(mod) ? mod : firstAllowedModule();
  setActiveModule(next);
  localStorage.setItem(NAV_STORAGE_KEY, next);
  if(updateHash && window.location.hash !== '#'+encodeURIComponent(next)){
    history.replaceState(null, '', window.location.pathname + window.location.search + '#'+encodeURIComponent(next));
  }
  await render(next);
  if(window.innerWidth<=768){
    const sb=$('sidebar'),ov=$('sb-overlay');
    if(sb) sb.classList.remove('sb-open');
    if(ov) ov.classList.remove('show');
  }
}

document.querySelectorAll('.nav-item').forEach(btn=>{
  btn.addEventListener('click',()=>{
    navigateTo(btn.dataset.module);
  });
});
window.addEventListener('hashchange', ()=>{
  const mod = moduleFromHash();
  if(mod) navigateTo(mod, {updateHash:false});
});
$('page-date').textContent=new Date().toLocaleDateString('pt-BR',{weekday:'long',year:'numeric',month:'long',day:'numeric'});

async function render(mod){
  $('content').innerHTML='<div class="loading">Carregando...</div>';
  try{
    if(mod==='dashboard')     await renderDashboard();
    else if(mod==='entrada')  await renderEntrada();
    else if(mod==='insumos')  await renderInsumos();
    else if(mod==='ativos')   await renderAtivos();
    else if(mod==='alocacoes')await renderAlocacoes();
    else if(mod==='qrcode')   await renderQRCode();
    else if(mod==='auditorias') await renderAuditorias();
    else if(mod==='manutencao') await renderManutencao();
    else if(mod==='licencas') await renderLicencas();
    else if(mod==='alertas')  await renderAlertas();
    else if(mod==='colaboradores') await renderColaboradores();
    else if(mod==='system_users')  await renderSystemUsers();
    else if(mod==='configuracoes')  await renderConfiguracoes();
    const content = $('content');
    if(content && content.querySelector('.loading') && !_redirectingToLogin){
      content.innerHTML='<div class="card" style="padding:20px;color:var(--text2)">Não foi possível carregar esta tela. Atualize a página e tente novamente.</div>';
    }
  }catch(e){
    if(_redirectingToLogin) return;  // ignore errors during logout redirect
    $('content').innerHTML=`<div class="card" style="color:var(--red-text);padding:20px">Atenção ${esc(e.message)}</div>`;
  }
}
