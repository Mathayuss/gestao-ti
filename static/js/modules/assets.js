// ══════════════════════════════════════════════════════════════════════════
// ATIVOS
// ══════════════════════════════════════════════════════════════════════════
function assetIconName(cat=''){
  const c = String(cat||'').toLowerCase();
  if(c.includes('smartphone') || c.includes('tablet') || c.includes('celular')) return 'smartphone';
  if(c.includes('impressora')) return 'printer';
  if(c.includes('switch') || c.includes('firewall') || c.includes('servidor') || c.includes('storage') || c.includes('rack') || c.includes('nobreak')) return 'app';
  return 'ativos';
}

function setAssetViewMode(mode){
  _assetViewMode = mode === 'table' ? 'table' : 'cards';
  localStorage.setItem('ticontrol-assets-view', _assetViewMode);
  renderAtivos(document.getElementById('asset-search')?.value || '', document.getElementById('ac')?.value || '');
}

function assetDisplayName(a){
  return [a.categoria, a.fabricante, a.modelo].filter(Boolean).join(' ') || a.hostname || a.patrimonio || a.id;
}

function assetVisualHtml(cat=''){
  const image = assetCategoryImage(cat);
  if(image){
    return `<div class="asset-card-visual has-image"><img src="${escAttr(image)}" alt="${escAttr(cat || 'Categoria do ativo')}" loading="lazy"></div>`;
  }
  return `<div class="asset-card-visual">${svgIcon(assetIconName(cat))}</div>`;
}

function renderAssetCards(data){
  if(!data.length){
    return `<div class="asset-empty">
      <div style="font-weight:800;color:var(--text);margin-bottom:4px">Nenhum ativo encontrado</div>
      <div style="font-size:13px">Ajuste os filtros ou cadastre um novo ativo.</div>
    </div>`;
  }
  return `<div class="asset-card-grid">${data.map(a=>{
    const d = daysUntil(a.garantia);
    const warrantyAlert = d >= 0 && d <= 60;
    const location = [a.unidade, a.setor].filter(Boolean).join(' - ') || 'Local não informado';
    const owner = a.colaborador || 'Sem responsável';
    const name = assetDisplayName(a);
    const code = a.patrimonio || a.id;
    const editPayload = JSON.stringify(a).replace(/"/g,'&quot;');
    const titlePayload = JSON.stringify(name).replace(/"/g,'&quot;');
    return `<article class="asset-card">
      <div class="asset-card-body">
        <div class="asset-card-top">
          ${assetVisualHtml(a.categoria)}
          <div style="min-width:0;flex:1">
            <div class="asset-card-title">${esc(name)}</div>
            <div class="asset-card-code">${esc(code)} · ${esc(a.hostname || 'sem hostname')}</div>
          </div>
        </div>
        <div class="flex-gap" style="flex-wrap:wrap">
          ${badge(a.status)}
          ${badge(a.categoria || 'Ativo de TI','blue')}
          ${warrantyAlert ? badge(`Garantia ${d}d`,'amber') : ''}
        </div>
        <div class="asset-card-meta">
          <div class="asset-card-field">
            <div class="asset-card-label">Marca / modelo</div>
            <div class="asset-card-value">${esc([a.fabricante,a.modelo].filter(Boolean).join(' ') || 'Não informado')}</div>
          </div>
          <div class="asset-card-field">
            <div class="asset-card-label">Service tag</div>
            <div class="asset-card-value mono">${esc(a.serviceTag || '—')}</div>
          </div>
          <div class="asset-card-field">
            <div class="asset-card-label">Localização</div>
            <div class="asset-card-value">${esc(location)}</div>
          </div>
          <div class="asset-card-field">
            <div class="asset-card-label">Garantia</div>
            <div class="asset-card-value" style="${warrantyAlert?'color:var(--amber);font-weight:800':''}">${fmtDate(a.garantia)}</div>
          </div>
        </div>
        <div class="asset-card-footer">
          <div class="asset-card-field">
            <div class="asset-card-label">Responsável</div>
            <div class="asset-card-value">${esc(owner)}</div>
          </div>
          <div class="asset-card-field">
            <div class="asset-card-label">IP / MAC</div>
            <div class="asset-card-value mono">${esc([a.ip || 'DHCP', a.mac].filter(Boolean).join(' · '))}</div>
          </div>
        </div>
      </div>
      <div class="asset-action-rail" aria-label="Ações do ativo">
        <button class="asset-action-btn" title="Visualizar" onclick="viewAsset('${escAttr(a.id)}')">${svgIcon('eye')}</button>
        <button class="asset-action-btn" title="Editar" onclick="editAsset(${editPayload})">${svgIcon('edit')}</button>
        <button class="asset-action-btn" title="QR Code" onclick="viewAssetQr('${escAttr(a.id)}',${titlePayload})">${svgIcon('qrcode')}</button>
        <button class="asset-action-btn" title="Histórico" onclick="viewAssetHistory('${escAttr(a.id)}')">${svgIcon('clipboard')}</button>
      </div>
    </article>`;
  }).join('')}</div>`;
}

