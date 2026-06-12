function _buildCatsConfigHtml(cats, cfg_cats){
  if(!cats||!cats.length) return '<p style="font-size:13px;color:var(--text3)">Nenhuma categoria cadastrada.</p>';
  cfg_cats = cfg_cats || {};
  return `<div class="cat-config-grid">${cats.map((cat,idx)=>{
    const cfg_raw = cfg_cats[cat] && typeof cfg_cats[cat] === 'object' ? cfg_cats[cat] : {};
    const cfg_cat = {tipo_alocacao:'colaborador', ...cfg_raw};
    const image = cfg_cat.image || '';
    const inputId = `cat-img-${idx}`;
    return `<div class="cat-config-row">
      <div class="cat-config-thumb">${image ? `<img src="${escAttr(image)}" alt="${escAttr(cat)}">` : svgIcon(assetIconName(cat))}</div>
      <div class="cat-config-main">
        <div class="cat-config-name" title="${escAttr(cat)}">${esc(cat)}</div>
        <div class="cat-config-actions">
          <select data-cat="${escAttr(cat)}" onchange="saveCatConfig()">
            <option value="colaborador" ${cfg_cat.tipo_alocacao==='colaborador'?'selected':''}>Colaborador</option>
            <option value="unidade" ${cfg_cat.tipo_alocacao==='unidade'?'selected':''}>Unidade</option>
          </select>
          <label class="btn btn-default btn-sm cat-config-upload" for="${inputId}" title="Imagem da categoria">
            ${inlineIcon(image ? 'image' : 'upload')} ${image ? 'Trocar' : 'Imagem'}
            <input id="${inputId}" type="file" accept="image/png,image/jpeg,image/webp" onchange="saveCategoryImage(${jsArg(cat)},this)">
          </label>
          ${image ? `<button class="btn btn-default btn-sm btn-icon" type="button" title="Remover imagem" onclick="removeCategoryImage(${jsArg(cat)})">${svgIcon('x')}</button>` : ''}
          <button class="btn btn-default btn-sm btn-icon" type="button" title="Renomear" onclick="renameCategoria(${jsArg(cat)})">${svgIcon('edit')}</button>
          <button class="btn btn-danger btn-sm btn-icon" type="button" title="Remover categoria" onclick="delCategoria(${jsArg(cat)})">${svgIcon('trash')}</button>
        </div>
      </div>
    </div>`;
  }).join('')}</div>`;
}

function collectCatConfig(){
  const cats = {};
  Object.entries(_settings.categorias_config || {}).forEach(([cat,cfg])=>{
    const current = cfg && typeof cfg === 'object' ? cfg : {};
    cats[cat] = {
      ...current,
      tipo_alocacao: current.tipo_alocacao === 'unidade' ? 'unidade' : 'colaborador'
    };
  });
  document.querySelectorAll('select[data-cat]').forEach(s=>{
    const current = cats[s.dataset.cat] || {};
    cats[s.dataset.cat] = {
      ...current,
      tipo_alocacao: s.value === 'unidade' ? 'unidade' : 'colaborador'
    };
  });
  return cats;
}

async function saveCatConfig(){
  try{
    const cats = collectCatConfig();
    const cfg = await api('/settings','PUT',{categorias_config:cats});
    if(cfg) _settings = cfg;
    if($('cats-config-list')) $('cats-config-list').innerHTML = _buildCatsConfigHtml(getAssetCats(), _settings.categorias_config || {});
    toast('Categoria atualizada');
  }catch(e){ toast(e.message,'error'); }
}

async function saveCategoryImage(cat,input){
  const file = input?.files?.[0];
  if(!file) return;
  if(!['image/png','image/jpeg','image/webp'].includes(file.type)){
    toast('Use PNG, JPG ou WEBP para a imagem da categoria','error');
    input.value = '';
    return;
  }
  if(file.size > ASSET_CATEGORY_IMAGE_MAX_BYTES){
    toast(`Imagem muito grande — máx ${fmtBytes(ASSET_CATEGORY_IMAGE_MAX_BYTES)}`,'error');
    input.value = '';
    return;
  }
  try{
    const image = await new Promise(res=>{ const r=new FileReader(); r.onload=e=>res(e.target.result); r.readAsDataURL(file); });
    const cats = collectCatConfig();
    cats[cat] = {
      ...(cats[cat] || {}),
      tipo_alocacao: (cats[cat]?.tipo_alocacao === 'unidade') ? 'unidade' : 'colaborador',
      image
    };
    const cfg = await api('/settings','PUT',{categorias_config:cats});
    if(cfg) _settings = cfg;
    if($('cats-config-list')) $('cats-config-list').innerHTML = _buildCatsConfigHtml(getAssetCats(), _settings.categorias_config || {});
    toast('Imagem da categoria salva');
  }catch(e){
    toast(e.message,'error');
  }finally{
    input.value = '';
  }
}

