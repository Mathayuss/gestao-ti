async function saveEmailCfg(testAfter=false){
  const pw = $('email-password')?.value;
  const payload = {
    source:     'app',
    host:       $('email-host').value.trim(),
    port:       +$('email-port').value,
    tls:        $('email-tls').checked,
    user:       $('email-user').value.trim(),
    from_name:  $('email-from-name').value.trim(),
    from_email: $('email-from-email').value.trim(),
    enabled:    $('email-enabled').checked,
    clear_password: $('email-clear-password')?.checked || false,
  };
  if(pw) payload.password = pw;
  try{
    await api('/settings/email','PUT',payload);
    toast('Configurações de e-mail salvas');
    if(testAfter) await testEmailCfg();
    else renderConfiguracoes();
  }catch(e){ toast(e.message,'error'); }
}

async function testEmailCfg(){
  try{
    const email = $('email-test-to')?.value?.trim();
    const r = await api('/settings/email/test','POST',email?{email}:{});
    if(r.ok) toast('E-mail de teste enviado com sucesso!');
    else toast('Erro: '+(r.error||'falha no envio'),'error');
  }catch(e){ toast(e.message,'error'); }
}

const EMAIL_TEMPLATE_DEFAULTS = {
  pacote_termos: {
    subject: '[{empresa}] Termos aguardando sua assinatura',
    body: 'Olá, {colaborador}!\n\nVocê possui {quantidade} termo(s) para revisar e assinar: {termos}.\n\nAcesse a Central de Assinaturas pelo botão abaixo para visualizar cada documento e registrar sua assinatura.\n\nEste link expira em 7 dias. Em caso de dúvidas, contate o setor de TI.',
    button_label: 'Revisar e Assinar Termos',
    footer: '{empresa} - Sistema de Gestão de TI',
  },
  assinatura: {
    subject: '[{empresa}] Termo de Responsabilidade - assinatura necessária',
    body: 'Olá, {colaborador}!\n\nVocê recebeu o equipamento {ativo}.\n\nPara confirmar o recebimento, clique no botão abaixo e assine digitalmente o Termo de Responsabilidade.\n\nEste link expira em 7 dias. Em caso de dúvidas, contate o setor de TI.',
    button_label: 'Assinar Termo',
    footer: '{empresa} - Sistema de Gestão de TI',
  },
  devolucao: {
    subject: '[{empresa}] Termo de Devolução - assinatura necessária',
    body: 'Olá, {colaborador}!\n\nFoi registrada a devolução dos equipamentos sob sua responsabilidade.\n\nPor favor, acesse o link abaixo e assine o Termo de Devolução.\n\nEste link expira em 7 dias.',
    button_label: 'Assinar Devolução',
    footer: '{empresa} - Sistema de Gestão de TI',
  },
  laudo_rh: {
    subject: '[{empresa}] Laudo técnico aguardando sua ciência — {colaborador}',
    body: 'Olá!\n\nO técnico {tecnico} concluiu a avaliação dos equipamentos de {colaborador} no processo de desligamento.\n\nPor favor, acesse o link abaixo para visualizar o laudo e dar ciência. Não é necessário fazer login.\n\nEste link expira em 7 dias.',
    button_label: 'Ver Laudo e Dar Ciência',
    footer: '{empresa} - Sistema de Gestão de TI',
  },
  laudo_editado_rh: {
    subject: '[{empresa}] Laudo técnico corrigido — {colaborador}',
    body: 'Olá!\n\nO laudo técnico referente à devolução de equipamentos de {colaborador} foi corrigido pelo administrador {editor}.\n\nMotivo da correção: {motivo}\n\nAcesse o sistema para verificar as alterações.',
    button_label: 'Acessar o Sistema',
    footer: '{empresa} - Sistema de Gestão de TI',
  },
  laudo_editado_colab: {
    subject: '[{empresa}] Atualização no laudo técnico — devolução de equipamentos',
    body: 'Olá, {colaborador}!\n\nInformamos que o laudo técnico referente à devolução dos equipamentos sob sua responsabilidade foi atualizado.\n\nMotivo da correção: {motivo}\n\nEm caso de dúvidas, entre em contato com o setor de TI.',
    button_label: 'Acessar o Sistema',
    footer: '{empresa} - Sistema de Gestão de TI',
  },
};

function carregarTemplateEmailPadrao(kind){
  const tpl = EMAIL_TEMPLATE_DEFAULTS[kind];
  if(!tpl) return;
  if(!confirm('Isso substituirá o template atual pelo padrão. Deseja continuar?')) return;
  setEmailTemplateFields(kind, tpl);
  syncEmailTemplateCard(kind);
  toast('Template padrão carregado. Clique em Salvar Templates para gravar.');
}

function setEmailTemplateFields(kind, tpl){
  const values = {
    subject: tpl?.subject || '',
    body: tpl?.body || '',
    button: tpl?.button_label || '',
    footer: tpl?.footer || '',
  };
  ['subject','body','button','footer'].forEach(field=>{
    const store = $(`email-tpl-${kind}-${field}`);
    const edit = $(`email-edit-${kind}-${field}`);
    if(store) store.value = values[field];
    if(edit) edit.value = values[field];
  });
}