function renderAssetTable(data){
  return `<div class="card"><div class="table-wrap"><table>
    <thead><tr><th>ID</th><th>Hostname</th><th>Categoria</th><th>Fabricante / Modelo</th><th>Service Tag</th><th>Colaborador</th><th>Status</th><th>Garantia</th><th></th></tr></thead>
    <tbody>${data.map(a=>{
      const d=daysUntil(a.garantia); const wG=d>=0&&d<=60;
      return `<tr>
        <td class="mono" style="color:var(--text3)">${esc(a.id)}</td>
        <td class="mono" style="font-weight:700">${esc(a.hostname)}</td>
        <td>${badge(a.categoria,'blue')}</td>
        <td>${esc(a.fabricante)} ${esc(a.modelo)}</td>
        <td class="mono">${esc(a.serviceTag)}</td>
        <td>${a.colaborador||'<span style="color:var(--text3)">—</span>'}</td>
        <td>${badge(a.status)}</td>
        <td style="font-size:12px;color:${wG?'var(--amber)':'inherit'}">${fmtDate(a.garantia)}${wG?` <small>(${d}d)</small>`:''}</td>
        <td><div class="flex-gap">
          <button class="btn btn-default btn-icon btn-sm" onclick="viewAsset('${a.id}')">Ver</button>
          <button class="btn btn-default btn-icon btn-sm" onclick="editAsset(${JSON.stringify(a).replace(/"/g,'&quot;')})">Editar</button>
        </div></td>
      </tr>`;}).join('')}
    </tbody>
  </table></div></div>`;
}

async function renderAtivos(q='',cat=''){
  q = q || '';
  cat = (cat === 'Todos') ? '' : (cat || '');
  const [data, allAssets] = await Promise.all([
    api(`/assets?q=${encodeURIComponent(q)}&categoria=${encodeURIComponent(cat)}`),
    api('/assets')
  ]);
  const cats=[...new Set([...getAssetCats(), ...allAssets.map(a=>a.categoria).filter(Boolean)])];
  const contentHtml = _assetViewMode === 'table' ? renderAssetTable(data) : renderAssetCards(data);
  $('content').innerHTML=`
  <div class="page-toolbar">
    <div class="page-toolbar-left">
      <div class="search-wrap"><span class="search-icon">${inlineIcon('search')}</span>
        <input id="asset-search" placeholder="Hostname, colaborador, service tag..." value="${escAttr(q)}" onkeyup="debounce(()=>renderAtivos(this.value,document.getElementById('ac').value))">
      </div>
      <select id="ac" style="width:auto" onchange="renderAtivos(document.getElementById('asset-search').value,this.value)">
        <option value="" ${!cat?'selected':''}>Todos</option>
        ${cats.map(c=>`<option value="${escAttr(c)}" ${c===cat?'selected':''}>${esc(c)}</option>`).join('')}
      </select>
      <div class="view-toggle" aria-label="Modo de visualização dos ativos">
        <button class="btn btn-sm ${_assetViewMode==='cards'?'active':''}" type="button" onclick="setAssetViewMode('cards')">${inlineIcon('ativos')} Cards</button>
        <button class="btn btn-sm ${_assetViewMode==='table'?'active':''}" type="button" onclick="setAssetViewMode('table')">${inlineIcon('clipboard')} Tabela</button>
      </div>
    </div>
    <div class="page-toolbar-right">
      <a class="btn btn-default" href="/api/export/assets.csv" download>Exportar CSV</a>
      <button class="btn btn-primary" onclick="openNewAsset()">Novo Ativo</button>
    </div>
  </div>
  ${contentHtml}`;
}

function viewAssetQr(id,title='Ativo'){
  openModal('QR Code do Ativo',`
    <div style="text-align:center">
      <div style="font-size:15px;font-weight:800;color:var(--text);margin-bottom:4px">${esc(title)}</div>
      <div class="mono" style="font-size:12px;color:var(--text3);margin-bottom:14px">${esc(id)}</div>
      <div style="display:inline-block;padding:14px;background:#fff;border:1px solid var(--border);border-radius:var(--r);box-shadow:var(--shadow-sm)">
        <img src="/api/assets/${id}/qrcode" width="180" height="180" alt="QR Code do ativo">
      </div>
      <div class="modal-footer">
        <a class="btn btn-default" href="/asset/${id}" target="_blank">Abrir perfil público</a>
        <a class="btn btn-primary" href="/api/assets/${id}/qrcode" download="qrcode-${id}.png">Baixar QR Code</a>
      </div>
    </div>
  `);
}

