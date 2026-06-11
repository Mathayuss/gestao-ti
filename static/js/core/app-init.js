// ══════════════════════════════════════════════════════════════════════════
// ALERT BADGE
// ══════════════════════════════════════════════════════════════════════════
const state={alertCount:0};
async function updateAlertBadge(){
  try{
    const alerts=await api('/alerts');
    state.alertCount=alerts.length;
    // Badge da sidebar
    const b=$('alert-badge');
    b.style.display=alerts.length>0?'':'none';
    if(alerts.length>0) b.textContent=alerts.length;
    // Bell do header
    const bellCount=$('hdr-bell-count');
    const bellPulse=$('hdr-bell-pulse');
    if(alerts.length>0){
      bellCount.style.display='flex';
      bellCount.textContent=alerts.length>99?'99+':alerts.length;
      bellPulse.classList.add('active');
    } else {
      bellCount.style.display='none';
      bellPulse.classList.remove('active');
    }
  }catch(e){}
}

function toggleHdrUser(e){
  e.stopPropagation();
  $('hdr-user').classList.toggle('open');
}
document.addEventListener('click',()=>{ const u=$('hdr-user'); if(u) u.classList.remove('open'); });

// ══════════════════════════════════════════════════════════════════════════
// INIT
// ══════════════════════════════════════════════════════════════════════════
(async()=>{
  // Verifica sessão primeiro — se /api/me retornar 401, o redirect acontece aqui e o resto para
  let me = null;
  try { me = await api('/me'); } catch(e){}
  if (!me || _redirectingToLogin) return;

  // Preenche dados do usuário logado (sidebar e header)
  const initials = (me.nome||'?').split(' ').map(p=>p[0]).slice(0,2).join('').toUpperCase();
  const avatarEl = document.getElementById('sb-avatar');
  const nomeEl   = document.getElementById('sb-nome');
  const perfilEl = document.getElementById('sb-perfil');
  if(avatarEl)  avatarEl.textContent  = initials;
  if(nomeEl)    nomeEl.textContent    = me.nome;
  if(perfilEl)  perfilEl.textContent  = me.perfil;
  const hdrAvatar = document.getElementById('hdr-avatar');
  const hdrUname  = document.getElementById('hdr-uname');
  const hdrUrole  = document.getElementById('hdr-urole');
  const hdrDdName = document.getElementById('hdr-dd-fullname');
  const hdrDdRole = document.getElementById('hdr-dd-role');
  if(hdrAvatar)  hdrAvatar.textContent  = initials;
  if(hdrUname)   hdrUname.textContent   = me.nome;
  if(hdrUrole)   hdrUrole.textContent   = me.perfil;
  if(hdrDdName)  hdrDdName.textContent  = me.nome;
  if(hdrDdRole)  hdrDdRole.textContent  = me.perfil;
  applyProfileNavigation(me);

  // Carrega settings e colaboradores em paralelo
  try {
    const [cfg, col] = await Promise.all([api('/settings'), api('/colaboradores')]);
    if (cfg) {
      _settings = cfg;
      if (!_settings.categorias_config) _settings.categorias_config = {};
      if (!_settings.categorias) _settings.categorias = [];
      if (!_settings.categorias_insumos) _settings.categorias_insumos = [];
      if (!_settings.categorias_compat) _settings.categorias_compat = {};
      // Sincroniza APP_BASE_URL com o valor detectado pelo servidor
      if (cfg.app_base_url) APP_BASE_URL = cfg.app_base_url;
      _applyAparencia(cfg.aparencia || {}, cfg.empresa || {});
    }
    if (col) _colab_cache = col;
  } catch(e){}
  if (_redirectingToLogin) return;

  await navigateTo(moduleFromHash() || moduleFromStorage() || 'dashboard');
  updateAlertBadge();
  setInterval(updateAlertBadge, 30000);
})();
