// ══════════════════════════════════════════════════════════════════════════
// DASHBOARD
// ══════════════════════════════════════════════════════════════════════════
async function renderDashboard(){
  const d=await api('/dashboard');
  if(!d) return;
  const {totais,colaboradores,devolucoes,categorias,alertas,ultimasAlocacoes,licencas}=d;
  state.alertCount=alertas.length; updateAlertBadge();
  // Busca empréstimos vencidos de forma silenciosa
  const emprestimosVencidos = await api('/emprestimos/vencidos').catch(()=>[]);

  const devPend = (devolucoes?.aguardandoLaudo||0)+(devolucoes?.aguardandoRH||0);
  const devPendentes = devolucoes?.pendentes||[];

  // ── ícones do dashboard: usa ICONS global; extras locais apenas para ícones sem equivalente ──
  const _dashIco = {
    rotate: '<path d="M9 14l-4-4 4-4"/><path d="M5 10h11a4 4 0 0 1 0 8h-1"/>',
    chart:  '<line x1="18" x2="18" y1="20" y2="10"/><line x1="12" x2="12" y1="20" y2="4"/><line x1="6" x2="6" y1="20" y2="14"/>',
    checkCircle: '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/>',
  };
  const svgIco = (k,c)=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:20px;height:20px;color:var(--${c})">${ICONS[k]||_dashIco[k]||''}</svg>`;

  // ── stat card helper ──────────────────────────────────────────────────
  const statCard = (label,value,icoKey,color,sub='',onclick='')=>`
  <div class="stat-card" ${onclick?`style="cursor:pointer" onclick="${onclick}"`:''}
       title="${onclick?'Clique para ver detalhes':''}">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
      <div style="min-width:0">
        <div class="stat-label">${label}</div>
        <div class="stat-value" style="color:var(--${color})">${value}</div>
        ${sub?`<div style="font-size:11px;color:var(--text3);margin-top:2px">${sub}</div>`:''}
      </div>
      <div style="padding:9px;background:var(--${color}-bg);border-radius:var(--r);flex-shrink:0">
        ${svgIco(icoKey,color)}
      </div>
    </div>
  </div>`;

  // ── badge laudo ───────────────────────────────────────────────────────
  const laudoBadgeDash = s => {
    if(!s||s==='Aguardando Laudo') return `<span style="display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700;background:var(--amber-bg);color:var(--amber-text)">Aguardando Laudo</span>`;
    return `<span style="display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700;background:var(--blue-bg);color:var(--blue-text)">Aguardando RH</span>`;
  };

  // ── seção de devoluções pendentes ─────────────────────────────────────
  const secDevPend = devPendentes.length===0 ? '' : `
  <div class="card mb-16" style="border-left:3px solid var(--amber)">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
      <div style="display:flex;align-items:center;gap:8px">
        ${svgIco('rotate','amber')}
        <span style="font-size:14px;font-weight:700">Devoluções Aguardando Ação</span>
        <span style="display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:800;background:var(--amber-bg);color:var(--amber-text)">${devPend}</span>
      </div>
      <button class="btn btn-default btn-sm" onclick="navigateTo('alocacoes');setTimeout(()=>allocTab('devol'),400)">Ver todas</button>
    </div>
    <div class="table-wrap"><table>
      <thead><tr><th>Colaborador</th><th>Setor</th><th>Data</th><th>Status</th><th>Ação</th></tr></thead>
      <tbody>${devPendentes.map(dv=>`<tr>
        <td style="font-weight:600">${esc(dv.colaborador)}</td>
        <td style="font-size:12px;color:var(--text2)">${esc(dv.setor||'—')}</td>
        <td style="font-size:12px;color:var(--text2)">${fmtDate(dv.dataDevolucao)}</td>
        <td>${laudoBadgeDash(dv.laudoStatus)}</td>
        <td>${(!dv.laudoStatus||dv.laudoStatus==='Aguardando Laudo')
          ? `<button class="btn btn-primary btn-sm" onclick="abrirLaudoPorId('${dv.id}')">Registrar Laudo</button>`
          : `<span style="font-size:11px;color:var(--text3)">Aguardando RH</span>`}
        </td>
      </tr>`).join('')}
      </tbody>
    </table></div>
  </div>`;

  // ── pct uso ativos ────────────────────────────────────────────────────
  const pctAloc = totais.ativos>0?Math.round(totais.alocados/totais.ativos*100):0;
  const licUsoPct= licencas.total>0?Math.round(licencas.atribuidas/licencas.total*100):0;

  $('content').innerHTML=`
  <div class="grid-4 mb-16">
    ${statCard('Total de Ativos',   totais.ativos,      'ativos',       'blue',  `${pctAloc}% em uso`,    "navigateTo('ativos')")}
    ${statCard('Alocados',          totais.alocados,    'alocacoes',    'blue',  '',                       "navigateTo('alocacoes')")}
    ${statCard('Disponíveis',       totais.disponiveis, 'checkCircle',  'green', '',                       "navigateTo('ativos')")}
    ${statCard('Em Manutenção',     totais.manutencao,  'manutencao',   'amber', '',                       "navigateTo('manutencao')")}
    ${statCard('Colaboradores',     colaboradores?.ativos||0,'colaboradores','blue',`${colaboradores?.inativos||0} inativos`,"navigateTo('colaboradores')")}
    ${statCard(devPend>0?'Devoluções pendentes':'Devoluções OK', devPend>0?devPend:'—',
               'rotate', devPend>0?'amber':'green',
               devPend>0?`${devolucoes?.aguardandoLaudo||0} laudo · ${devolucoes?.aguardandoRH||0} aguard. RH`:'Nenhuma pendência',
               "navigateTo('alocacoes');setTimeout(()=>allocTab('devol'),400)")}
  </div>

  ${secDevPend}

  ${emprestimosVencidos.length>0?`
  <div class="card mb-16" style="border-left:3px solid var(--red)">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
      <div style="display:flex;align-items:center;gap:8px">
        ${svgIco('alocacoes','red')}
        <span style="font-size:14px;font-weight:700">Empréstimos com Devolução Vencida</span>
        <span style="display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:800;background:var(--red-bg);color:var(--red-text)">${emprestimosVencidos.length}</span>
      </div>
      <button class="btn btn-default btn-sm" onclick="navigateTo('alocacoes')">Ver Alocações</button>
    </div>
    <div class="table-wrap"><table>
      <thead><tr><th>Colaborador</th><th>Ativo</th><th>Devolução Prevista</th><th>Dias de Atraso</th></tr></thead>
      <tbody>${emprestimosVencidos.map(a=>{
        const dias = Math.floor((new Date()-new Date(a.dataDevolucaoPrevista))/(1000*60*60*24));
        return `<tr>
          <td style="font-weight:600">${esc(a.colaborador)}</td>
          <td style="font-size:12px;font-family:var(--mono)">${esc((a.ativoNome||'').split(' ')[0])}</td>
          <td style="font-size:12px;color:var(--red-text);font-weight:600">${esc(a.dataDevolucaoPrevista)}</td>
          <td><span style="display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:700;background:var(--red-bg);color:var(--red-text);border:1px solid var(--red-border)">${dias}d atraso</span></td>
        </tr>`;
      }).join('')}</tbody>
    </table></div>
  </div>`:''}

  <div class="grid-2 mb-16">
    <div class="card">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px">
        ${svgIco('alertas','red')}
        <span style="font-size:14px;font-weight:700">Alertas Ativos</span>
        ${alertas.length>0?`<span style="display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:800;background:var(--red-bg);color:var(--red-text)">${alertas.length}</span>`:''}
      </div>
      ${alertas.length===0
        ?`<div style="display:flex;align-items:center;gap:8px;color:var(--green-text);font-size:13px;padding:8px 0">
            ${svgIco('checkCircle','green')} Nenhum alerta no momento.
          </div>`
        :alertas.slice(0,8).map(a=>`<div class="alert-row">
            ${badge({garantia:'Garantia',estoque:'Estoque',licenca:'Licença'}[a.tipo]||a.tipo,a.nivel==='danger'?'red':'amber')}
            <span style="flex:1;font-size:13px">${esc(a.titulo)}</span>
            <span style="font-size:11px;color:var(--text3)">${esc(a.detalhe)}</span>
          </div>`).join('')}
      ${alertas.length>8?`<div style="text-align:center;margin-top:8px"><button class="btn btn-default btn-sm" onclick="navigateTo('alertas')">Ver todos (${alertas.length})</button></div>`:''}
    </div>

    <div class="card">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px">
        ${svgIco('chart','blue')}
        <span style="font-size:14px;font-weight:700">Distribuição por Categoria</span>
      </div>
      ${totais.ativos===0
        ?`<p style="font-size:13px;color:var(--text3)">Nenhum ativo cadastrado.</p>`
        :Object.entries(categorias).sort((a,b)=>b[1]-a[1]).map(([cat,cnt])=>{
          const pct=Math.round(cnt/totais.ativos*100);
          return `<div style="margin-bottom:10px">
            <div class="flex-between" style="font-size:13px;margin-bottom:4px">
              <span style="font-weight:500">${esc(cat)}</span>
              <span style="color:var(--text2);font-size:12px">${cnt} <span style="color:var(--text3)">(${pct}%)</span></span>
            </div>
            <div class="progress-wrap"><div class="progress-bar" style="width:${pct}%;background:var(--blue)"></div></div>
          </div>`;}).join('')}
      <hr class="divider" style="margin:14px 0 10px">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
        <div style="background:var(--bg3);border-radius:var(--r);padding:8px 10px">
          <div style="display:flex;align-items:center;gap:5px;margin-bottom:4px">
            ${svgIco('licencas',licUsoPct>90?'red':licUsoPct>70?'amber':'blue').replace('width:20px;height:20px','width:14px;height:14px')}
            <div style="font-size:10px;font-weight:700;color:var(--text3);text-transform:uppercase">Licenças</div>
          </div>
          <div style="font-size:14px;font-weight:700">${licencas.atribuidas}<span style="font-size:11px;font-weight:400;color:var(--text3)">/${licencas.total}</span></div>
          <div style="font-size:10px;color:var(--text3)">${licUsoPct}% utilizado</div>
          <div class="progress-wrap" style="margin-top:4px"><div class="progress-bar" style="width:${licUsoPct}%;background:var(--${licUsoPct>90?'red':licUsoPct>70?'amber':'green'})"></div></div>
        </div>
        <div style="background:var(--bg3);border-radius:var(--r);padding:8px 10px">
          <div style="display:flex;align-items:center;gap:5px;margin-bottom:4px">
            ${svgIco('chart','blue').replace('width:20px;height:20px','width:14px;height:14px')}
            <div style="font-size:10px;font-weight:700;color:var(--text3);text-transform:uppercase">Custo anual</div>
          </div>
          <div style="font-size:13px;font-weight:700;word-break:break-all">${fmtCur(licencas.custoAnual)}</div>
          <div style="font-size:10px;color:var(--text3)">em licenças</div>
        </div>
      </div>
    </div>
  </div>

  <div class="card">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
      <div style="display:flex;align-items:center;gap:8px">
        ${svgIco('alocacoes','blue')}
        <span style="font-size:14px;font-weight:700">Últimas Alocações</span>
      </div>
      <button class="btn btn-default btn-sm" onclick="navigateTo('alocacoes')">Ver todas</button>
    </div>
    <div class="table-wrap"><table>
      <thead><tr><th>Colaborador</th><th>Ativo</th><th>Setor</th><th>Data</th><th>Termo</th></tr></thead>
      <tbody>${ultimasAlocacoes.length===0
        ?`<tr><td colspan="5" style="text-align:center;color:var(--text3);padding:20px">Nenhuma alocação ainda.</td></tr>`
        :ultimasAlocacoes.map(a=>`<tr>
          <td style="font-weight:600">${esc(a.colaborador)}</td>
          <td class="mono" style="font-size:12px">${esc((a.ativoNome||'').split(' ')[0])}</td>
          <td style="font-size:12px;color:var(--text2)">${esc(a.setor)}</td>
          <td style="font-size:12px;color:var(--text2)">${fmtDate(a.dataAloc)}</td>
          <td>${badge(a.termoStatus)}</td></tr>`).join('')}
      </tbody>
    </table></div>
  </div>`;
}