async function viewAsset(id){
  const a=await api(`/assets/${id}`);
  openModal('Perfil do Ativo',`
  <div style="display:flex;gap:16px;margin-bottom:18px;align-items:flex-start">
    <div style="font-size:32px;padding:12px;background:var(--blue-bg);border-radius:var(--rl)"></div>
    <div style="flex:1">
      <div class="flex-gap" style="margin-bottom:4px"><span class="mono" style="font-size:16px;font-weight:700">${esc(a.hostname)}</span>${badge(a.status)}</div>
      <div style="font-size:13px;color:var(--text2)">${esc(a.fabricante)} ${esc(a.modelo)} · ${esc(a.categoria)}</div>
    </div>
    <div style="padding:8px;background:white;border:1px solid var(--border2);border-radius:var(--r)">
      <img src="/api/assets/${id}/qrcode" width="80" height="80" alt="QR">
      <div style="text-align:center;font-family:var(--mono);font-size:10px;color:var(--text3);margin-top:3px">${id}</div>
    </div>
  </div>
  <div class="form-grid-2">
    ${[['Service Tag',a.serviceTag,true],['Patrimônio',a.patrimonio,true],['Nota Fiscal',a.nf,false],['S.O.',a.os,false],['IP',a.ip,true],['MAC',a.mac,true],['Colaborador',a.colaborador||'Não alocado',false],['Setor',a.setor||'—',false],['Unidade',a.unidade,false],['Garantia',fmtDate(a.garantia),false]].map(([k,v,m])=>`
    <div style="background:var(--bg3);border-radius:var(--r);padding:8px 10px">
      <div style="font-size:11px;color:var(--text2);margin-bottom:2px">${k}</div>
      <div style="font-size:13px;font-weight:600;${m?'font-family:var(--mono)':''}">${esc(v)||'—'}</div>
    </div>`).join('')}
  </div>
  ${a.incidentes&&a.incidentes.length?`<div style="margin-top:14px">
    <div class="section-title" style="font-size:13px">Incidentes (${a.incidentes.length})</div>
    ${a.incidentes.map(i=>`<div style="padding:8px;border-radius:var(--r);border:1px solid var(--border);margin-bottom:6px;font-size:13px">
      ${badge(i.tipo,'amber')} ${esc(i.descricao)}<span style="float:right;font-size:11px;color:var(--text3)">${new Date(i.data).toLocaleDateString('pt-BR')}</span>
    </div>`).join('')}
  </div>`:''}
  ${attachmentPanel('asset', id, 'Anexos do Ativo')}
  <div class="modal-footer">
    <button class="btn btn-default" onclick="openIncident('${id}')">Registrar Incidente</button>
    <button class="btn btn-default" onclick="viewAssetHistory('${id}')">Histórico</button>
    <button class="btn btn-primary" onclick="closeModal();editAsset(${JSON.stringify(a).replace(/"/g,'&quot;')})">Editar</button>
  </div>`,true);
  loadAttachments('asset', id);
}

function openIncident(aid){
  openModal('Registrar Incidente',`
  <div class="form-group"><label>Tipo</label>
    <select id="inc-tipo"><option>Dano</option><option>Perda</option><option>Roubo</option><option>Mau uso</option><option>Manutenção</option></select>
  </div>
  <div class="form-group"><label>Descrição</label><textarea id="inc-desc" rows="3"></textarea></div>
  <div class="modal-footer">
    <button class="btn btn-default" onclick="closeModal()">Cancelar</button>
    <button class="btn btn-danger" onclick="saveIncident('${aid}')">Registrar</button>
  </div>`);
}
async function saveIncident(refId){
  await api('/incidents','POST',{refId,tipo:$('inc-tipo').value,descricao:$('inc-desc').value});
  toast('Incidente registrado'); closeModal();
}

const ASSET_CATS_DEFAULT=['Notebook','Desktop','Monitor','Smartphone','Dock Station','Switch','Firewall','Access Point','Servidor','Storage','Rack','Nobreak','DVR','NVR','Câmera IP','Tablet','Impressora'];
function getAssetCats(){ return (_settings.categorias&&_settings.categorias.length)?_settings.categorias:ASSET_CATS_DEFAULT; }

function onCatChange(cat){
  const isUni = catIsUnidade(cat);
  $('fa-colab-wrap').style.display = isUni ? 'none' : '';
  $('fa-resp-wrap').style.display  = isUni ? '' : 'none';
  const lbl = $('fa-setor-lbl');
  if(lbl) lbl.textContent = isUni ? 'Setor / Local Físico' : 'Setor';
}

