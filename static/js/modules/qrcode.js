// ══════════════════════════════════════════════════════════════════════════
// ══════════════════════════════════════════════════════════════════════════
// QR CODE & ETIQUETAS
// ══════════════════════════════════════════════════════════════════════════
let _qrSel=null;
let _allocTab='pend';
let _cfgTab='geral';
let _qrBatchSel=new Set();
const LABEL_CFG_KEY = 'ticontrol-label-config-v2';
const LABEL_CUSTOM_TEMPLATES_KEY = 'ticontrol-label-templates-v1';
const LABEL_SIZES = {
  pequena:{label:'Pequena',dim:'58 x 38 mm',w:58,h:38,qr:18,fs:9},
  media:{label:'Media',dim:'88 x 38 mm',w:88,h:38,qr:22,fs:10},
  grande:{label:'Grande',dim:'100 x 70 mm',w:100,h:70,qr:30,fs:12}
};
const LABEL_DEFAULT_CFG = {
  size:'media',
  campos:{hostname:true,patrimonio:true,serviceTag:true,setor:true,colaborador:false,ip:false,garantia:false},
  copias:1,
  empresa:'',
  qr:'normal',
  borda:'preta',
  mostrarSistema:true,
  logoEmpresa:false,
  logoNoQr:false,
  papel:'a4',
  margem:6,
  gap:3,
};
const LABEL_PRESETS = {
  patrimonial:{
    name:'Patrimonial padrão',
    config:{size:'media',campos:{hostname:true,patrimonio:true,serviceTag:true,setor:true,colaborador:false,ip:false,garantia:false},copias:1,qr:'normal',borda:'preta',mostrarSistema:true,papel:'a4',margem:6,gap:3}
  },
  inventario:{
    name:'Inventário rápido',
    config:{size:'pequena',campos:{hostname:true,patrimonio:true,serviceTag:false,setor:true,colaborador:false,ip:false,garantia:false},copias:1,qr:'compacto',borda:'azul',mostrarSistema:true,papel:'a4',margem:6,gap:3}
  },
  minimo:{
    name:'Mínima com QR',
    config:{size:'pequena',campos:{hostname:false,patrimonio:true,serviceTag:false,setor:false,colaborador:false,ip:false,garantia:false},copias:1,qr:'grande',borda:'preta',mostrarSistema:false,papel:'unitaria',margem:0,gap:0}
  }
};
let _lblCfg=loadLabelConfig();

function loadLabelConfig(){
  try{
    const saved=JSON.parse(localStorage.getItem(LABEL_CFG_KEY)||'{}');
    return {...LABEL_DEFAULT_CFG,...saved,campos:{...LABEL_DEFAULT_CFG.campos,...(saved.campos||{})}};
  }catch(e){
    return {...LABEL_DEFAULT_CFG,campos:{...LABEL_DEFAULT_CFG.campos}};
  }
}

function saveLabelConfig(){
  try{localStorage.setItem(LABEL_CFG_KEY,JSON.stringify(_lblCfg));}catch(e){}
}

function labelSizeDef(size){
  return LABEL_SIZES[size]||LABEL_SIZES.media;
}

function labelConfigSnapshot(){
  return JSON.parse(JSON.stringify(_lblCfg));
}

function mergeLabelConfig(config){
  return {...LABEL_DEFAULT_CFG,...config,campos:{...LABEL_DEFAULT_CFG.campos,...(config.campos||{})}};
}

function loadCustomLabelTemplates(){
  try{
    const data=JSON.parse(localStorage.getItem(LABEL_CUSTOM_TEMPLATES_KEY)||'[]');
    return Array.isArray(data) ? data.filter(t=>t&&t.id&&t.name&&t.config) : [];
  }catch(e){
    return [];
  }
}

function saveCustomLabelTemplates(items){
  try{localStorage.setItem(LABEL_CUSTOM_TEMPLATES_KEY,JSON.stringify(items));}catch(e){}
}

