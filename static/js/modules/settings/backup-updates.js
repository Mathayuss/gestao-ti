function updateBackupScheduleFields(){
  const freqEl = $('backup-frequency');
  const weeklyEl = $('backup-weekly-day-group');
  const monthlyEl = $('backup-monthly-day-group');
  const freq = freqEl ? freqEl.value : 'daily';
  if(weeklyEl) weeklyEl.style.display = freq === 'weekly' ? 'block' : 'none';
  if(monthlyEl) monthlyEl.style.display = freq === 'monthly' ? 'block' : 'none';
}

async function saveBackupCfg(){
  const retention = Math.max(1, Math.min(90, Number($('backup-retention').value) || 7));
  const monthlyDay = Math.max(1, Math.min(31, Number($('backup-monthly-day')?.value) || 1));
  const weeklyDay = Math.max(0, Math.min(6, Number($('backup-weekly-day')?.value) || 0));
  try{
    await api('/settings/backup','PUT',{
      enabled: $('backup-enabled').checked,
      frequency: $('backup-frequency').value,
      schedule_time: $('backup-schedule-time').value || '02:00',
      weekly_day: weeklyDay,
      monthly_day: monthlyDay,
      retention,
      include_audit: $('backup-include-audit').checked,
    });
    toast('Configuração de backup salva');
    renderConfiguracoes();
  }catch(e){ toast(e.message,'error'); }
}

async function runBackupNow(){
  try{
    const r = await api('/backups/run','POST',{});
    toast('Backup gerado: ' + r.filename);
    renderConfiguracoes();
  }catch(e){ toast(e.message,'error'); }
}

async function checkSystemUpdate(){
  try{
    toast('Verificando atualizações...');
    const r = await api('/system/update/status?fetch=1');
    window.TICONTROL_LAST_UPDATE_STATE = r;
    if(r.updateAvailable) toast('Atualização disponível','warning');
    else toast(r.message || 'Nenhuma atualização pendente');
    _cfgTab = 'updates';
    renderConfiguracoes();
  }catch(e){ toast(e.message,'error'); }
}

function confirmApplySystemUpdate(){
  openModal('Confirmar Atualização',`
    <div class="info-box amber" style="margin-bottom:14px;font-size:13px">
      O sistema irá gerar um backup lógico e aplicar a atualização disponível no repositório. Depois disso, reinicie/recrie a aplicação para carregar o novo código.
    </div>
    <div style="font-size:13px;color:var(--text2);line-height:1.5">
      Esta ação não é automática: ela só começa quando você confirmar abaixo.
    </div>
    <div class="modal-footer">
      <button class="btn btn-default" onclick="closeModal()">Cancelar</button>
      <button class="btn btn-primary" onclick="applySystemUpdate()">Aplicar atualização</button>
    </div>`);
}

function showManualUpdateInstructions(){
  openModal('Atualização Manual',`
    <div class="info-box blue" style="margin-bottom:14px;font-size:13px">
      Neste ambiente a aplicação não tem acesso direto ao repositório do servidor. A atualização continua sendo uma escolha manual do administrador.
    </div>
    <div style="font-size:13px;color:var(--text2);line-height:1.55;margin-bottom:10px">
      Execute um dos comandos abaixo no servidor onde o sistema está instalado:
    </div>
    <pre style="white-space:pre-wrap;background:var(--bg3);border:1px solid var(--border);border-radius:var(--r);padding:10px;font-size:12px;margin:0 0 12px;overflow:auto">Windows:
.\\scripts\\update-windows.ps1

Linux:
./scripts/update-linux.sh</pre>
    <div style="font-size:12px;color:var(--text3);line-height:1.5">
      O script gera backup antes da troca, atualiza o código, reconstrói a aplicação e valida o serviço.
    </div>
    <div class="modal-footer"><button class="btn btn-default" onclick="closeModal()">Fechar</button></div>`);
}