function assetFormHtml(a={}){
  const isUni = catIsUnidade(a.categoria||'');
  return `<div class="form-grid-2">
    <div class="form-group"><label>Hostname / Identificação</label><input id="fa-hn" value="${esc(a.hostname||'')}"></div>
    <div class="form-group"><label>Service Tag / Nº Série</label><input id="fa-st" value="${esc(a.serviceTag||'')}"></div>
    <div class="form-group"><label>Patrimônio</label><input id="fa-pat" value="${esc(a.patrimonio||'')}"></div>
    <div class="form-group"><label>Nota Fiscal</label><input id="fa-nf" value="${esc(a.nf||'')}"></div>
    <div class="form-group"><label>IP</label><input id="fa-ip" value="${esc(a.ip||'DHCP')}"></div>
    <div class="form-group"><label>MAC Address</label><input id="fa-mac" value="${esc(a.mac||'')}"></div>
    <div class="form-group"><label>Fabricante</label><input id="fa-fab" value="${esc(a.fabricante||'')}"></div>
    <div class="form-group"><label>Modelo</label><input id="fa-mod" value="${esc(a.modelo||'')}"></div>
    <div class="form-group"><label>Sistema Operacional</label><input id="fa-os" value="${esc(a.os||'Windows 11 Pro')}"></div>
    <div class="form-group"><label>Garantia</label><input id="fa-gar" type="date" value="${a.garantia||''}"></div>
    <div class="form-group"><label>Categoria</label>
      <select id="fa-cat" onchange="onCatChange(this.value)">
        ${getAssetCats().map(c=>`<option ${c===(a.categoria||'')?'selected':''}>${c}</option>`).join('')}
      </select>
    </div>
    <div class="form-group"><label>Status</label>
      <select id="fa-st2">${['Disponível','Alocado','Manutenção','Ativo','Baixado','Descartado','Extraviado','Inativo'].map(s=>`<option ${s===a.status?'selected':''}>${s}</option>`).join('')}</select>
    </div>

    <!-- Colaborador — visível apenas para categorias de uso pessoal -->
    <div class="form-group" id="fa-colab-wrap" style="${isUni?'display:none':''}">
      <label>Colaborador</label>
      <input id="fa-colab" value="${esc(a.colaborador||'')}" list="fa-colab-list" placeholder="Nome do colaborador">
      <datalist id="fa-colab-list">${_colab_cache.map(c=>`<option>${esc(c.nome)}</option>`).join('')}</datalist>
    </div>

    <!-- Responsável — visível para categorias de unidade (switch, firewall, etc.) -->
    <div class="form-group" id="fa-resp-wrap" style="${!isUni?'display:none':''}">
      <label>Responsável Técnico</label>
      <input id="fa-resp" value="${esc(a.colaborador||'')}" placeholder="Técnico responsável (opcional)">
    </div>

    <div class="form-group"><label id="fa-setor-lbl">${isUni?'Setor / Local Físico':'Setor'}</label>
      <select id="fa-setor"><option value="">—</option>${setorOpts(a.setor||'')}</select>
    </div>
    <div class="form-group"><label>Unidade</label>
      <select id="fa-uni"><option value="">—</option>${unidadeOpts(a.unidade||'')}</select>
    </div>
  </div>`;
}
function getAssetForm(){
  const isUni = catIsUnidade($('fa-cat').value);
  return {hostname:$('fa-hn').value,serviceTag:$('fa-st').value,patrimonio:$('fa-pat').value,nf:$('fa-nf').value,
          ip:$('fa-ip').value,mac:$('fa-mac').value,fabricante:$('fa-fab').value,modelo:$('fa-mod').value,
          os:$('fa-os').value,categoria:$('fa-cat').value,status:$('fa-st2').value,
          colaborador: isUni ? $('fa-resp').value : $('fa-colab').value,
          setor:$('fa-setor').value,unidade:$('fa-uni').value,garantia:$('fa-gar').value};
}
function openNewAsset(){
  openModal('Novo Ativo de TI',assetFormHtml()+`<div class="modal-footer"><button class="btn btn-default" onclick="closeModal()">Cancelar</button><button class="btn btn-primary" onclick="saveNewAsset()">Cadastrar</button></div>`,true);
}
function editAsset(a){
  openModal('Editar Ativo',assetFormHtml(a)+`<div class="modal-footer"><button class="btn btn-default" onclick="closeModal()">Cancelar</button><button class="btn btn-primary" onclick="saveEditAsset('${a.id}')">Salvar</button></div>`,true);
}
async function saveNewAsset(){await api('/assets','POST',getAssetForm());toast('Ativo cadastrado');closeModal();renderAtivos();}
async function saveEditAsset(id){await api(`/assets/${id}`,'PUT',getAssetForm());toast('Ativo atualizado');closeModal();renderAtivos();}