async function removeCategoryImage(cat){
  try{
    const cats = collectCatConfig();
    cats[cat] = {
      ...(cats[cat] || {}),
      tipo_alocacao: (cats[cat]?.tipo_alocacao === 'unidade') ? 'unidade' : 'colaborador',
      image: ''
    };
    const cfg = await api('/settings','PUT',{categorias_config:cats});
    if(cfg) _settings = cfg;
    if($('cats-config-list')) $('cats-config-list').innerHTML = _buildCatsConfigHtml(getAssetCats(), _settings.categorias_config || {});
    toast('Imagem da categoria removida');
  }catch(e){ toast(e.message,'error'); }
}

async function addCategoria(){
  const inp = $('nova-cat');
  const nome = inp?.value?.trim();
  if(!nome){ toast('Digite o nome da categoria','error'); return; }
  const cats = await api('/settings/categorias','POST',{nome});
  if(!cats) return;
  _settings.categorias = cats;
  inp.value = '';
  const cfg_cats = _settings.categorias_config || {};
  $('cats-config-list').innerHTML = _buildCatsConfigHtml(getAssetCats(), cfg_cats);
  toast(`Categoria '${nome}' adicionada`);
}

async function delCategoria(nome){
  if(!confirm(`Remover categoria '${nome}'?\nAtivos já cadastrados com essa categoria não serão afetados.`)) return;
  const cats = await api(`/settings/categorias/${encodeURIComponent(nome)}`,'DELETE');
  if(!cats) return;
  _settings.categorias = cats;
  const cfg_cats = _settings.categorias_config || {};
  $('cats-config-list').innerHTML = _buildCatsConfigHtml(getAssetCats(), cfg_cats);
  toast(`Categoria '${nome}' removida`);
}

async function renameCategoria(nome){
  const novo = prompt(`Novo nome para '${nome}':`, nome);
  if(!novo||novo.trim()===nome) return;
  const novoNome = novo.trim();
  const prevCfg = _settings.categorias_config || {};
  const cats = await api(`/settings/categorias/${encodeURIComponent(nome)}`,'PUT',{nome:novoNome});
  if(!cats) return;
  _settings.categorias = cats;
  let cfg_cats = _settings.categorias_config || {};
  if(prevCfg[nome]){
    cfg_cats = {...prevCfg, [novoNome]: {...prevCfg[nome]}};
    const cfg = await api('/settings','PUT',{categorias_config:cfg_cats});
    if(cfg) _settings = cfg;
  }
  cfg_cats = _settings.categorias_config || cfg_cats;
  $('cats-config-list').innerHTML = _buildCatsConfigHtml(getAssetCats(), cfg_cats);
  toast(`Categoria renomeada para '${novoNome}'`);
}

// ── Categorias de Insumos / Periféricos ──────────────────────────────────────
function getSupplyCats(){ return (_settings.categorias_insumos&&_settings.categorias_insumos.length)?_settings.categorias_insumos:['Periférico','Cabo','Insumo','Componente','Toner','Papel','Bateria','Adaptador']; }

function _buildCatsInsumoHtml(cats){
  if(!cats||!cats.length) return '<p style="font-size:13px;color:var(--text3)">Nenhuma categoria cadastrada.</p>';
  return `<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px">${cats.map(cat=>`
    <div style="display:flex;align-items:center;gap:6px;padding:6px 10px;border:1px solid var(--border);border-radius:var(--r);background:var(--bg3);min-width:0">
      <span style="flex:1;font-size:13px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(cat)}">${esc(cat)}</span>
      <button class="btn btn-default btn-sm btn-icon" style="flex-shrink:0" title="Renomear" onclick="renameCategoriaInsumo('${esc(cat)}')">✎</button>
      <button class="btn btn-danger btn-sm btn-icon" style="flex-shrink:0" title="Remover" onclick="delCategoriaInsumo('${esc(cat)}')">x</button>
    </div>`).join('')}</div>`;
}