function labelTemplateOptions(){
  const custom=loadCustomLabelTemplates();
  return `
    <optgroup label="Modelos padrão">
      ${Object.entries(LABEL_PRESETS).map(([id,p])=>`<option value="preset:${id}">${esc(p.name)}</option>`).join('')}
    </optgroup>
    ${custom.length?`<optgroup label="Meus modelos">${custom.map(t=>`<option value="custom:${escAttr(t.id)}">${esc(t.name)}</option>`).join('')}</optgroup>`:''}`;
}

async function renderQRCode(q=''){
  const assets=await api('/assets?q='+encodeURIComponent(q));
  if(!_qrSel&&assets.length) _qrSel=assets[0].id;
  const sel=assets.find(a=>a.id===_qrSel)||assets[0];
  const visibleIds=assets.map(a=>a.id);
  const selectedCount=_qrBatchSel.size;
  $('content').innerHTML=`
  <div style="display:grid;grid-template-columns:240px 1fr;gap:16px">
    <div class="card" style="padding:14px">
      <div style="font-size:12px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.04em;margin-bottom:10px">Selecionar Ativo</div>
      <div class="search-wrap" style="margin-bottom:10px"><span class="search-icon">${inlineIcon('search')}</span>
        <input style="width:100%" value="${esc(q)}" placeholder="Buscar ativo..." onkeyup="debounce(()=>renderQRCode(this.value))">
      </div>
      <div style="display:flex;align-items:center;justify-content:space-between;gap:6px;margin-bottom:8px">
        <div id="qr-batch-count" style="font-size:11px;color:var(--text3);font-weight:700">${selectedCount} selecionado(s)</div>
        <div style="display:flex;gap:4px">
          <button class="btn btn-default btn-sm" style="padding:4px 7px;font-size:10px" onclick="qrBatchSelectVisible(${escAttr(JSON.stringify(visibleIds))})">Marcar</button>
          <button class="btn btn-default btn-sm" style="padding:4px 7px;font-size:10px" onclick="qrBatchClear()">Limpar</button>
        </div>
      </div>
      <div style="display:flex;flex-direction:column;gap:2px;max-height:440px;overflow-y:auto">
        ${assets.map(a=>`<div onclick="qrSel('${escAttr(a.id)}')" style="display:flex;align-items:center;gap:8px;padding:8px 10px;border-radius:var(--r);cursor:pointer;font-family:var(--mono);font-size:12px;transition:background .1s;${a.id===_qrSel?'background:var(--blue);color:#fff;font-weight:700':'color:var(--text)'}">
          <input class="qr-batch-check" type="checkbox" ${_qrBatchSel.has(a.id)?'checked':''} onclick="qrBatchToggle(event,'${escAttr(a.id)}',this.checked)" style="width:auto;flex-shrink:0">
          <span style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(a.hostname)}</span>
        </div>`).join('')}
      </div>
    </div>
    <div>
      <!-- Abas -->
      <div style="display:flex;gap:0;margin-bottom:16px;border-bottom:2px solid var(--border)">
        <button id="tab-qr" onclick="qrTab('qr')" style="padding:8px 18px;font-size:13px;font-weight:600;border:none;background:none;cursor:pointer;color:var(--blue);border-bottom:2px solid var(--blue);margin-bottom:-2px">QR Code</button>
        <button id="tab-etq" onclick="qrTab('etq')" style="padding:8px 18px;font-size:13px;font-weight:600;border:none;background:none;cursor:pointer;color:var(--text2);border-bottom:2px solid transparent;margin-bottom:-2px">Etiquetas</button>
      </div>
      <!-- QR Code -->
      <div id="panel-qr">
        ${sel?`<div class="card">
          <div style="display:flex;gap:28px;align-items:flex-start">
            <div style="text-align:center;flex-shrink:0">
              <div style="padding:16px;background:white;border:1px solid var(--border);border-radius:var(--rl);display:inline-block;margin-bottom:10px;box-shadow:var(--shadow-sm)">
                <img src="/api/assets/${sel.id}/qrcode" width="164" height="164" alt="QR">
              </div>
              <div class="mono" style="font-size:11px;color:var(--text3);margin-bottom:4px">${sel.id}</div>
              <div style="font-weight:700;font-size:13px;margin-bottom:14px">${esc(sel.hostname)}</div>
              <div style="display:flex;flex-direction:column;gap:6px">
                <a href="/api/assets/${sel.id}/qrcode" class="btn btn-primary btn-sm" download>Baixar QR</a>
                <a href="/asset/${sel.id}" class="btn btn-default btn-sm" target="_blank">Ver Perfil</a>
              </div>
            </div>
            <div style="flex:1">
              <div style="font-size:15px;font-weight:700;margin-bottom:14px">Dados do Perfil Público</div>
              <div class="form-grid-2" style="gap:8px">
                ${[['Status',badge(sel.status)],['Categoria',sel.categoria],['Fabricante',sel.fabricante],['Modelo',sel.modelo],['S.O.',sel.os||'—'],['IP',sel.ip||'—'],['Colaborador',sel.colaborador||'Não alocado'],['Setor',sel.setor||'—'],['Unidade',sel.unidade||'—'],['Garantia',fmtDate(sel.garantia)]].map(([k,v])=>`
                <div style="background:var(--bg3);border-radius:var(--r);padding:9px 12px;border:1px solid var(--border)">
                  <div style="font-size:10px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:.04em;margin-bottom:3px">${k}</div>
                  <div style="font-size:13px;font-weight:600">${v||'—'}</div>
                </div>`).join('')}
              </div>
              <div style="margin-top:12px;padding:10px 14px;background:var(--bg3);border-radius:var(--r);border:1px solid var(--border)">
                <div style="font-size:10px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:.04em;margin-bottom:3px">URL do QR</div>
                <div class="mono" style="font-size:12px;color:var(--blue)">${APP_BASE_URL}/asset/${sel.id}</div>
              </div>
            </div>
          </div>
        </div>`:''}
      </div>
      <!-- Etiquetas -->
      <div id="panel-etq" style="display:none">
        ${sel?renderEtiquetaPanel(sel):'<div class="card"><p style="color:var(--text3)">Selecione um ativo.</p></div>'}
      </div>
    </div>
  </div>`;
}