function emailTemplateExcerpt(text){
  const value = String(text || '').replace(/\s+/g,' ').trim();
  return value ? (value.length > 132 ? value.slice(0,132) + '...' : value) : 'Sem mensagem configurada.';
}

function getEmailTemplatePayload(kind){
  return {
    subject: ($(`email-tpl-${kind}-subject`)?.value || '').trim(),
    body: ($(`email-tpl-${kind}-body`)?.value || '').trim(),
    button_label: ($(`email-tpl-${kind}-button`)?.value || '').trim(),
    footer: ($(`email-tpl-${kind}-footer`)?.value || '').trim(),
  };
}

function syncEmailTemplateCard(kind){
  const payload = getEmailTemplatePayload(kind);
  const subject = $(`email-template-card-${kind}-subject`);
  const preview = $(`email-template-card-${kind}-preview`);
  const button = $(`email-template-card-${kind}-button`);
  if(subject){
    subject.textContent = payload.subject || 'Sem assunto configurado';
    subject.title = payload.subject || '';
  }
  if(preview) preview.textContent = emailTemplateExcerpt(payload.body);
  if(button) button.textContent = payload.button_label || 'Sem botão';
}

function getEmailTemplateCardMeta(kind){
  const card = $(`email-template-card-${kind}`);
  let variables = [];
  try{ variables = JSON.parse(card?.dataset?.templateVariables || '[]'); }
  catch(e){ variables = []; }
  return {
    title: card?.dataset?.templateTitle || 'Template de E-mail',
    subtitle: card?.dataset?.templateSubtitle || 'Personalize o texto enviado por e-mail.',
    variables,
  };
}

function loadEmailTemplateDefaultInEditor(kind){
  const tpl = EMAIL_TEMPLATE_DEFAULTS[kind];
  if(!tpl) return;
  if(!confirm('Isso substituirá os campos do editor pelo padrão. Deseja continuar?')) return;
  ['subject','body','button','footer'].forEach(field=>{
    const el = $(`email-edit-${kind}-${field}`);
    if(!el) return;
    el.value = field === 'button' ? tpl.button_label : tpl[field];
  });
}

function openEmailTemplateEditor(kind){
  const meta = getEmailTemplateCardMeta(kind);
  const payload = getEmailTemplatePayload(kind);
  const varsHtml = meta.variables.length
    ? meta.variables.map(v=>`<code>{${esc(v)}}</code>`).join(' ')
    : '<span style="color:var(--text3)">Nenhuma variável específica.</span>';
  openModal(`Editar E-mail — ${meta.title}`, `
    <div class="email-template-editor">
      <div class="email-template-editor-head">
        <div class="email-template-icon">${svgIcon('mail')}</div>
        <div style="min-width:0">
          <div class="email-template-title">${esc(meta.title)}</div>
          <div class="email-template-sub">${esc(meta.subtitle)}</div>
        </div>
      </div>
      <div class="info-box blue" style="margin:12px 0 14px;font-size:12px">
        Variáveis disponíveis: ${varsHtml}
      </div>
      <div class="email-template-modal-grid">
        <div class="form-group span-2"><label>Assunto</label>
          <input id="email-edit-${kind}-subject" value="${escAttr(payload.subject)}">
        </div>
        <div class="form-group span-2"><label>Mensagem</label>
          <textarea id="email-edit-${kind}-body" class="email-template-body-field">${esc(payload.body)}</textarea>
        </div>
        <div class="form-group"><label>Texto do botão</label>
          <input id="email-edit-${kind}-button" value="${escAttr(payload.button_label)}">
        </div>
        <div class="form-group"><label>Rodapé</label>
          <input id="email-edit-${kind}-footer" value="${escAttr(payload.footer)}">
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-default" type="button" onclick="closeModal()">Cancelar</button>
        <button class="btn btn-default" type="button" onclick="loadEmailTemplateDefaultInEditor('${kind}')">${inlineIcon('clipboard')} Carregar padrão</button>
        <button class="btn btn-primary" type="button" onclick="saveEmailTemplateEditor('${kind}')">${inlineIcon('save')} Salvar template</button>
      </div>
    </div>`, true);
}

async function saveEmailTemplateEditor(kind){
  setEmailTemplateFields(kind, {
    subject: ($(`email-edit-${kind}-subject`)?.value || '').trim(),
    body: ($(`email-edit-${kind}-body`)?.value || '').trim(),
    button_label: ($(`email-edit-${kind}-button`)?.value || '').trim(),
    footer: ($(`email-edit-${kind}-footer`)?.value || '').trim(),
  });
  syncEmailTemplateCard(kind);
  closeModal();
  await saveEmailTemplates();
}

async function saveEmailTemplates(){
  try{
    await api('/settings/email/templates','PUT',{
      pacote_termos: getEmailTemplatePayload('pacote_termos'),
      assinatura: getEmailTemplatePayload('assinatura'),
      devolucao: getEmailTemplatePayload('devolucao'),
      laudo_rh: getEmailTemplatePayload('laudo_rh'),
      laudo_editado_rh: getEmailTemplatePayload('laudo_editado_rh'),
      laudo_editado_colab: getEmailTemplatePayload('laudo_editado_colab'),
    });
    toast('Templates de e-mail salvos');
    renderConfiguracoes();
  }catch(e){ toast(e.message,'error'); }
}