async function addCategoriaInsumo(){
  const inp = $('nova-cat-ins');
  const nome = inp?.value?.trim();
  if(!nome){ toast('Digite o nome da categoria','error'); return; }
  const cats = await api('/settings/categorias-insumos','POST',{nome});
  if(!cats) return;
  _settings.categorias_insumos = cats;
  inp.value = '';
  $('cats-insumos-list').innerHTML = _buildCatsInsumoHtml(getSupplyCats());
  toast(`Categoria '${nome}' adicionada`);
}

async function delCategoriaInsumo(nome){
  if(!confirm(`Remover categoria '${nome}'?\nItens já cadastrados com essa categoria não serão afetados.`)) return;
  const cats = await api(`/settings/categorias-insumos/${encodeURIComponent(nome)}`,'DELETE');
  if(!cats) return;
  _settings.categorias_insumos = cats;
  $('cats-insumos-list').innerHTML = _buildCatsInsumoHtml(getSupplyCats());
  toast(`Categoria '${nome}' removida`);
}

async function renameCategoriaInsumo(nome){
  const novo = prompt(`Novo nome para '${nome}':`, nome);
  if(!novo||novo.trim()===nome) return;
  const cats = await api(`/settings/categorias-insumos/${encodeURIComponent(nome)}`,'PUT',{nome:novo.trim()});
  if(!cats) return;
  _settings.categorias_insumos = cats;
  $('cats-insumos-list').innerHTML = _buildCatsInsumoHtml(getSupplyCats());
  toast(`Categoria renomeada para '${novo.trim()}'`);
}

// ── Matriz de Compatibilidade Ativo × Insumo ─────────────────────────────────
function _buildCompatMatrix(ativosCats, insumosCats, compat){
  if(!ativosCats.length||!insumosCats.length)
    return '<p style="font-size:13px;color:var(--text3)">Cadastre categorias de ativos e insumos primeiro.</p>';

  const rows = ativosCats.map(ac=>{
    const allowed = compat[ac] || [];
    const unconfigured = !Object.hasOwn(compat, ac);
    const selectedCount = unconfigured ? 0 : allowed.length;
    const stateLabel = selectedCount ? `${selectedCount}/${insumosCats.length}` : 'Livre';
    const chips = insumosCats.map(ic=>{
      const checked = !unconfigured && allowed.includes(ic);
      return `<label class="compat-chip ${checked?'is-checked':''}" title="${escAttr(ac)} permite ${escAttr(ic)}">
        <input type="checkbox" data-ativo="${escAttr(ac)}" data-insumo="${escAttr(ic)}" ${checked?'checked':''} onchange="this.closest('.compat-chip').classList.toggle('is-checked',this.checked);updateCompatMatrixState()">
        ${svgIcon('check')}<span>${esc(ic)}</span>
      </label>`;
    }).join('');
    return `<div class="compat-row compat-item ${selectedCount?'':'is-unrestricted'}">
      <div class="compat-item-main">
        <div class="compat-row-title">
          <span class="compat-row-name" title="${escAttr(ac)}">${esc(ac)}</span>
          <span class="compat-row-state ${selectedCount?'active':''}">${stateLabel}</span>
        </div>
      </div>
      <div class="compat-chip-list">${chips}</div>
    </div>`;
  }).join('');

  return `<div class="compat-list-wrap"><div class="compat-list">${rows}</div></div>
  <div class="compat-help">
    ${inlineIcon('warning')} Linha sem nenhum item marcado = todos os insumos em estoque serão exibidos.
  </div>`;
}

function updateCompatMatrixState(){
  document.querySelectorAll('#compat-matrix .compat-row').forEach(row=>{
    const checks = [...row.querySelectorAll('input[type=checkbox]')];
    const selected = checks.filter(cb=>cb.checked).length;
    row.classList.toggle('is-unrestricted', selected === 0);
    const state = row.querySelector('.compat-row-state');
    if(state){
      state.textContent = selected ? `${selected}/${checks.length}` : 'Livre';
      state.classList.toggle('active', selected > 0);
    }
  });
}