async function applySystemUpdate(){
  $('modal-title').textContent = 'Aplicando Atualização...';
  $('modal-body').innerHTML = `
    <div style="text-align:center;padding:28px 0 20px">
      <div class="spinner" style="margin-bottom:18px"></div>
      <div style="font-size:14px;font-weight:600;color:var(--text);margin-bottom:6px">Aplicando atualização...</div>
      <div style="font-size:12px;color:var(--text3);line-height:1.6">
        Gerando backup e aplicando código do repositório.<br>Aguarde, isso pode levar alguns segundos.
      </div>
    </div>`;
  try{
    const r = await api('/system/update/apply','POST',{});
    toast(r.message || 'Atualização aplicada');
    openModal('Atualização Aplicada',`
      <div class="info-box blue" style="margin-bottom:12px">
        Backup gerado: <strong>${esc(r.backup?.filename || 'backup criado')}</strong>
      </div>
      <div style="font-size:13px;color:var(--text2);line-height:1.5">
        Nova versão: <strong>${esc(r.newVersion || '?')}</strong><br>
        ${r.restartScheduled ? 'A aplicação será reiniciada automaticamente em instantes.' : 'Reinicie/recrie a aplicação para carregar o novo código.'}
      </div>
      ${r.output?`<pre style="white-space:pre-wrap;background:var(--bg3);border:1px solid var(--border);border-radius:var(--r);padding:10px;font-size:11px;margin-top:12px;max-height:180px;overflow:auto">${esc(r.output)}</pre>`:''}
      <div class="modal-footer"><button class="btn btn-default" onclick="closeModal();renderConfiguracoes()">Fechar</button></div>`);
  }catch(e){ closeModal(); toast(e.message,'error'); }
}

async function deleteBackupFile(filename){
  if(_pendingDeleteBackup !== filename){
    _pendingDeleteBackup = filename;
    setTimeout(()=>{ if(_pendingDeleteBackup===filename) _pendingDeleteBackup=null; }, 4000);
    toast('Clique novamente para confirmar a exclusão do backup.','warning');
    return;
  }
  _pendingDeleteBackup = null;
  try{
    await api('/backups/files/' + encodeURIComponent(filename), 'DELETE');
    toast('Backup excluído');
    renderConfiguracoes();
  }catch(e){ toast(e.message,'error'); }
}

let _pendingRestoreAction = null;
function _buildValidationModalHtml(r, source){
  const valid = r.valid !== false;
  const summaryRows = Object.entries(r.summary||{}).map(([k,v])=>
    `<tr><td style="padding:3px 10px 3px 0;color:var(--text2);font-size:12px">${esc(k)}</td><td style="font-weight:700;font-size:12px">${v}</td></tr>`
  ).join('');
  const errHtml = (r.errors||[]).length ? `<div style="margin-top:10px"><b style="font-size:12px">Erros:</b><ul style="margin:4px 0 0 16px;font-size:12px">${(r.errors||[]).map(e=>`<li style="color:var(--red-text)">${esc(e)}</li>`).join('')}</ul></div>` : '';
  const warnHtml = (r.warnings||[]).length ? `<div style="margin-top:10px"><b style="font-size:12px">Avisos:</b><ul style="margin:4px 0 0 16px;font-size:12px">${(r.warnings||[]).map(w=>`<li style="color:var(--amber-text,#92400e)">${esc(w)}</li>`).join('')}</ul></div>` : '';
  const sha = r.sha256 ? `<div><b>SHA-256:</b> <span class="mono" style="font-size:10px">${esc(r.sha256.slice(0,20))}…</span></div>` : '';
  return `
    <div style="margin-bottom:12px;display:flex;gap:10px;align-items:center">
      <span style="font-weight:700">Status:</span>${badge(valid?'VÁLIDO':'INVÁLIDO',valid?'green':'red')}
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:12px;font-size:12px">
      <div><b>Arquivo:</b> ${esc(source)}</div>
      <div><b>Gerado em:</b> ${esc(r.geradoEm||'?')}</div>
      <div><b>Gerado por:</b> ${esc(r.geradoPor||'?')}</div>
      <div><b>Versão:</b> ${esc(r.versao||'?')}</div>
      ${sha}
    </div>
    <details open><summary style="cursor:pointer;font-weight:700;font-size:13px;margin-bottom:6px">Registros</summary>
      <table style="width:100%">${summaryRows}</table>
    </details>
    ${errHtml}${warnHtml}`;
}

async function validateBackupFile(filename){
  try{
    const r = await api('/backups/validate','POST',{filename});
    if(!r) return;
    openModal('Validação de Backup', _buildValidationModalHtml(r, filename)+`
      <div class="modal-footer"><button class="btn btn-default" onclick="closeModal()">Fechar</button></div>`);
  }catch(e){ toast(e.message,'error'); }
}

