// ══════════════════════════════════════════════════════════════════════════
// ══════════════════════════════════════════════════════════════════════════
// QR CODE & ETIQUETAS
// ══════════════════════════════════════════════════════════════════════════
let _qrSel=null;
let _allocTab='pend';
let _cfgTab='geral';
let _lblCfg={
  size:'media',
  campos:{hostname:true,patrimonio:true,serviceTag:true,setor:true,colaborador:false,ip:false,garantia:false},
  copias:1,
  empresa:'',
  qr:'normal',
  borda:'preta',
  mostrarSistema:true,
  logoEmpresa:false,
  logoNoQr:false,
};

async function renderQRCode(q=''){
  const assets=await api('/assets?q='+encodeURIComponent(q));
  if(!_qrSel&&assets.length) _qrSel=assets[0].id;
  const sel=assets.find(a=>a.id===_qrSel)||assets[0];
  $('content').innerHTML=`
  <div style="display:grid;grid-template-columns:240px 1fr;gap:16px">
    <div class="card" style="padding:14px">
      <div style="font-size:12px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.04em;margin-bottom:10px">Selecionar Ativo</div>
      <div class="search-wrap" style="margin-bottom:10px"><span class="search-icon">${inlineIcon('search')}</span>
        <input style="width:100%" value="${esc(q)}" placeholder="Buscar ativo..." onkeyup="debounce(()=>renderQRCode(this.value))">
      </div>
      <div style="display:flex;flex-direction:column;gap:2px;max-height:440px;overflow-y:auto">
        ${assets.map(a=>`<div onclick="qrSel('${a.id}')" style="padding:8px 10px;border-radius:var(--r);cursor:pointer;font-family:var(--mono);font-size:12px;transition:background .1s;${a.id===_qrSel?'background:var(--blue);color:#fff;font-weight:700':'color:var(--text)'}">${esc(a.hostname)}</div>`).join('')}
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
  const sizes=[{id:'pequena',label:'Pequena',dim:'58 × 38 mm',w:'120px',h:'72px'},
               {id:'media',label:'Média',dim:'88 × 38 mm',w:'180px',h:'72px'},
               {id:'grande',label:'Grande',dim:'100 × 70 mm',w:'200px',h:'136px'}];
  const bordas=[['preta','Preta'],['azul','Azul'],['cinza','Cinza'],['sem','Sem borda']];
  const campos=[['hostname','Nome / Hostname'],['patrimonio','Patrimônio'],['serviceTag','Service Tag'],
                ['setor','Setor'],['colaborador','Colaborador'],['ip','IP'],['garantia','Garantia']];
  return `<div class="card">
    <div style="font-size:15px;font-weight:700;margin-bottom:18px">Configurar Etiqueta</div>
    <div style="display:grid;grid-template-columns:260px 1fr;gap:20px">
      <div>
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
            <select id="lbl-qr" onchange="_lblCfg.qr=this.value;atualizarPreviewEtiqueta('${sel.id}')">
              <option value="normal" ${_lblCfg.qr==='normal'?'selected':''}>Normal</option>
              <option value="grande" ${_lblCfg.qr==='grande'?'selected':''}>Maior</option>
              <option value="compacto" ${_lblCfg.qr==='compacto'?'selected':''}>Compacto</option>
            </select>
          </div>
          <div class="form-group" style="margin-bottom:0">
            <label>Borda</label>
            <select id="lbl-borda" onchange="_lblCfg.borda=this.value;atualizarPreviewEtiqueta('${sel.id}')">
              ${bordas.map(([v,l])=>`<option value="${v}" ${_lblCfg.borda===v?'selected':''}>${l}</option>`).join('')}
            </select>
          </div>
        </div>
        <label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer;padding:0 0 14px">
          <input type="checkbox" ${_lblCfg.mostrarSistema?'checked':''} onchange="_lblCfg.mostrarSistema=this.checked;atualizarPreviewEtiqueta('${sel.id}')" style="width:auto">
          Exibir identificação TI Control
        </label>
        <div style="font-size:12px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px">Nome da empresa (opcional)</div>
        <input id="lbl-empresa" value="${esc(_lblCfg.empresa)}" placeholder="Ex: ACME Corp" oninput="_lblCfg.empresa=this.value;atualizarPreviewEtiqueta('${sel.id}')" style="margin-bottom:16px">

        <div style="font-size:12px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px">Logo da Empresa</div>
        ${(_settings?.empresa?.logo_base64) ? `
        <div style="margin-bottom:6px;padding:6px 8px;background:var(--bg3);border:1px solid var(--border);border-radius:var(--r);display:inline-flex;align-items:center;gap:8px">
          <img src="${_settings.empresa.logo_base64}" style="height:18px;object-fit:contain;max-width:80px">
          <span style="font-size:10px;color:var(--text3)">logo cadastrado</span>
        </div>
        <div style="display:flex;flex-direction:column;gap:6px;margin-top:8px;margin-bottom:14px">
          <label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer">
            <input type="checkbox" ${_lblCfg.logoEmpresa?'checked':''} onchange="_lblCfg.logoEmpresa=this.checked;atualizarPreviewEtiqueta('${sel.id}')" style="width:auto">
            Exibir logo na etiqueta
          </label>
          <label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer">
            <input type="checkbox" ${_lblCfg.logoNoQr?'checked':''} onchange="_lblCfg.logoNoQr=this.checked;atualizarPreviewEtiqueta('${sel.id}')" style="width:auto">
            Logo no centro do QR Code
          </label>
        </div>` : `
        <div style="font-size:11px;color:var(--text3);margin-bottom:14px;padding:8px 10px;background:var(--bg3);border:1px solid var(--border);border-radius:var(--r);line-height:1.6">
          Nenhum logo cadastrado.<br>
          Configure em <b>Configurações → Geral → Dados da Empresa</b>.
        </div>`}

        <div style="font-size:12px;font-weight:700;color:var(--text2);text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px">Cópias por ativo</div>
        <input id="lbl-copias" type="number" min="1" max="20" value="${_lblCfg.copias}" oninput="_lblCfg.copias=Math.max(1,+this.value||1);atualizarPreviewEtiqueta('${sel.id}')" style="width:80px;margin-bottom:18px">
        <div style="display:flex;gap:8px">
          <button class="btn btn-primary" onclick="imprimirEtiqueta('${sel.id}')">Imprimir etiqueta</button>
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
  const sz={pequena:{w:'116px',h:'72px',qr:48,fs:11},
            media  :{w:'176px',h:'72px',qr:56,fs:12},
            grande :{w:'200px',h:'140px',qr:72,fs:13}}[_lblCfg.size]||{w:'176px',h:'72px',qr:56,fs:12};
  const qrDelta = _lblCfg.qr==='grande' ? 14 : (_lblCfg.qr==='compacto' ? -12 : 0);
  const qrSize  = Math.max(34, sz.qr + qrDelta);
  const borderMap = {preta:'1.5px solid #111827',azul:'1.5px solid #2563eb',cinza:'1.5px solid #94a3b8',sem:'1px solid transparent'};
  const cls    = mode==='print' ? 'label-print-item' : 'label-card';
  const campos = _lblCfg.campos;
  const logo   = _settings?.empresa?.logo_base64 || '';

  // topo da etiqueta: logo ao lado do nome da empresa
  const _hasLogo = logo && _lblCfg.logoEmpresa;
  const _hasNome = !!_lblCfg.empresa;
  const topoHtml = (_hasLogo || _hasNome) ? `<div style="display:flex;align-items:center;gap:4px;margin-bottom:2px;overflow:hidden;max-width:100%">${
    _hasLogo ? `<img src="${logo}" style="height:12px;flex-shrink:0;object-fit:contain;object-position:left">` : ''
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
  const overlaySize = Math.round(qrSize * 0.26);
  const qrHtml = `<div style="position:relative;display:inline-block;flex-shrink:0">
    <img src="/api/assets/${asset.id}/qrcode" width="${qrSize}" height="${qrSize}" style="display:block">
    ${(logo && _lblCfg.logoNoQr) ? `<img src="${logo}" style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:${overlaySize}px;height:${overlaySize}px;object-fit:contain;background:#fff;padding:1px;border-radius:2px">` : ''}
  </div>`;

  // auto-shrink hostname: calcula font-size para caber em uma linha
  const hn = asset.hostname || asset.id;
  const textAreaW = parseInt(sz.w) - 16 - qrSize - 6; // padding + qr + gap
  const autoFs = Math.max(7, Math.min(sz.fs, Math.floor(textAreaW / (hn.length * 0.58))));

  const inner=`
    <div class="${cls}" style="width:${sz.w};min-height:${sz.h};padding:7px 8px;display:flex;flex-direction:column;justify-content:space-between;border:${borderMap[_lblCfg.borda]||borderMap.preta}">
      <div style="overflow:hidden">
        ${topoHtml}
        <div style="display:flex;gap:6px;align-items:flex-start">
          <div style="flex:1;overflow:hidden">
            ${campos.hostname?`<div class="lbl-hostname" style="font-size:${autoFs}px">${esc(hn)}</div>`:''}
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
  // Re-render the etiqueta panel for the current asset
  const sel=_qrSel;
  renderQRCode().then(()=>{qrTab('etq');});
}
function lblToggle(campo,val){
  _lblCfg.campos[campo]=val;
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
  // Create / reuse a hidden print zone
  let pz=document.getElementById('print-zone');
  if(!pz){pz=document.createElement('div');pz.id='print-zone';pz.className='print-zone';document.body.appendChild(pz);}
  pz.innerHTML=buildLabelHtml(asset,'print');
  window.print();
}

function qrSel(id){_qrSel=id;renderQRCode();}

