// ══════════════════════════════════════════════════════════════════════════
// ══════════════════════════════════════════════════════════════════════════
// QR CODE & ETIQUETAS
// ══════════════════════════════════════════════════════════════════════════
let _qrSel=null;
let _allocTab='pend';
let _cfgTab='geral';
let _qrBatchSel=new Set();
let _printPrinters=[];
let _labelEditorTab='campos';
const LABEL_CFG_KEY = 'ticontrol-label-config-v2';
const LABEL_CUSTOM_TEMPLATES_KEY = 'ticontrol-label-templates-v1';
const LABEL_SIZES = {
  pequena:{label:'Pequena',dim:'58 x 38 mm',w:58,h:38,qr:18,fs:9},
  media:{label:'Media',dim:'88 x 38 mm',w:88,h:38,qr:22,fs:10},
  grande:{label:'Grande',dim:'100 x 70 mm',w:100,h:70,qr:30,fs:12},
  personalizada:{label:'Personalizada',dim:'medida informada',w:88,h:38,qr:22,fs:10}
};
const LABEL_DEFAULT_CFG = {
  size:'media',
  customW:88,
  customH:38,
  campos:{hostname:true,patrimonio:true,serviceTag:true,setor:true,colaborador:false,ip:false,garantia:false},
  copias:1,
  empresa:'',
  layout:'auto',
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

function clampLabelMm(value,fallback,min,max){
  const parsed=Number(String(value).replace(',','.'));
  const number=Number.isFinite(parsed)?parsed:fallback;
  return Math.round(Math.min(max,Math.max(min,number))*10)/10;
}

function formatLabelMm(value){
  const n=Number(value);
  if(!Number.isFinite(n)) return '';
  return Number.isInteger(n) ? String(n) : n.toFixed(1).replace('.',',');
}

function labelSizeDef(size){
  if(size === 'personalizada'){
    const w = clampLabelMm(_lblCfg.customW,88,25,150);
    const h = clampLabelMm(_lblCfg.customH,38,15,100);
    const base = Math.min(w, h);
    const maxQr = Math.max(10, Math.min(w - 14, h - 10));
    return {
      label:'Personalizada',
      dim:`${formatLabelMm(w)} x ${formatLabelMm(h)} mm`,
      w,
      h,
      qr:Math.min(Math.max(10, Math.round(base * 0.58)), maxQr),
      fs:Math.min(12, Math.max(7, Math.round(w / 9)))
    };
  }
  return LABEL_SIZES[size]||LABEL_SIZES.media;
}

function labelRenderPlan(sz){
  const qrDelta = _lblCfg.qr==='grande' ? 5 : (_lblCfg.qr==='compacto' ? -5 : 0);
  const forcedLayout = _lblCfg.layout || 'auto';
  const tiny = sz.w < 34 || sz.h < 18;
  const compact = !tiny && (sz.w < 52 || sz.h < 28);
  const pad = tiny ? 1 : (compact ? 1.25 : 2.3);
  const gap = compact ? 1.4 : 2;
  const availableW = Math.max(8, sz.w - (pad * 2));
  const availableH = Math.max(8, sz.h - (pad * 2));
  const compactQrTarget = Math.max(13, sz.qr + qrDelta);
  if(forcedLayout === 'qr-only' || tiny){
    const qr = Math.max(10, Math.min(availableW, availableH));
    return {
      mode:'qr-only',
      qr,
      pad,
      gap,
      maxLines:0,
      notice:forcedLayout === 'qr-only'
        ? 'Modo somente QR ativo. A impressão enviará apenas o QR Code para a etiqueta.'
        : 'Esta etiqueta é muito pequena para texto. O sistema usará somente o QR Code para preservar a leitura.'
    };
  }
  if(forcedLayout === 'compact' || compact){
    const qr = Math.max(10, Math.min(availableH, availableW * 0.48, compactQrTarget));
    const textW = availableW - qr - gap;
    if(textW < 12){
      const qrOnly = Math.max(10, Math.min(availableW, availableH));
      return {mode:'qr-only', qr:qrOnly, pad, gap, maxLines:0, notice:'O tamanho informado deixa pouco espaço para texto. O sistema usará somente o QR Code.'};
    }
    const maxLines = Math.max(2, Math.min(4, Math.floor(availableH / 4.8)));
    return {mode:'compact', qr, pad, gap, textW, maxLines, notice:'Etiqueta pequena: a impressão será compactada e priorizará os campos que couberem.'};
  }
  const qr = Math.max(12, Math.min(sz.h - 7, sz.w * 0.36, sz.qr + qrDelta));
  return {mode:'full', qr, pad, gap, textW:Math.max(20, sz.w - (pad * 2) - qr - gap), maxLines:5, notice:''};
}

function labelPrimaryCode(asset,campos){
  if(campos?.patrimonio && asset.patrimonio) return asset.patrimonio;
  if(campos?.serviceTag && asset.serviceTag) return asset.serviceTag;
  return asset.id;
}

function labelCompactLines(asset,campos){
  const primary=labelPrimaryCode(asset,campos);
  const hn=asset.hostname||asset.id;
  const lines=[{text:primary,strong:true}];
  const add=(text,strong=false)=>{
    const clean=String(text||'').trim();
    if(clean && !lines.some(line=>line.text===clean)) lines.push({text:clean,strong});
  };
  if(campos?.hostname && hn!==primary) add(hn);
  if(campos?.serviceTag && asset.serviceTag) add(`ST ${asset.serviceTag}`);
  if(campos?.setor && asset.setor) add(`Setor ${asset.setor}`);
  if(campos?.colaborador && asset.colaborador) add(asset.colaborador);
  if(campos?.ip && asset.ip) add(`IP ${asset.ip}`);
  if(campos?.garantia && asset.garantia) add(`Gar ${fmtDate(asset.garantia)}`);
  return lines;
}

function labelFitNotice(){
  const plan=labelRenderPlan(labelSizeDef(_lblCfg.size));
  if(!plan.notice) return '';
  return `<div class="info-box amber" style="font-size:11px;line-height:1.5;margin-bottom:12px">${plan.notice}</div>`;
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
  const [assets,printers]=await Promise.all([
    api('/assets?q='+encodeURIComponent(q)),
    api('/print-printers').catch(()=>[])
  ]);
  _printPrinters=Array.isArray(printers)?printers:[];
  if(!_qrSel&&assets.length) _qrSel=assets[0].id;
  const sel=assets.find(a=>a.id===_qrSel)||assets[0];
  const visibleIds=assets.map(a=>a.id);
  const selectedCount=_qrBatchSel.size;
  $('content').innerHTML=`
  <div class="qr-workspace">
    <div class="card qr-asset-selector" style="padding:14px">
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
      <div class="qr-asset-list">
        ${assets.map(a=>`<div onclick="qrSel('${escAttr(a.id)}')" style="display:flex;align-items:center;gap:8px;padding:8px 10px;border-radius:var(--r);cursor:pointer;font-family:var(--mono);font-size:12px;transition:background .1s;${a.id===_qrSel?'background:var(--blue);color:#fff;font-weight:700':'color:var(--text)'}">
          <input class="qr-batch-check" type="checkbox" ${_qrBatchSel.has(a.id)?'checked':''} onclick="qrBatchToggle(event,'${escAttr(a.id)}',this.checked)" style="width:auto;flex-shrink:0">
          <span style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(a.hostname)}</span>
        </div>`).join('')}
      </div>
    </div>
    <div>
      ${sel?renderEtiquetaPanel(sel):'<div class="card"><p style="color:var(--text3)">Selecione um ativo.</p></div>'}
    </div>
  </div>`;
}

