// ══════════════════════════════════════════════════════════════════════════
// ENTRADA DE ITENS (Ativos + Insumos/Periféricos)
// ══════════════════════════════════════════════════════════════════════════
let _entradaTab = 'ativo'; // 'ativo' | 'insumo'
let _entradaModo = 'individual'; // 'individual' | 'lote'
let _entradaNextPat = '';

async function renderEntrada(){
  const [supplies, r] = await Promise.all([
    api('/supplies'),
    api('/assets/proximo-patrimonio'),
  ]);
  _entradaNextPat = r.patrimonio || '';
  const insumos = supplies;
  $('content').innerHTML = _buildEntradaView(insumos);
  _entradaBindEvents(insumos);
}

function _buildEntradaView(insumos){
  const tabStyle = (tab) =>
    `cursor:pointer;padding:9px 20px;font-size:13px;font-weight:700;border:none;background:transparent;` +
    `border-bottom:2px solid ${_entradaTab===tab?'var(--blue)':'transparent'};` +
    `color:${_entradaTab===tab?'var(--blue)':'var(--text2)'};transition:all .15s`;

  const tabAtivo = _entradaTab === 'ativo';

  const abaAtivo = tabAtivo ? `
    <div class="card" style="margin-top:0">
      <div style="display:flex;gap:12px;margin-bottom:18px">
        <label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer;padding:8px 14px;border-radius:var(--r);border:1px solid ${_entradaModo==='individual'?'var(--blue)':'var(--border)'};background:${_entradaModo==='individual'?'var(--blue-bg)':'var(--bg3)'}">
          <input type="radio" name="ent-modo" value="individual" ${_entradaModo==='individual'?'checked':''} style="width:auto" id="ent-modo-ind"> Individual
        </label>
        <label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer;padding:8px 14px;border-radius:var(--r);border:1px solid ${_entradaModo==='lote'?'var(--blue)':'var(--border)'};background:${_entradaModo==='lote'?'var(--blue-bg)':'var(--bg3)'}">
          <input type="radio" name="ent-modo" value="lote" ${_entradaModo==='lote'?'checked':''} style="width:auto" id="ent-modo-lot"> Em Lote
        </label>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
        <div>
          <div class="form-group"><label>Categoria *</label>
            <select id="ent-cat">
              ${getAssetCats().map(c=>`<option>${c}</option>`).join('')}
            </select>
          </div>
          <div class="form-group"><label>Fabricante *</label><input id="ent-fab" placeholder="Ex: Dell, HP, Lenovo"></div>
          <div class="form-group"><label>Modelo *</label><input id="ent-mod" placeholder="Ex: Latitude 5420"></div>
          <div class="form-group"><label>Nota Fiscal</label><input id="ent-nf" placeholder="NF-2024-001"></div>
          <div class="form-group"><label>Garantia (data)</label><input id="ent-gar" type="date"></div>
        </div>
        <div>
          <div id="ent-individual-fields" style="${_entradaModo==='individual'?'':'display:none'}">
            <div class="form-group"><label>Hostname / Nome</label><input id="ent-hn" placeholder="PC-001"></div>
            <div class="form-group"><label>Service Tag / Nº de Série</label><input id="ent-st" placeholder="ABC123XY"></div>
            <div class="form-group"><label>IP</label><input id="ent-ip" placeholder="DHCP" value="DHCP"></div>
          </div>
          <div id="ent-lote-fields" style="${_entradaModo==='lote'?'':'display:none'}">
            <div class="form-group"><label>Quantidade *</label>
              <input id="ent-qty" type="number" min="1" max="100" value="1" oninput="atualizarPreviewPat()">
            </div>
          </div>

          <div style="padding:14px 16px;background:var(--blue-bg);border-radius:var(--r);border:1px solid var(--blue-border);margin-bottom:10px">
            <div style="font-size:10px;font-weight:800;color:var(--blue-text);text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px">Próximo Patrimônio Gerado</div>
            <div id="ent-pat-preview" class="mono" style="font-size:18px;font-weight:800;color:var(--blue)"></div>
            <div id="ent-pat-range" style="font-size:11px;color:var(--blue-text);margin-top:3px;display:none"></div>
          </div>
          <div style="padding:10px 14px;background:var(--green-bg);border-radius:var(--r);border:1px solid var(--green-border);font-size:12px;color:var(--green-text)">
            O patrimônio é gerado <strong>automaticamente</strong> em sequência ao confirmar a entrada.
          </div>
        </div>
      </div>

      <div class="modal-footer" style="margin-top:18px;padding-top:16px;border-top:1px solid var(--border);justify-content:flex-end">
        <button class="btn btn-primary" onclick="salvarEntradaAtivo()">
          ${inlineIcon('entrada')} Registrar Entrada
        </button>
      </div>
    </div>
  ` : '';

  const abaInsumo = !tabAtivo ? `
    <div class="card" style="margin-top:0">
      <div class="form-group"><label>Item / Insumo *</label>
        <select id="ent-ins-id">
          <option value="">— Selecione o item —</option>
          ${insumos.map(s=>`<option value="${s.id}">${esc(s.nome)} (${esc(s.categoria)}) — estoque atual: ${s.estoque}</option>`).join('')}
        </select>
      </div>
      <div class="form-grid-2">
        <div class="form-group"><label>Quantidade *</label><input id="ent-ins-qty" type="number" min="1" value="1"></div>
        <div class="form-group"><label>Motivo</label>
          <select id="ent-ins-motivo"><option>Compra</option><option>Devolução</option><option>Ajuste</option><option>Outro</option></select>
        </div>
      </div>
      <div class="info-box blue" style="font-size:12px">Para <strong>cadastrar um novo insumo</strong>, acesse o menu <strong>Insumos &amp; Periféricos</strong>.</div>
      <div class="modal-footer" style="margin-top:18px;padding-top:16px;border-top:1px solid var(--border);justify-content:flex-end">
        <button class="btn btn-success" onclick="salvarEntradaInsumo()">
          ${inlineIcon('entrada')} Registrar Entrada de Estoque
        </button>
      </div>
    </div>
  ` : '';

  return `
  <div style="max-width:860px;margin:0 auto">
    <div class="flex-between mb-16">
      <div>
        <div style="font-size:17px;font-weight:800;color:var(--text);margin-bottom:2px">Entrada de Itens</div>
        <div style="font-size:12px;color:var(--text3)">Registre entrada de ativos patrimoniais ou reposição de estoque de insumos e periféricos</div>
      </div>
    </div>

    <div style="background:var(--bg2);border:1px solid var(--border);border-radius:var(--rl);overflow:hidden;box-shadow:var(--shadow-sm)">
      <div style="display:flex;border-bottom:1px solid var(--border);padding:0 8px">
        <button id="ent-tab-ativo" style="${tabStyle('ativo')}" onclick="mudarTabEntrada('ativo')">
          ${inlineIcon('ativos')} Ativo de TI
        </button>
        <button id="ent-tab-insumo" style="${tabStyle('insumo')}" onclick="mudarTabEntrada('insumo')">
          ${inlineIcon('insumos')} Insumo / Periférico
        </button>
      </div>
      <div style="padding:20px 22px">
        ${abaAtivo}${abaInsumo}
      </div>
    </div>
  </div>`;
}