function qrTab(tab){
  $('panel-qr').style.display  = tab==='qr'  ? '' : 'none';
  $('panel-etq').style.display = tab==='etq' ? '' : 'none';
  $('tab-qr').style.color  = tab==='qr'  ? 'var(--blue)' : 'var(--text2)';
  $('tab-etq').style.color = tab==='etq' ? 'var(--blue)' : 'var(--text2)';
  $('tab-qr').style.borderBottomColor  = tab==='qr'  ? 'var(--blue)' : 'transparent';
  $('tab-etq').style.borderBottomColor = tab==='etq' ? 'var(--blue)' : 'transparent';
}

function renderEtiquetaPanel(sel){
  const sizes=Object.entries(LABEL_SIZES).map(([id,s])=>({id,...s}));
  const bordas=[['preta','Preta'],['azul','Azul'],['cinza','Cinza'],['sem','Sem borda']];
  const campos=[['hostname','Nome / Hostname'],['patrimonio','Patrimônio'],['serviceTag','Service Tag'],
                ['setor','Setor'],['colaborador','Colaborador'],['ip','IP'],['garantia','Garantia']];
  return `<div class="card">
    <div style="font-size:15px;font-weight:700;margin-bottom:18px">Configurar Etiqueta</div>
    <div style="display:grid;grid-template-columns:260px 1fr;gap:20px">
      <div>
        <div style="font-size:12px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.04em;margin-bottom:10px">Modelos</div>
        <div style="display:flex;gap:6px;margin-bottom:8px">
          <select id="lbl-template" style="flex:1;min-width:0">
            <option value="">Selecionar modelo</option>
            ${labelTemplateOptions()}
          </select>
          <button class="btn btn-default btn-sm" type="button" onclick="applyLabelTemplate('${sel.id}')">Aplicar</button>
        </div>
        <div style="display:flex;gap:6px;margin-bottom:18px">
          <button class="btn btn-default btn-sm" type="button" onclick="saveCurrentLabelTemplate('${sel.id}')">Salvar modelo</button>
          <button class="btn btn-default btn-sm" type="button" onclick="deleteCurrentLabelTemplate('${sel.id}')">Excluir</button>
        </div>
        <div style="font-size:12px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.04em;margin-bottom:10px">Tamanho</div>
        <div style="display:flex;flex-direction:column;gap:6px;margin-bottom:18px">
          ${sizes.map(s=>`<label style="display:flex;align-items:center;gap:10px;padding:9px 12px;border:1px solid ${_lblCfg.size===s.id?'var(--blue)':'var(--border)'};border-radius:var(--r);cursor:pointer;background:${_lblCfg.size===s.id?'var(--blue-bg)':'var(--bg3)'};transition:all .15s" onclick="lblSetSize('${s.id}')">
            <input type="radio" name="lbl-size" value="${s.id}" ${_lblCfg.size===s.id?'checked':''} style="width:auto">
            <div>
              <div style="font-size:13px;font-weight:600;color:${_lblCfg.size===s.id?'var(--blue-text)':'var(--text)'}">${s.label}</div>
              <div style="font-size:11px;color:var(--text3)">${s.dim}</div>
            </div>
          </label>`).join('')}
        </div>
        <div style="font-size:12px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.04em;margin-bottom:10px">Campos</div>
        <div style="display:flex;flex-direction:column;gap:5px;margin-bottom:16px">
          ${campos.map(([k,lbl])=>`<label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer;padding:5px 0">
            <input type="checkbox" id="lbl-c-${k}" ${_lblCfg.campos[k]?'checked':''} onchange="lblToggle('${k}',this.checked)" style="width:auto">
            ${lbl}
          </label>`).join('')}
        </div>
        <div style="font-size:12px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.04em;margin-bottom:10px">Aparência</div>
        <div class="form-grid-2" style="gap:8px;margin-bottom:14px">
          <div class="form-group" style="margin-bottom:0">
            <label>QR Code</label>
            <select id="lbl-qr" onchange="lblSetOption('qr',this.value,'${sel.id}')">
              <option value="normal" ${_lblCfg.qr==='normal'?'selected':''}>Normal</option>
              <option value="grande" ${_lblCfg.qr==='grande'?'selected':''}>Maior</option>
              <option value="compacto" ${_lblCfg.qr==='compacto'?'selected':''}>Compacto</option>
            </select>
          </div>
          <div class="form-group" style="margin-bottom:0">
            <label>Borda</label>
            <select id="lbl-borda" onchange="lblSetOption('borda',this.value,'${sel.id}')">
              ${bordas.map(([v,l])=>`<option value="${v}" ${_lblCfg.borda===v?'selected':''}>${l}</option>`).join('')}
            </select>
          </div>
        </div>
        <label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer;padding:0 0 14px">
          <input type="checkbox" ${_lblCfg.mostrarSistema?'checked':''} onchange="lblSetOption('mostrarSistema',this.checked,'${sel.id}')" style="width:auto">
          Exibir identificação TI Control
        </label>
        <div style="font-size:12px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px">Nome da empresa (opcional)</div>
        <input id="lbl-empresa" value="${esc(_lblCfg.empresa)}" placeholder="Ex: ACME Corp" oninput="lblSetOption('empresa',this.value,'${sel.id}')" style="margin-bottom:16px">

        <div style="font-size:12px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px">Logo da Empresa</div>
        ${(_settings?.empresa?.logo_base64) ? `
        <div style="margin-bottom:6px;padding:6px 8px;background:var(--bg3);border:1px solid var(--border);border-radius:var(--r);display:inline-flex;align-items:center;gap:8px">
          <img src="${_settings.empresa.logo_base64}" style="height:18px;object-fit:contain;max-width:80px">
          <span style="font-size:10px;color:var(--text3)">logo cadastrado</span>
        </div>
        <div style="display:flex;flex-direction:column;gap:6px;margin-top:8px;margin-bottom:14px">
          <label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer">
            <input type="checkbox" ${_lblCfg.logoEmpresa?'checked':''} onchange="lblSetOption('logoEmpresa',this.checked,'${sel.id}')" style="width:auto">
            Exibir logo na etiqueta
          </label>
          <label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer">
            <input type="checkbox" ${_lblCfg.logoNoQr?'checked':''} onchange="lblSetOption('logoNoQr',this.checked,'${sel.id}')" style="width:auto">
            Logo no centro do QR Code
          </label>
        </div>` : `
        <div style="font-size:11px;color:var(--text3);margin-bottom:14px;padding:8px 10px;background:var(--bg3);border:1px solid var(--border);border-radius:var(--r);line-height:1.6">
          Nenhum logo cadastrado.<br>
          Configure em <b>Configurações → Geral → Dados da Empresa</b>.
        </div>`}

        <div style="font-size:12px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.04em;margin-bottom:10px">Impressão</div>
        <div class="form-grid-2" style="gap:8px;margin-bottom:14px">
          <div class="form-group" style="margin-bottom:0">
            <label>Papel</label>
            <select id="lbl-papel" onchange="lblSetOption('papel',this.value,'${sel.id}')">
              <option value="a4" ${_lblCfg.papel==='a4'?'selected':''}>A4 / folha</option>
              <option value="unitaria" ${_lblCfg.papel==='unitaria'?'selected':''}>Etiqueta individual</option>
            </select>
          </div>
          <div class="form-group" style="margin-bottom:0">
            <label>Margem A4 (mm)</label>
            <input id="lbl-margem" type="number" min="0" max="20" value="${_lblCfg.margem}" oninput="lblSetNumber('margem',this.value,'${sel.id}')" ${_lblCfg.papel==='unitaria'?'disabled':''}>
          </div>
          <div class="form-group" style="margin-bottom:0">
            <label>Espaço (mm)</label>
            <input id="lbl-gap" type="number" min="0" max="10" value="${_lblCfg.gap}" oninput="lblSetNumber('gap',this.value,'${sel.id}')">
          </div>
        </div>
        <div class="info-box blue" style="font-size:11px;line-height:1.55;margin-bottom:14px">
          Para melhor precisão, imprima em escala 100% e desative ajuste automático da página.
        </div>

        <div style="font-size:12px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px">Cópias por ativo</div>
        <input id="lbl-copias" type="number" min="1" max="20" value="${_lblCfg.copias}" oninput="lblSetNumber('copias',this.value,'${sel.id}',1,20)" style="width:80px;margin-bottom:18px">
        <div style="display:flex;gap:8px">
          <button class="btn btn-primary" onclick="imprimirEtiqueta('${sel.id}')">Imprimir etiqueta</button>
          <button id="btn-print-batch" class="btn btn-default" onclick="imprimirEtiquetasSelecionadas()" ${_qrBatchSel.size?'':'disabled'}>Imprimir selecionados (${_qrBatchSel.size})</button>
          <button class="btn btn-default" onclick="baixarEtiquetasPdf('${sel.id}')">Baixar PDF</button>
        </div>
      </div>
      <div>
        <div style="font-size:12px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.04em;margin-bottom:12px">Pré-visualização</div>
        <div id="lbl-preview" style="background:var(--bg3);border-radius:var(--rl);padding:20px;min-height:120px;display:flex;flex-wrap:wrap;gap:10px;align-items:flex-start;border:1px solid var(--border)">
          ${buildLabelHtml(sel,'preview')}
        </div>
      </div>
    </div>
  </div>`;
}