async function validateBackupUpload(){
  const fi = document.getElementById('backup-restore-file');
  if(!fi||!fi.files[0]){ toast('Selecione um arquivo JSON de backup.','warning'); return; }
  const fd = new FormData(); fd.append('file', fi.files[0]);
  try{
    const r = await api('/backups/validate','POST',fd);
    if(!r) return;
    openModal('Validação de Backup', _buildValidationModalHtml(r, fi.files[0].name)+`
      <div class="modal-footer"><button class="btn btn-default" onclick="closeModal()">Fechar</button></div>`);
  }catch(e){ toast(e.message,'error'); }
}

function _showRestoreConfirmModal(r, source, onConfirm){
  _pendingRestoreAction = onConfirm;
  const summaryRows = Object.entries(r.summary||{}).map(([k,v])=>
    `<tr><td style="padding:3px 10px 3px 0;color:var(--text2);font-size:12px">${esc(k)}</td><td style="font-weight:700;font-size:12px">${v}</td></tr>`
  ).join('');
  const warnHtml = (r.warnings||[]).length ? `<div class="info-box" style="margin-top:10px;background:var(--amber-bg,#fef3c7);border-left-color:var(--amber-text,#92400e)"><b style="font-size:12px">Avisos:</b><ul style="margin:4px 0 0 16px;font-size:12px">${(r.warnings||[]).map(w=>`<li>${esc(w)}</li>`).join('')}</ul></div>` : '';
  openModal('Confirmar Restauração', `
    <div class="info-box red" style="margin-bottom:14px;font-size:13px">
      <b>Atenção:</b> Esta operação irá <b>apagar todos os dados atuais</b> e restaurar a partir do backup selecionado. Um backup automático será gerado antes.
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:12px;font-size:12px">
      <div><b>Arquivo:</b> ${esc(source)}</div>
      <div><b>Gerado em:</b> ${esc(r.geradoEm||'?')}</div>
      <div><b>Gerado por:</b> ${esc(r.geradoPor||'?')}</div>
      <div><b>Versão:</b> ${esc(r.versao||'?')}</div>
    </div>
    <details><summary style="cursor:pointer;font-weight:700;font-size:13px;margin-bottom:6px">Registros a restaurar</summary>
      <table style="width:100%">${summaryRows}</table>
    </details>
    ${warnHtml}
    <div class="modal-footer">
      <button class="btn btn-default" onclick="closeModal()">Cancelar</button>
      <button class="btn btn-danger" onclick="_pendingRestoreAction && _pendingRestoreAction()">Confirmar Restauração</button>
    </div>`);
}

async function confirmRestoreBackupFile(filename){
  try{
    const r = await api('/backups/validate','POST',{filename});
    if(!r) return;
    if(!r.valid){ toast('Backup inválido: '+(r.errors||[])[0],'error'); return; }
    _showRestoreConfirmModal(r, filename, async ()=>{
      closeModal();
      try{
        const res = await api('/backups/restore/'+encodeURIComponent(filename),'POST',{});
        if(!res) return;
        toast('Restauração concluída! '+Object.entries(res.stats||{}).map(([k,v])=>k+':'+v).join(', '));
        renderConfiguracoes();
      }catch(e){ toast(e.message,'error'); }
    });
  }catch(e){ toast(e.message,'error'); }
}

async function confirmRestoreBackupUpload(){
  const fi = document.getElementById('backup-restore-file');
  if(!fi||!fi.files[0]){ toast('Selecione um arquivo JSON de backup.','warning'); return; }
  const file = fi.files[0];
  const fdV = new FormData(); fdV.append('file', file);
  try{
    const r = await api('/backups/validate','POST',fdV);
    if(!r) return;
    if(!r.valid){ toast('Backup inválido: '+(r.errors||[])[0],'error'); return; }
    _showRestoreConfirmModal(r, file.name, async ()=>{
      closeModal();
      const fdR = new FormData(); fdR.append('file', file);
      try{
        const res = await api('/backups/restore','POST',fdR);
        if(!res) return;
        toast('Restauração concluída! '+Object.entries(res.stats||{}).map(([k,v])=>k+':'+v).join(', '));
        renderConfiguracoes();
      }catch(e){ toast(e.message,'error'); }
    });
  }catch(e){ toast(e.message,'error'); }
}
