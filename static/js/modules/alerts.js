// ══════════════════════════════════════════════════════════════════════════
// ALERTAS
// ══════════════════════════════════════════════════════════════════════════
async function renderAlertas(){
  const alerts = await api('/alerts');
  if(!alerts) return;
  const groups = {
    garantia: alerts.filter(a=>a.tipo==='garantia'),
    estoque: alerts.filter(a=>a.tipo==='estoque'),
    licenca: alerts.filter(a=>a.tipo==='licenca'),
  };
  const alertRow = a=>`<tr>
    <td>${badge({garantia:'Garantia',estoque:'Estoque',licenca:'Licença'}[a.tipo]||a.tipo,a.nivel==='danger'?'red':'amber')}</td>
    <td style="font-weight:600">${esc(a.titulo||'')}</td>
    <td style="font-size:12px;color:var(--text2)">${esc(a.detalhe||'')}</td>
    <td class="mono" style="font-size:11px;color:var(--text3)">${esc(a.ref||'')}</td>
  </tr>`;
  const sec=(title,arr)=>`<div class="card mb-16">
    <div class="section-title">${title} ${badge(arr.length,arr.length>0?'red':'green')}</div>
    ${arr.length===0?'<p style="color:var(--text3);font-size:13px">Sem alertas nesta categoria.</p>':`
      <div class="table-wrap"><table>
        <thead><tr><th>Tipo</th><th>Alerta</th><th>Detalhe</th><th>Referência</th></tr></thead>
        <tbody>${arr.map(alertRow).join('')}</tbody>
      </table></div>`}
  </div>`;
  $('content').innerHTML =
    sec('Garantias Vencendo', groups.garantia) +
    sec('Estoque Mínimo Atingido', groups.estoque) +
    sec('Licenças', groups.licenca);
}