function buildLabelHtml(asset,mode){
  const sz=labelSizeDef(_lblCfg.size);
  const qrDelta = _lblCfg.qr==='grande' ? 5 : (_lblCfg.qr==='compacto' ? -5 : 0);
  const qrSize  = Math.max(14, sz.qr + qrDelta);
  const borderMap = {preta:'1.5px solid #111827',azul:'1.5px solid #2563eb',cinza:'1.5px solid #94a3b8',sem:'1px solid transparent'};
  const cls    = mode==='print' ? 'label-print-item' : 'label-card';
  const campos = _lblCfg.campos;
  const logo   = _settings?.empresa?.logo_base64 || '';

  // topo da etiqueta: logo ao lado do nome da empresa
  const _hasLogo = logo && _lblCfg.logoEmpresa;
  const _hasNome = !!_lblCfg.empresa;
  const topoHtml = (_hasLogo || _hasNome) ? `<div style="display:flex;align-items:center;gap:4px;margin-bottom:2px;overflow:hidden;max-width:100%">${
    _hasLogo ? `<img src="${logo}" style="height:4mm;flex-shrink:0;object-fit:contain;object-position:left;max-width:22mm">` : ''
  }${
    _hasNome ? `<div class="lbl-empresa" style="overflow:hidden;white-space:nowrap;text-overflow:ellipsis">${esc(_lblCfg.empresa)}</div>` : ''
  }</div>` : '';

  // campos de texto
  const lines=[];
  if(campos.patrimonio&&asset.patrimonio)   lines.push(`<div class="lbl-field">Pat: <b>${esc(asset.patrimonio)}</b></div>`);
  if(campos.serviceTag&&asset.serviceTag)   lines.push(`<div class="lbl-field">ST: <b>${esc(asset.serviceTag)}</b></div>`);
  if(campos.setor&&asset.setor)             lines.push(`<div class="lbl-field">Setor: ${esc(asset.setor)}</div>`);
  if(campos.colaborador&&asset.colaborador) lines.push(`<div class="lbl-field">Usuário: ${esc(asset.colaborador)}</div>`);
  if(campos.ip&&asset.ip)                   lines.push(`<div class="lbl-field">IP: <span style="font-family:monospace">${esc(asset.ip)}</span></div>`);
  if(campos.garantia&&asset.garantia)       lines.push(`<div class="lbl-field">Gar: ${fmtDate(asset.garantia)}</div>`);

  // QR com overlay de logo opcional
  const overlaySize = Math.round(qrSize * 0.26 * 10) / 10;
  const qrHtml = `<div style="position:relative;display:inline-block;flex-shrink:0">
    <img src="/api/assets/${asset.id}/qrcode" style="display:block;width:${qrSize}mm;height:${qrSize}mm">
    ${(logo && _lblCfg.logoNoQr) ? `<img src="${logo}" style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:${overlaySize}mm;height:${overlaySize}mm;object-fit:contain;background:#fff;padding:.4mm;border-radius:1mm">` : ''}
  </div>`;

  // auto-shrink hostname: calcula font-size para caber em uma linha
  const hn = asset.hostname || asset.id;
  const textAreaW = sz.w - 8 - qrSize - 3; // padding + qr + gap em mm
  const autoFs = Math.max(6.5, Math.min(sz.fs, Math.floor(textAreaW / Math.max(1, hn.length * 0.32))));

  const inner=`
    <div class="${cls}" style="width:${sz.w}mm;height:${sz.h}mm;padding:2.3mm 2.6mm;display:flex;flex-direction:column;justify-content:space-between;border:${borderMap[_lblCfg.borda]||borderMap.preta}">
      <div style="overflow:hidden">
        ${topoHtml}
        <div style="display:flex;gap:2mm;align-items:flex-start">
          <div style="flex:1;overflow:hidden">
            ${campos.hostname?`<div class="lbl-hostname" style="font-size:${autoFs}pt">${esc(hn)}</div>`:''}
            ${lines.join('')}
          </div>
          ${qrHtml}
        </div>
      </div>
      ${_lblCfg.mostrarSistema?'<div class="lbl-tag">TI Control</div>':''}
    </div>`;
  if(mode==='print'){
    let out='';
    for(let i=0;i<(_lblCfg.copias||1);i++) out+=inner;
    return out;
  }
  return inner;
}

function lblSetSize(size){
  _lblCfg.size=size;
  saveLabelConfig();
  // Re-render the etiqueta panel for the current asset
  renderQRCode().then(()=>{qrTab('etq');});
}

function applyLabelTemplate(aid){
  const value=$('lbl-template')?.value || '';
  if(!value){
    toast('Selecione um modelo de etiqueta.','warn');
    return;
  }
  const config=selectedLabelTemplateConfig(value);
  if(!config){
    toast('Modelo de etiqueta não encontrado.','error');
    return;
  }
  _lblCfg=labelExportConfig(config);
  saveLabelConfig();
  toast('Modelo aplicado');
  renderQRCode().then(()=>{qrTab('etq');atualizarPreviewEtiqueta(aid);});
}

function selectedLabelTemplateConfig(value){
  const selected=value || $('lbl-template')?.value || '';
  const [kind,id]=selected.split(':');
  if(kind==='preset') return LABEL_PRESETS[id]?.config || null;
  if(kind==='custom') return loadCustomLabelTemplates().find(t=>t.id===id)?.config || null;
  return null;
}

function labelExportConfig(templateConfig=null){
  return mergeLabelConfig({
    ...labelConfigSnapshot(),
    ...(templateConfig||{}),
    empresa:_lblCfg.empresa,
    logoEmpresa:_lblCfg.logoEmpresa,
    logoNoQr:_lblCfg.logoNoQr
  });
}

function saveCurrentLabelTemplate(aid){
  const name=prompt('Nome do modelo de etiqueta');
  if(!name || !name.trim()) return;
  const cleanName=name.trim().slice(0,50);
  const items=loadCustomLabelTemplates();
  const existing=items.find(t=>t.name.toLowerCase()===cleanName.toLowerCase());
  const item={id:existing?.id || `tpl-${Date.now()}`,name:cleanName,config:labelConfigSnapshot()};
  const next=existing ? items.map(t=>t.id===existing.id?item:t) : [...items,item];
  saveCustomLabelTemplates(next.slice(-20));
  toast(existing?'Modelo atualizado':'Modelo salvo');
  renderQRCode().then(()=>{qrTab('etq');atualizarPreviewEtiqueta(aid);});
}

function deleteCurrentLabelTemplate(aid){
  const value=$('lbl-template')?.value || '';
  const [kind,id]=value.split(':');
  if(kind!=='custom'){
    toast('Selecione um modelo personalizado para excluir.','warn');
    return;
  }
  const items=loadCustomLabelTemplates();
  const item=items.find(t=>t.id===id);
  if(!item){
    toast('Modelo personalizado não encontrado.','error');
    return;
  }
  if(!confirm(`Excluir o modelo "${item.name}"?`)) return;
  saveCustomLabelTemplates(items.filter(t=>t.id!==id));
  toast('Modelo excluído');
  renderQRCode().then(()=>{qrTab('etq');atualizarPreviewEtiqueta(aid);});
}

function lblSetOption(key,val,aid){
  _lblCfg[key]=val;
  saveLabelConfig();
  if(key==='papel'){
    renderQRCode().then(()=>{qrTab('etq');});
    return;
  }
  atualizarPreviewEtiqueta(aid);
}
function lblSetNumber(key,val,aid,min=0,max=99){
  const n=Math.min(max,Math.max(min,+val||min));
  _lblCfg[key]=n;
  saveLabelConfig();
  atualizarPreviewEtiqueta(aid);
}
function lblToggle(campo,val){
  _lblCfg.campos[campo]=val;
  saveLabelConfig();
  atualizarPreviewEtiqueta(_qrSel);
}
function atualizarPreviewEtiqueta(aid){
  // Fetch fresh asset data to rebuild preview
  api('/assets/'+aid).then(asset=>{
    const el=$('lbl-preview');
    if(el) el.innerHTML=buildLabelHtml(asset,'preview');
  });
}

async function imprimirEtiqueta(aid){
  const asset=await api('/assets/'+aid);
  imprimirEtiquetaAssets([asset]);
}

async function imprimirEtiquetasSelecionadas(){
  const ids=[..._qrBatchSel];
  if(!ids.length){
    toast('Selecione ao menos um ativo para imprimir em lote.','warn');
    return;
  }
  const assets=await Promise.all(ids.map(id=>api('/assets/'+encodeURIComponent(id))));
  imprimirEtiquetaAssets(assets);
}

async function baixarEtiquetasPdf(fallbackId){
  const ids=_qrBatchSel.size ? [..._qrBatchSel] : [fallbackId];
  const selectedTemplate=selectedLabelTemplateConfig();
  const exportConfig=labelExportConfig(selectedTemplate);
  try{
    const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
    const resp = await fetch('/api/assets/labels.pdf', {
      method:'POST',
      credentials:'include',
      headers:{'Content-Type':'application/json', ...(csrf ? {'X-CSRFToken':csrf} : {})},
      body:JSON.stringify({ids, config:exportConfig})
    });
    if(!resp.ok){
      const err = await resp.json().catch(()=>({}));
      throw new Error(err.error || `Erro ${resp.status}`);
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = ids.length > 1 ? 'etiquetas_ativos.pdf' : `etiqueta_${ids[0]}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    toast(selectedTemplate?'PDF gerado com modelo selecionado':'PDF de etiquetas gerado');
  }catch(err){
    toast(err.message || 'Falha ao gerar PDF de etiquetas','error');
  }
}