function _entradaBindEvents(insumos){
  atualizarPreviewPat();
  document.querySelectorAll('input[name="ent-modo"]').forEach(r=>{
    r.addEventListener('change', e=>{
      _entradaModo = e.target.value;
      const ind = document.getElementById('ent-individual-fields');
      const lot = document.getElementById('ent-lote-fields');
      if(ind) ind.style.display = _entradaModo==='individual' ? '' : 'none';
      if(lot) lot.style.display = _entradaModo==='lote' ? '' : 'none';
      atualizarPreviewPat();
    });
  });
}

async function mudarTabEntrada(tab){
  _entradaTab = tab;
  await renderEntrada();
}

function atualizarPreviewPat(){
  const prev = document.getElementById('ent-pat-preview');
  const range = document.getElementById('ent-pat-range');
  if(!prev) return;
  prev.textContent = _entradaNextPat || '...';
  if(_entradaModo === 'lote' && range){
    const qty = Math.max(1, parseInt(document.getElementById('ent-qty')?.value)||1);
    if(qty > 1 && _entradaNextPat){
      const parts = _entradaNextPat.split('-');
      const prefix = parts.slice(0, -1).join('-');
      const firstNum = parseInt(parts[parts.length-1]);
      const lastPat = `${prefix}-${String(firstNum + qty - 1).padStart(6,'0')}`;
      range.style.display='';
      range.textContent = `até ${lastPat} (${qty} itens)`;
    } else {
      range.style.display='none';
    }
  } else if(range){
    range.style.display='none';
  }
}

async function salvarEntradaAtivo(){
  const fab = document.getElementById('ent-fab')?.value?.trim();
  const mod = document.getElementById('ent-mod')?.value?.trim();
  const cat = document.getElementById('ent-cat')?.value;
  if(!fab||!mod||!cat){ toast('Preencha fabricante, modelo e categoria','error'); return; }

  try{
    if(_entradaModo === 'individual'){
      const r = await api('/assets','POST',{
        hostname: document.getElementById('ent-hn')?.value?.trim()||'',
        fabricante: fab, modelo: mod, categoria: cat,
        serviceTag: document.getElementById('ent-st')?.value?.trim()||'',
        ip: document.getElementById('ent-ip')?.value?.trim()||'DHCP',
        nf: document.getElementById('ent-nf')?.value?.trim()||'',
        garantia: document.getElementById('ent-gar')?.value||'',
        status: 'Disponível',
      });
      toast(`Ativo cadastrado — Patrimônio: ${r.patrimonio}`);
    } else {
      const qty = Math.max(1, parseInt(document.getElementById('ent-qty')?.value)||1);
      const lista = await api('/assets/lote','POST',{
        fabricante: fab, modelo: mod, categoria: cat,
        nf: document.getElementById('ent-nf')?.value?.trim()||'',
        garantia: document.getElementById('ent-gar')?.value||'',
        quantidade: qty,
      });
      toast(`${lista.length} ativo(s) cadastrado(s) — ${lista[0].patrimonio} até ${lista[lista.length-1].patrimonio}`);
    }
    await renderEntrada();
  }catch(e){ toast(e.message,'error'); }
}

async function salvarEntradaInsumo(){
  const id = document.getElementById('ent-ins-id')?.value;
  const qty = parseInt(document.getElementById('ent-ins-qty')?.value)||0;
  const motivo = document.getElementById('ent-ins-motivo')?.value||'Compra';
  if(!id){ toast('Selecione um item','error'); return; }
  if(qty < 1){ toast('Quantidade inválida','error'); return; }
  try{
    await api(`/supplies/${id}/entrada`,'POST',{quantidade:qty,motivo});
    toast('Entrada de estoque registrada');
    await renderEntrada();
  }catch(e){ toast(e.message,'error'); }
}

