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
  $(`email-tpl-${kind}-subject`).value = tpl.subject;
  $(`email-tpl-${kind}-body`).value = tpl.body;
  $(`email-tpl-${kind}-button`).value = tpl.button_label;
  $(`email-tpl-${kind}-footer`).value = tpl.footer;
}

function getEmailTemplatePayload(kind){
  return {
    subject: $(`email-tpl-${kind}-subject`).value.trim(),
    body: $(`email-tpl-${kind}-body`).value.trim(),
    button_label: $(`email-tpl-${kind}-button`).value.trim(),
    footer: $(`email-tpl-${kind}-footer`).value.trim(),
  };
}

async function saveEmailTemplates(){
  try{
    await api('/settings/email/templates','PUT',{
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