async function saveCompatConfig(){
  const checks = document.querySelectorAll('#compat-matrix input[type=checkbox]');
  const compat = {};
  checks.forEach(cb=>{
    const ac = cb.dataset.ativo;
    const ic = cb.dataset.insumo;
    if(!compat[ac]) compat[ac] = [];
    if(cb.checked) compat[ac].push(ic);
  });
  await api('/settings','PUT',{categorias_compat: compat});
  _settings.categorias_compat = compat;
  toast('Compatibilidade salva');
}

// ── Filtro dinâmico na modal de alocação ─────────────────────────────────────
function _renderPerifList(items){
  const list = $('perf-list');
  if(!list) return;
  if(!items||!items.length){
    list.innerHTML='<p style="font-size:12px;color:var(--text3);text-align:center;padding:20px">Nenhum insumo compatível disponível em estoque.</p>';
    return;
  }
  list.innerHTML = items.map(s=>`
    <div class="perm-item" id="perf-row-${s.id}" style="cursor:pointer;justify-content:space-between" onclick="togglePerif('${s.id}','${esc(s.nome)}',${s.estoque})">
      <div class="flex-gap">
        <span id="perf-chk-${s.id}" style="font-size:14px">-</span>
        <div><div style="font-size:12px;font-weight:600">${esc(s.nome)}</div>
          <div style="font-size:11px;color:var(--text3)">${esc(s.categoria)} · ${s.estoque} em estoque</div>
        </div>
      </div>
      <div class="flex-gap" id="perf-qty-wrap-${s.id}" style="display:none" onclick="event.stopPropagation()">
        <button class="btn btn-default btn-icon btn-sm" onclick="changeQty('${s.id}',-1)">−</button>
        <span id="perf-qty-${s.id}" style="font-weight:700;min-width:20px;text-align:center">1</span>
        <button class="btn btn-default btn-icon btn-sm" onclick="changeQty('${s.id}',1,${s.estoque})">+</button>
      </div>
    </div>`).join('');
  // restaura seleção prévia
  _allocPerifs.forEach(p=>{
    const chk = $('perf-chk-'+p.supplyId);
    const wrap = $('perf-qty-wrap-'+p.supplyId);
    const row  = $('perf-row-'+p.supplyId);
    const qty  = $('perf-qty-'+p.supplyId);
    if(chk) chk.textContent='✓';
    if(wrap) wrap.style.display='flex';
    if(row)  row.classList.add('on');
    if(qty)  qty.textContent = p.quantidade;
  });
}

function onAllocAtivoChange(sel){
  _allocPerifs = [];
  const cats = (typeof _allocAssets !== 'undefined' && Array.isArray(_allocAssets) && _allocAssets.length)
    ? _allocAssets.map(a => a.categoria).filter(Boolean)
    : [sel?.options?.[sel.selectedIndex]?.dataset?.cat || ''].filter(Boolean);
  if(!cats.length){
    $('perf-list').innerHTML='<p style="font-size:12px;color:var(--text3);text-align:center;padding:20px">Adicione ao menos um ativo para ver os insumos compatíveis.</p>';
    _updatePerifCount();
    return;
  }
  const compat = _settings.categorias_compat || {};
  let allowed = null;
  cats.forEach(cat => {
    if(Object.hasOwn(compat, cat) && compat[cat].length > 0){
      const set = new Set(compat[cat]);
      allowed = allowed === null ? set : new Set([...allowed].filter(x => set.has(x)));
    }
  });
  let filtered;
  if(allowed && allowed.size > 0){
    filtered = _allAllocSupplies.filter(s => allowed.has(s.categoria));
  } else if(allowed && allowed.size === 0) {
    filtered = [];
  } else {
    // sem restrição configurada → exibe todos com estoque
    filtered = _allAllocSupplies;
  }
  _renderPerifList(filtered);
  _updatePerifCount();
}

function _updatePerifCount(){
  const badge = $('al-perf-count');
  if(!badge) return;
  const n = _allocPerifs.reduce((t,p)=>t+p.quantidade, 0);
  badge.textContent = n;
  badge.style.display = n > 0 ? 'inline-flex' : 'none';
}