function imprimirEtiquetaAssets(assets){
  let pz=document.getElementById('print-zone');
  if(!pz){pz=document.createElement('div');pz.id='print-zone';pz.className='print-zone';document.body.appendChild(pz);}
  prepareLabelPrintCss();
  pz.dataset.paper=_lblCfg.papel||'a4';
  pz.style.setProperty('--label-print-margin',`${_lblCfg.papel==='unitaria'?0:_lblCfg.margem}mm`);
  pz.style.setProperty('--label-print-gap',`${_lblCfg.gap}mm`);
  pz.innerHTML=assets.map(asset=>buildLabelHtml(asset,'print')).join('');
  window.print();
}

function prepareLabelPrintCss(){
  const sz=labelSizeDef(_lblCfg.size);
  let style=document.getElementById('label-print-page-style');
  if(!style){style=document.createElement('style');style.id='label-print-page-style';document.head.appendChild(style);}
  if(_lblCfg.papel==='unitaria'){
    style.textContent=`@media print{@page{size:${sz.w}mm ${sz.h}mm;margin:0}}`;
  }else{
    style.textContent='@media print{@page{size:A4 portrait;margin:0}}';
  }
}

function qrSel(id){_qrSel=id;renderQRCode();}

function qrBatchToggle(event,id,checked){
  if(event) event.stopPropagation();
  if(checked) _qrBatchSel.add(id);
  else _qrBatchSel.delete(id);
  qrBatchRefreshUi();
}

function qrBatchSelectVisible(ids){
  (ids||[]).forEach(id=>_qrBatchSel.add(id));
  document.querySelectorAll('#content .qr-batch-check').forEach(input=>{input.checked=true;});
  qrBatchRefreshUi();
}

function qrBatchClear(){
  _qrBatchSel.clear();
  document.querySelectorAll('#content .qr-batch-check').forEach(input=>{input.checked=false;});
  qrBatchRefreshUi();
}

function qrBatchRefreshUi(){
  const count=_qrBatchSel.size;
  const counter=$('qr-batch-count');
  const btn=$('btn-print-batch');
  if(counter) counter.textContent=`${count} selecionado(s)`;
  if(btn){
    btn.disabled=!count;
    btn.textContent=`Imprimir selecionados (${count})`;
  }
}