function qrTab(tab){
  const panelQr=$('panel-qr');
  const panelEtq=$('panel-etq');
  const tabQr=$('tab-qr');
  const tabEtq=$('tab-etq');
  if(!panelQr||!panelEtq||!tabQr||!tabEtq) return;
  panelQr.style.display  = tab==='qr'  ? '' : 'none';
  panelEtq.style.display = tab==='etq' ? '' : 'none';
  tabQr.style.color  = tab==='qr'  ? 'var(--blue)' : 'var(--text2)';
  tabEtq.style.color = tab==='etq' ? 'var(--blue)' : 'var(--text2)';
  tabQr.style.borderBottomColor  = tab==='qr'  ? 'var(--blue)' : 'transparent';
  tabEtq.style.borderBottomColor = tab==='etq' ? 'var(--blue)' : 'transparent';
}

function renderEtiquetaPanel(sel){
  const sizes=Object.entries(LABEL_SIZES).map(([id,s])=>({id,...s}));
  const bordas=[['preta','Preta'],['azul','Azul'],['cinza','Cinza'],['sem','Sem borda']];
  const campos=[['hostname','Nome / Hostname'],['patrimonio','Patrimônio'],['serviceTag','Service Tag'],
                ['setor','Setor'],['colaborador','Colaborador'],['ip','IP'],['garantia','Garantia']];
  const selectedSize=labelSizeDef(_lblCfg.size);
  return `<div class="card label-editor-card">
    <div class="label-editor-head">
      <div>
        <div style="font-size:15px;font-weight:700;margin-bottom:4px">Configurar Etiqueta</div>
        <div style="font-size:12px;color:var(--text3);line-height:1.5">
          ${esc(sel.hostname||sel.id)}${sel.patrimonio?' · Pat. '+esc(sel.patrimonio):''}${sel.categoria?' · '+esc(sel.categoria):''}
        </div>
      </div>
      <a href="/asset/${sel.id}" class="btn btn-default btn-sm" target="_blank">Ver perfil público</a>
    </div>
    <div class="label-editor-layout">
      <div class="label-editor-controls">
        <div class="label-editor-model-row">
          <select id="lbl-template" aria-label="Modelo de etiqueta">
            <option value="">Selecionar modelo</option>
            ${labelTemplateOptions()}
          </select>
          <button class="btn btn-primary btn-sm" type="button" onclick="applyLabelTemplate('${sel.id}')">Aplicar</button>
          <button class="btn btn-default btn-sm btn-icon" type="button" onclick="saveCurrentLabelTemplate('${sel.id}')" title="Salvar modelo" aria-label="Salvar modelo">${inlineIcon('save')}</button>
          <button class="btn btn-default btn-sm btn-icon" type="button" onclick="deleteCurrentLabelTemplate('${sel.id}')" title="Excluir modelo" aria-label="Excluir modelo">${inlineIcon('trash')}</button>
        </div>

        <div class="label-editor-quick-grid">
          <div class="form-group">
            <label>Tamanho</label>
            <select id="lbl-size" onchange="lblSetSize(this.value)">
              ${sizes.map(s=>`<option value="${s.id}" ${_lblCfg.size===s.id?'selected':''}>${s.label} · ${s.dim}</option>`).join('')}
            </select>
          </div>
          <div class="form-group">
            <label>Cópias</label>
            <input id="lbl-copias" type="number" min="1" max="20" value="${_lblCfg.copias}" oninput="lblSetNumber('copias',this.value,'${sel.id}',1,20)">
          </div>
        </div>
        <div id="lbl-custom-size" class="label-custom-size" style="${_lblCfg.size==='personalizada'?'':'display:none'}">
          <div class="form-group">
            <label>Largura (mm)</label>
            <input id="lbl-custom-w" type="number" min="25" max="150" step="0.1" value="${formatLabelMm(clampLabelMm(_lblCfg.customW,88,25,150)).replace(',','.')}" oninput="lblSetCustomSize('customW',this.value,'${sel.id}')">
          </div>
          <div class="form-group">
            <label>Altura (mm)</label>
            <input id="lbl-custom-h" type="number" min="15" max="100" step="0.1" value="${formatLabelMm(clampLabelMm(_lblCfg.customH,38,15,100)).replace(',','.')}" oninput="lblSetCustomSize('customH',this.value,'${sel.id}')">
          </div>
        </div>

        <div class="label-editor-tabs" role="tablist" aria-label="Configurações da etiqueta">
          ${[['campos','Campos'],['aparencia','Aparência'],['saida','Saída']].map(([id,label])=>`
            <button id="lbl-tab-${id}" class="${_labelEditorTab===id?'active':''}" type="button" onclick="labelEditorTab('${id}')" role="tab" aria-selected="${_labelEditorTab===id}">${label}</button>`).join('')}
        </div>

        <div id="lbl-panel-campos" class="label-editor-tab-panel" style="display:${_labelEditorTab==='campos'?'grid':'none'}">
          ${campos.map(([k,label])=>`<label class="label-check-option">
            <input type="checkbox" id="lbl-c-${k}" ${_lblCfg.campos[k]?'checked':''} onchange="lblToggle('${k}',this.checked)">
            <span>${label}</span>
          </label>`).join('')}
        </div>

        <div id="lbl-panel-aparencia" class="label-editor-tab-panel" style="display:${_labelEditorTab==='aparencia'?'grid':'none'}">
          <div class="form-group"><label>Conteúdo</label>
            <select id="lbl-layout" onchange="lblSetOption('layout',this.value,'${sel.id}')">
              <option value="auto" ${(_lblCfg.layout||'auto')==='auto'?'selected':''}>Automático</option>
              <option value="compact" ${_lblCfg.layout==='compact'?'selected':''}>Compacto</option>
              <option value="qr-only" ${_lblCfg.layout==='qr-only'?'selected':''}>Somente QR</option>
            </select>
          </div>
          <div class="form-group"><label>QR Code</label>
            <select id="lbl-qr" onchange="lblSetOption('qr',this.value,'${sel.id}')">
              <option value="normal" ${_lblCfg.qr==='normal'?'selected':''}>Normal</option>
              <option value="grande" ${_lblCfg.qr==='grande'?'selected':''}>Maior</option>
              <option value="compacto" ${_lblCfg.qr==='compacto'?'selected':''}>Compacto</option>
            </select>
          </div>
          <div class="form-group"><label>Borda</label>
            <select id="lbl-borda" onchange="lblSetOption('borda',this.value,'${sel.id}')">
              ${bordas.map(([v,l])=>`<option value="${v}" ${_lblCfg.borda===v?'selected':''}>${l}</option>`).join('')}
            </select>
          </div>
          <div class="form-group"><label>Nome da empresa</label>
            <input id="lbl-empresa" value="${escAttr(_lblCfg.empresa)}" placeholder="Opcional" oninput="lblSetOption('empresa',this.value,'${sel.id}')">
          </div>
          <label class="label-check-option label-option-wide">
            <input type="checkbox" ${_lblCfg.mostrarSistema?'checked':''} onchange="lblSetOption('mostrarSistema',this.checked,'${sel.id}')">
            <span>Exibir identificação TI Control</span>
          </label>
          ${(_settings?.empresa?.logo_base64) ? `
            <label class="label-check-option"><input type="checkbox" ${_lblCfg.logoEmpresa?'checked':''} onchange="lblSetOption('logoEmpresa',this.checked,'${sel.id}')"><span>Exibir logo</span></label>
            <label class="label-check-option"><input type="checkbox" ${_lblCfg.logoNoQr?'checked':''} onchange="lblSetOption('logoNoQr',this.checked,'${sel.id}')"><span>Logo no QR Code</span></label>
          ` : '<div class="label-option-wide" style="font-size:11px;color:var(--text3)">Logo não configurado.</div>'}
        </div>

        <div id="lbl-panel-saida" class="label-editor-tab-panel" style="display:${_labelEditorTab==='saida'?'grid':'none'}">
          <div class="form-group"><label>Formato</label>
            <select id="lbl-papel" onchange="lblSetOption('papel',this.value,'${sel.id}')">
              <option value="a4" ${_lblCfg.papel==='a4'?'selected':''}>A4 / folha</option>
              <option value="unitaria" ${_lblCfg.papel==='unitaria'?'selected':''}>Etiqueta individual</option>
            </select>
          </div>
          <div class="form-group"><label>Margem (mm)</label>
            <input id="lbl-margem" type="number" min="0" max="20" value="${_lblCfg.margem}" oninput="lblSetNumber('margem',this.value,'${sel.id}')" ${_lblCfg.papel==='unitaria'?'disabled':''}>
          </div>
          <div class="form-group"><label>Espaço (mm)</label>
            <input id="lbl-gap" type="number" min="0" max="10" value="${_lblCfg.gap}" oninput="lblSetNumber('gap',this.value,'${sel.id}')">
          </div>
        </div>
      </div>

      <div class="label-editor-preview-column">
        <div class="label-editor-preview-head">
          <span>Pré-visualização</span>
          <span id="lbl-size-badge" class="badge badge-gray">${esc(selectedSize.dim)}</span>
        </div>
        <div id="lbl-fit-notice">${labelFitNotice()}</div>
        <div id="lbl-preview" class="label-editor-preview">
          ${buildLabelHtml(sel,'preview')}
        </div>
      </div>
    </div>

    <div class="label-editor-actions">
      <div class="label-agent-action">
        <select id="lbl-printer" aria-label="Agente de impressão">
          ${_printPrinters.length
            ? _printPrinters.map(p=>`<option value="${escAttr(p.id)}">${esc(p.id)}${p.location?' · '+esc(p.location):''}${p.status?' · '+esc(p.status):''}</option>`).join('')
            : '<option value="">Nenhum agente cadastrado</option>'}
        </select>
        <button class="btn btn-primary btn-sm" onclick="enviarEtiquetaAgente('${sel.id}')" ${_printPrinters.length?'':'disabled'}>${inlineIcon('printer')} Enviar ao agente</button>
      </div>
      <div class="label-output-actions">
        <button class="btn btn-default btn-sm" onclick="baixarEtiquetasPdf('${sel.id}')">${inlineIcon('download')} PDF</button>
        <button id="btn-print-batch" class="btn btn-default btn-sm" onclick="imprimirEtiquetasSelecionadas()" ${_qrBatchSel.size?'':'disabled'}>Selecionados (${_qrBatchSel.size})</button>
        <button class="btn btn-primary btn-sm" onclick="imprimirEtiqueta('${sel.id}')">${inlineIcon('printer')} Imprimir</button>
      </div>
    </div>
  </div>`;
}

function labelEditorTab(tab){
  _labelEditorTab=['campos','aparencia','saida'].includes(tab)?tab:'campos';
  ['campos','aparencia','saida'].forEach(id=>{
    const active=id===_labelEditorTab;
    const button=$(`lbl-tab-${id}`);
    const panel=$(`lbl-panel-${id}`);
    if(button){
      button.classList.toggle('active',active);
      button.setAttribute('aria-selected',String(active));
    }
    if(panel) panel.style.display=active?'grid':'none';
  });
}

function buildLabelHtml(asset,mode){
  const sz=labelSizeDef(_lblCfg.size);
  const plan=labelRenderPlan(sz);
  const qrSize=plan.qr;
  const borderMap = {preta:'1.5px solid #111827',azul:'1.5px solid #2563eb',cinza:'1.5px solid #94a3b8',sem:'1px solid transparent'};
  const cls    = mode==='print' ? 'label-print-item' : 'label-card';
  const campos = _lblCfg.campos;
  const logo   = _settings?.empresa?.logo_base64 || '';
  const border = borderMap[_lblCfg.borda]||borderMap.preta;
  const baseStyle = `width:${sz.w}mm;height:${sz.h}mm;padding:${plan.pad}mm;display:flex;border:${border}`;

  const overlaySize = Math.round(Math.max(3, qrSize * 0.24) * 10) / 10;
  const qrHtml = `<div style="position:relative;display:inline-block;flex-shrink:0">
    <img src="/api/assets/${asset.id}/qrcode" style="display:block;width:${qrSize}mm;height:${qrSize}mm">
    ${(logo && _lblCfg.logoNoQr) ? `<img src="${logo}" style="position:absolute;z-index:2;top:50%;left:50%;transform:translate(-50%,-50%);width:${overlaySize}mm;height:${overlaySize}mm;object-fit:contain;background:#fff;padding:.45mm;border-radius:.8mm;box-sizing:border-box">` : ''}
  </div>`;

  const hn = asset.hostname || asset.id;
  const primaryCode = labelPrimaryCode(asset,campos);

  if(plan.mode === 'qr-only'){
    const inner=`
      <div class="${cls}" data-label-mode="qr-only" style="${baseStyle};align-items:center;justify-content:center;border-radius:1mm">
        ${qrHtml}
      </div>`;
    if(mode==='print'){
      let out='';
      for(let i=0;i<(_lblCfg.copias||1);i++) out+=inner;
      return out;
    }
    return inner;
  }

  if(plan.mode === 'compact'){
    const lines=labelCompactLines(asset,campos).slice(0,plan.maxLines||2);
    const renderLine=line=>{
      const maxFs=line.strong ? 6.8 : 5.2;
      const minFs=line.strong ? 4.1 : 3.4;
      const factor=line.strong ? 0.42 : 0.5;
      const fs=Math.max(minFs,Math.min(maxFs,plan.textW/Math.max(1,line.text.length*factor)));
      return `<div class="${line.strong?'lbl-hostname':'lbl-field'}" style="font-size:${fs}pt;line-height:1.05;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin:0;color:${line.strong?'#000':'#333'}">${esc(line.text)}</div>`;
    };
    const inner=`
      <div class="${cls}" data-label-mode="compact" style="${baseStyle};align-items:center;gap:${plan.gap}mm;border-radius:1mm">
        ${qrHtml}
        <div style="min-width:0;flex:1;overflow:hidden;color:#000;display:flex;flex-direction:column;justify-content:center;gap:.45mm">
          ${lines.map(renderLine).join('')}
        </div>
      </div>`;
    if(mode==='print'){
      let out='';
      for(let i=0;i<(_lblCfg.copias||1);i++) out+=inner;
      return out;
    }
    return inner;
  }

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

  // auto-shrink hostname: calcula font-size para caber em uma linha
  const textAreaW = plan.textW;
  const autoFs = Math.max(6.5, Math.min(sz.fs, Math.floor(textAreaW / Math.max(1, hn.length * 0.32))));

  const inner=`
    <div class="${cls}" data-label-mode="full" style="${baseStyle};flex-direction:column;justify-content:space-between;border-radius:2mm">
      <div style="overflow:hidden">
        ${topoHtml}
        <div style="display:flex;gap:${plan.gap}mm;align-items:flex-start">
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
  renderQRCode();
}

function lblSetCustomSize(key,val,aid){
  const min = key === 'customW' ? 25 : 15;
  const max = key === 'customW' ? 150 : 100;
  const fallback = key === 'customW' ? 88 : 38;
  _lblCfg[key]=clampLabelMm(val,_lblCfg[key]||fallback,min,max);
  _lblCfg.size='personalizada';
  saveLabelConfig();
  atualizarPreviewEtiqueta(aid);
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
  renderQRCode().then(()=>{atualizarPreviewEtiqueta(aid);});
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
  renderQRCode().then(()=>{atualizarPreviewEtiqueta(aid);});
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
  renderQRCode().then(()=>{atualizarPreviewEtiqueta(aid);});
}

function lblSetOption(key,val,aid){
  _lblCfg[key]=val;
  saveLabelConfig();
  if(key==='papel'){
    renderQRCode();
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
    const sizeBadge=$('lbl-size-badge');
    if(sizeBadge) sizeBadge.textContent=labelSizeDef(_lblCfg.size).dim;
    const fitNotice=$('lbl-fit-notice');
    if(fitNotice) fitNotice.innerHTML=labelFitNotice();
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

function selectedPrinterId(){
  return $('lbl-printer')?.value || '';
}

async function enviarEtiquetaAgente(fallbackId){
  const printerId=selectedPrinterId();
  if(!printerId){
    toast('Cadastre ou selecione uma impressora/agente.','warn');
    return;
  }
  const ids=_qrBatchSel.size ? [..._qrBatchSel] : [fallbackId];
  const selectedTemplate=selectedLabelTemplateConfig();
  const exportConfig=labelExportConfig(selectedTemplate);
  try{
    await api('/print-jobs','POST',{
      printerId,
      ids,
      template:'ETQ_PATRIMONIO_ZPL',
      copies:_lblCfg.copias||1,
      config:exportConfig,
    });
    toast(`${ids.length} etiqueta(s) enviada(s) para a fila da impressora.`);
  }catch(err){
    toast(err.message||'Falha ao enviar etiqueta para a fila','error');
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
