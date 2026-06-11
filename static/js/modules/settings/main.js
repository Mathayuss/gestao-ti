// ══════════════════════════════════════════════════════════════════════════
// CONFIGURAÇÕES
// ══════════════════════════════════════════════════════════════════════════

async function renderConfiguracoes(){
  const [cfg, perfis, sysUsers] = await Promise.all([api('/settings'), api('/system-users/perfis'), api('/system-users')]);
  let backupState = {config: cfg.backup || {}, files: []};
  let updateState = null;
  try{
    backupState = await api('/backups');
  }catch(e){
    backupState = {config: cfg.backup || {}, files: []};
  }
  try{
    updateState = await api('/system/update/status');
  }catch(e){
    updateState = {supported:false, message:'Não foi possível consultar atualização.', currentVersion:APP_VERSION};
  }
  PERFIS_SYS = Object.keys(perfis);
  _settings.categorias = cfg.categorias || [];
  _settings.categorias_insumos = cfg.categorias_insumos || [];
  _settings.categorias_compat = cfg.categorias_compat || {};
  _settings.termos_avulsos_tipos = cfg.termos_avulsos_tipos || ['VPN','BYOD','Confidencialidade','Outro'];
  _settings.termos_avulsos_modelos = cfg.termos_avulsos_modelos || {};
  _termoAvulsoTipos = [..._settings.termos_avulsos_tipos];
  _termoAvulsoModelos = {..._settings.termos_avulsos_modelos};
  const {empresa, setores, unidades, alertas, regras_usuario, campos_ativo_obrigatorios} = cfg;
  const cfg_cats   = cfg.categorias_config    || {};
  const cfg_email  = cfg.email                || {};
  const cfg_tpl    = cfg.email_templates      || {};
  const cfg_tr     = cfg.termo_recebimento    || {};
  const cfg_td     = cfg.termo_devolucao      || {};
  const cfg_te     = cfg.termo_emprestimo     || {};
  const cfg_tv     = cfg.termo_vpn            || {};
  const cfg_backup = backupState.config || cfg.backup || {};
  const cfg_ap     = cfg.aparencia            || {};
  const cfg_pat_prefixo = cfg.patrimonio_prefixo || 'TI';
  const cfg_public_url  = cfg.app_base_url_saved || '';
  const backupFiles = Array.isArray(backupState.files) ? backupState.files : [];
  const backupFreqLabel = {daily:'Diário', weekly:'Semanal', monthly:'Mensal'};
  const backupWeekdayLabel = ['Domingo','Segunda-feira','Terça-feira','Quarta-feira','Quinta-feira','Sexta-feira','Sábado'];
  const backupScheduleTime = cfg_backup.schedule_time || '02:00';
  const backupWeeklyDay = Number.isFinite(Number(cfg_backup.weekly_day)) ? Number(cfg_backup.weekly_day) : 1;
  const backupMonthlyDay = Math.max(1, Math.min(31, Number(cfg_backup.monthly_day) || 1));
  const backupScheduleLabel = cfg_backup.frequency === 'weekly'
    ? `${backupWeekdayLabel[backupWeeklyDay] || 'Segunda-feira'} às ${backupScheduleTime}`
    : (cfg_backup.frequency === 'monthly'
      ? `Dia ${backupMonthlyDay} às ${backupScheduleTime}`
      : `Todos os dias às ${backupScheduleTime}`);
  const updateBadge = updateState.supported
    ? (updateState.updateAvailable ? badge('Disponível','amber') : badge('OK','green'))
    : badge('Manual','blue');
  const updateApplyHint = updateState.supported
    ? (updateState.canApply ? 'Atualização pronta para aplicar.' : (updateState.blockReason || (updateState.updateAvailable ? 'Verifique os bloqueios antes de aplicar.' : 'Nenhuma atualização disponível.')))
    : 'Atualização automática indisponível neste ambiente.';
  const updateDetails = updateState.supported
    ? `${esc(updateState.branch||'branch')} · ${esc(updateState.currentCommit||updateState.currentVersion||'?')} · atrás ${updateState.behind||0} · à frente ${updateState.ahead||0}`
    : `Execute no servidor: <span class="mono">${esc(updateState.manualCommand || './scripts/update-linux.sh')}</span>`;
  const tplAss = cfg_tpl.assinatura || {};
  const tplDev = cfg_tpl.devolucao || {};
  const emailTemplateCard = (kind,title,subtitle,variables,tpl) => `
    <div class="card" style="margin-top:16px">
      <div class="flex-between" style="margin-bottom:12px;gap:12px;align-items:flex-start;flex-wrap:wrap">
        <div>
          <div class="section-title" style="margin-bottom:4px">${title}</div>
          <div style="font-size:12px;color:var(--text3)">${subtitle}</div>
        </div>
        <button class="btn btn-default btn-sm" onclick="carregarTemplateEmailPadrao('${kind}')" type="button">Carregar padrão</button>
      </div>
      <div class="info-box blue" style="margin-bottom:14px;font-size:12px">
        Variáveis: ${variables.map(v=>`<code>{${v}}</code>`).join(' ')}
      </div>
      <div class="form-grid-2">
        <div class="form-group" style="grid-column:span 2"><label>Assunto</label>
          <input id="email-tpl-${kind}-subject" value="${escAttr(tpl.subject||'')}">
        </div>
        <div class="form-group" style="grid-column:span 2"><label>Mensagem</label>
          <textarea id="email-tpl-${kind}-body" style="min-height:150px;resize:vertical">${esc(tpl.body||'')}</textarea>
        </div>
        <div class="form-group"><label>Texto do botão</label>
          <input id="email-tpl-${kind}-button" value="${escAttr(tpl.button_label||'')}">
        </div>
        <div class="form-group"><label>Rodapé</label>
          <input id="email-tpl-${kind}-footer" value="${escAttr(tpl.footer||'')}">
        </div>
      </div>
    </div>`;
  const backupStatusBadge = cfg_backup.last_error ? badge('Erro','red') : (cfg_backup.last_run ? badge('OK','green') : badge('Pendente','gray'));
  const backupFilesHtml = backupFiles.length ? backupFiles.map(f=>`
    <div class="alert-row" style="padding:10px 0;gap:10px;align-items:flex-start">
      <div style="flex:1;min-width:180px">
        <div style="font-size:13px;font-weight:700;color:var(--text)">${esc(f.filename)}</div>
        <div style="font-size:11px;color:var(--text3);margin-top:2px">
          ${fmtBytes(f.size)} · ${fmtDateTime(f.createdAt || f.modified)}
        </div>
        <div class="mono" style="font-size:10px;color:var(--text3);margin-top:4px;word-break:break-all">${esc(f.sha256)}</div>
      </div>
      <div class="flex-gap" style="flex-wrap:wrap;justify-content:flex-end">
        <button class="btn btn-default btn-sm" onclick="validateBackupFile('${escAttr(f.filename)}')" type="button">Validar</button>
        <a class="btn btn-default btn-sm" href="/api/backups/files/${encodeURIComponent(f.filename)}" download>Baixar</a>
        <button class="btn btn-warning btn-sm" onclick="confirmRestoreBackupFile('${escAttr(f.filename)}')" type="button">Restaurar</button>
        <button class="btn btn-danger btn-sm" onclick="deleteBackupFile('${escAttr(f.filename)}')" type="button">Excluir</button>
      </div>
    </div>`).join('') : `<div style="font-size:12px;color:var(--text3);padding:10px 0">Nenhum backup armazenado pela aplicação ainda.</div>`;
  const perfilCards = Object.entries(perfis).map(([p,info])=>`
  <div class="card" style="border-top:3px solid var(--${info.cor}-text)">
    <div class="flex-between" style="margin-bottom:8px">
      <span style="font-weight:700;font-size:14px">${p}</span>
      <div class="flex-gap">
        ${badge(sysUsers.filter(u=>u.perfil===p&&u.status==='Ativo').length+' usuário(s)','gray')}
        <button class="btn btn-default btn-icon btn-sm" onclick='editPerfilPerms(${JSON.stringify(p)},${JSON.stringify(info)})' title="Editar permissões">Editar</button>
      </div>
    </div>
    <div style="font-size:12px;color:var(--text2);margin-bottom:10px">${esc(info.label)}</div>
    <div class="perm-grid">
      ${['pode_editar','pode_excluir','pode_exportar'].map(k=>`
      <div class="perm-item ${info[k]?'on':'off'}">${info[k]?'OK':'x'} ${k.replace('pode_','').replace('_',' ')}</div>`).join('')}
    </div>
    <div style="font-size:11px;font-weight:600;color:var(--text2);margin-bottom:6px">MÓDULOS LIBERADOS:</div>
    <div style="display:flex;flex-wrap:wrap;gap:4px">
      ${info.modulos.map(m=>`<span class="badge badge-${info.cor}" style="font-size:10px">${MODULO_LABEL[m]||m}</span>`).join('')}
    </div>
  </div>`).join('');

  // tab bar
  const CFG_TABS_DEF = [
    ['geral',     'Geral'],
    ['operacao',  'Operação'],
    ['aparencia', 'Aparência'],
    ['perfis',    'Perfis'],
    ['email',     'E-mail'],
    ['termos',    'Termos'],
    ['backup',    'Backup'],
    ['updates',   'Atualizações'],
  ];
  const tabBar = `<div class="cfg-tab-bar" style="display:flex;gap:0;margin-bottom:20px;border-bottom:2px solid var(--border);overflow-x:auto">
    ${CFG_TABS_DEF.map(([id,label])=>`<button id="cfg-tab-${id}" onclick="cfgTab('${id}')"
      style="padding:9px 20px;font-size:13px;font-weight:600;border:none;background:none;cursor:pointer;white-space:nowrap;border-bottom:2px solid transparent;margin-bottom:-2px;color:var(--text2)">${label}</button>`).join('')}
  </div>`;

  // ── painéis ──────────────────────────────────────────────────────────────
  const panelGeral = `<div id="cfg-panel-geral" style="display:none;grid-template-columns:1fr 1fr;gap:16px">
    <div class="card" style="grid-column:span 2">
      <div class="section-title">Dados da Empresa</div>
      <div class="form-grid-2">
        ${[['Nome da Empresa','cfg-emp-nome',empresa.nome],['CNPJ','cfg-emp-cnpj',empresa.cnpj],
           ['E-mail TI','cfg-emp-email',empresa.email],['Telefone','cfg-emp-tel',empresa.telefone],
           ['Site','cfg-emp-site',empresa.site],['Endereço','cfg-emp-end',empresa.endereco]].map(([l,id,v])=>`
        <div class="form-group"><label>${l}</label><input id="${id}" value="${esc(v)}"></div>`).join('')}
        <div class="form-group" style="grid-column:span 2">
          <label>Logo da Empresa</label>
          <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:8px">
            ${empresa.logo_base64
              ? `<div style="padding:6px 10px;background:#fff;border:1px solid var(--border);border-radius:var(--r);display:inline-flex;align-items:center;gap:8px">
                   <img id="logo-current" src="${empresa.logo_base64}" style="height:28px;object-fit:contain;max-width:120px">
                 </div>
                 <button class="btn btn-danger btn-sm" onclick="removeLogo()" type="button">Remover logo</button>`
              : `<span style="font-size:12px;color:var(--text3)">Nenhum logo cadastrado</span>`}
          </div>
          <input type="file" id="cfg-emp-logo" accept="image/png,image/jpeg,image/svg+xml,image/webp" onchange="previewLogoUpload(this)">
          <div class="hint">PNG, JPG ou SVG · Fundo transparente recomendado · Máx 4 MB</div>
          <div id="logo-upload-preview" style="margin-top:8px"></div>
        </div>
      </div>
      <div class="modal-footer" style="padding-top:10px;margin-top:0;border-top:none;justify-content:flex-start">
        <button class="btn btn-primary" onclick="saveEmpresa()">Salvar Empresa</button>
      </div>
      <hr class="divider">
      <div class="section-title" style="margin-top:4px">Numeração de Patrimônio</div>
      <div style="display:flex;align-items:flex-end;gap:12px">
        <div class="form-group" style="margin-bottom:0;min-width:120px">
          <label>Prefixo</label>
          <input id="cfg-pat-prefixo" value="${esc(cfg_pat_prefixo)}" placeholder="TI" maxlength="10" style="text-transform:uppercase;width:100px">
        </div>
        <div style="padding:10px 14px;background:var(--blue-bg);border-radius:var(--r);border:1px solid var(--blue-border);font-size:13px;font-weight:700;color:var(--blue);font-family:var(--mono)">
          ${esc(cfg_pat_prefixo)}-000001
        </div>
        <button class="btn btn-primary btn-sm" onclick="savePrefixoPatrimonio()">Salvar Prefixo</button>
      </div>
      <div style="font-size:11px;color:var(--text3);margin-top:8px">O número é gerado automaticamente a cada entrada de ativo. Ex: <strong>${esc(cfg_pat_prefixo)}-000001</strong>, <strong>${esc(cfg_pat_prefixo)}-000002</strong>, ...</div>
    </div>
    <div class="card">
      <div class="section-title" style="margin-bottom:12px">URL Pública da Aplicação</div>
      <div style="font-size:12px;color:var(--text2);margin-bottom:12px;line-height:1.6">
        Usada em <strong>links de e-mail</strong> (assinatura, devolução, laudos) e contextos sem requisição HTTP ativa.<br>
        Links gerados no navegador já usam automaticamente a URL de acesso atual —
        configure esta apenas se os destinatários dos e-mails precisam de um endereço específico (IP fixo, domínio público).
      </div>
      <div style="display:flex;align-items:flex-end;gap:8px;flex-wrap:wrap">
        <div class="form-group" style="margin-bottom:0;flex:1;min-width:220px">
          <label>URL (ex: http://10.0.0.10:5000 ou https://ti.empresa.com.br)</label>
          <input id="cfg-public-url" value="${esc(cfg_public_url)}"
                 placeholder="Detectada automaticamente da requisição atual"
                 style="width:100%;font-family:var(--mono);font-size:12px">
        </div>
        <button class="btn btn-default btn-sm" style="white-space:nowrap;height:36px"
                onclick="document.getElementById('cfg-public-url').value = window.location.origin"
                type="button">Usar URL atual</button>
        <button class="btn btn-primary btn-sm" style="height:36px"
                onclick="savePublicUrl()" type="button">Salvar</button>
      </div>
      <div id="public-url-status" style="margin-top:8px;font-size:12px"></div>
      <div style="font-size:11px;color:var(--text3);margin-top:8px">
        URL atual da sessão: <strong class="mono" style="color:var(--blue)">${esc(window.location.origin||'')}</strong>
        — se igual à URL pública configurada, links de e-mail e navegador serão idênticos.
      </div>
    </div>
    <div class="card">
      <div class="flex-between" style="margin-bottom:12px">
        <div class="section-title" style="margin-bottom:0">Setores</div>
        <div class="flex-gap">
          <input id="novo-setor" placeholder="Novo setor..." style="width:140px">
          <button class="btn btn-primary btn-sm" onclick="addSetor()">Adicionar</button>
        </div>
      </div>
      <div id="setores-list">
        ${setores.map(s=>`
        <div class="alert-row" style="padding:6px 0">
          <span style="flex:1;font-size:13px">${esc(s)}</span>
          <button class="btn btn-danger btn-sm btn-icon" onclick="delSetor('${esc(s)}')">x</button>
        </div>`).join('')}
      </div>
    </div>
    <div class="card">
      <div class="flex-between" style="margin-bottom:12px">
        <div class="section-title" style="margin-bottom:0">Unidades / Locais</div>
        <button class="btn btn-primary btn-sm" onclick="openNewUnidade()">Novo</button>
      </div>
      <div id="unidades-list">
        ${unidades.map(u=>`
        <div class="alert-row" style="padding:6px 0">
          <div style="flex:1">
            <div style="font-size:13px;font-weight:600">${esc(u.nome)}</div>
            <div style="font-size:11px;color:var(--text3)">${esc(u.cidade)} — ${esc(u.estado)} · ${badge(u.tipo,'gray')}</div>
          </div>
          <button class="btn btn-default btn-icon btn-sm" onclick="editUnidade(${JSON.stringify(u).replace(/"/g,'&quot;')})">Editar</button>
          <button class="btn btn-danger btn-sm btn-icon" onclick="delUnidade('${u.id}')">x</button>
        </div>`).join('')}
      </div>
    </div>
  </div>`;

  const panelOperacao = `<div id="cfg-panel-operacao" style="display:none;grid-template-columns:1fr 1fr;gap:16px">
    <div class="card">
      <div class="section-title">Configurações de Alertas</div>
      <div class="form-group"><label>Dias de antecedência — Garantia</label>
        <input id="cfg-al-gar" type="number" value="${alertas.dias_garantia}" min="1" max="365">
      </div>
      <div class="form-group"><label>Dias de antecedência — Licença</label>
        <input id="cfg-al-lic" type="number" value="${alertas.dias_licenca}" min="1" max="365">
      </div>
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
        <input type="checkbox" id="cfg-al-esq" ${alertas.estoque_minimo?'checked':''} style="width:auto">
        <label for="cfg-al-esq" style="margin:0">Alertar quando estoque atingir mínimo</label>
      </div>
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px">
        <input type="checkbox" id="cfg-al-email" ${alertas.notif_email?'checked':''} style="width:auto">
        <label for="cfg-al-email" style="margin:0">Notificações por e-mail (requer config. SMTP)</label>
      </div>
      <button class="btn btn-primary btn-sm" onclick="saveAlertas()">Salvar Alertas</button>
    </div>
    <div class="card">
      <div class="section-title">Regras de Operação</div>
      <div style="display:flex;flex-direction:column;gap:10px;margin-bottom:16px">
        ${[
          ['cfg-r-termo','exige_termo_alocacao','Exigir termo ao alocar ativo'],
          ['cfg-r-email','permite_alocar_sem_email','Permitir alocação sem e-mail do colaborador'],
          ['cfg-r-vinculo','obriga_vinculo_saida','Obrigar vínculo em saídas de periférico'],
        ].map(([id,key,label])=>`
        <div style="display:flex;align-items:center;gap:10px">
          <input type="checkbox" id="${id}" ${regras_usuario[key]?'checked':''} style="width:auto">
          <label for="${id}" style="margin:0;font-size:13px">${label}</label>
        </div>`).join('')}
        <div class="form-group" style="margin-top:4px"><label>Máximo de periféricos por colaborador</label>
          <input id="cfg-r-maxp" type="number" value="${regras_usuario.max_perifericos_por_colab}" min="1" max="50">
        </div>
      </div>
      <button class="btn btn-primary btn-sm" onclick="saveRegras()">Salvar Regras</button>
    </div>
    <div class="card" style="grid-column:span 2">
      <div class="flex-between" style="margin-bottom:14px">
        <div>
          <div class="section-title" style="margin-bottom:4px">Categorias de Ativos</div>
          <div style="font-size:12px;color:var(--text2)">Gerencie as categorias disponíveis e defina o tipo de alocação de cada uma</div>
        </div>
        <div class="flex-gap">
          <input id="nova-cat" placeholder="Nova categoria..." style="width:180px" onkeydown="if(event.key==='Enter')addCategoria()">
          <button class="btn btn-primary btn-sm" onclick="addCategoria()">Adicionar</button>
        </div>
      </div>
      <div id="cats-config-list">
        ${_buildCatsConfigHtml(getAssetCats(), cfg_cats)}
      </div>
      <div class="info-box blue" style="margin-top:12px;font-size:12px">
        Categorias do tipo <strong>Unidade</strong> não exibem campo Colaborador no formulário de ativo — apenas Responsável Técnico (opcional) e Unidade.
      </div>
    </div>
    <div class="card" style="grid-column:span 2">
      <div class="flex-between" style="margin-bottom:14px">
        <div>
          <div class="section-title" style="margin-bottom:4px">Categorias de Insumos / Periféricos</div>
          <div style="font-size:12px;color:var(--text2)">Categorias disponíveis nos formulários de insumos e periféricos</div>
        </div>
        <div class="flex-gap">
          <input id="nova-cat-ins" placeholder="Nova categoria..." style="width:180px" onkeydown="if(event.key==='Enter')addCategoriaInsumo()">
          <button class="btn btn-primary btn-sm" onclick="addCategoriaInsumo()">Adicionar</button>
        </div>
      </div>
      <div id="cats-insumos-list">
        ${_buildCatsInsumoHtml(_settings.categorias_insumos && _settings.categorias_insumos.length ? _settings.categorias_insumos : cfg.categorias_insumos || [])}
      </div>
    </div>
    <div class="card" style="grid-column:span 2">
      <div class="compat-panel-head">
        <div>
          <div class="section-title" style="margin-bottom:4px">Compatibilidade — Ativo × Insumo</div>
          <div class="compat-panel-copy">Marque apenas as restrições necessárias. Sem seleção = todos os insumos liberados.</div>
        </div>
        <button class="btn btn-primary btn-sm" onclick="saveCompatConfig()">Salvar Compatibilidade</button>
      </div>
      <div id="compat-matrix">
        ${_buildCompatMatrix(getAssetCats(), getSupplyCats(), cfg.categorias_compat || {})}
      </div>
    </div>
  </div>`;

  const panelAparencia = `<div id="cfg-panel-aparencia" style="display:none">
    <div class="card">
      <div class="section-title">Identidade do Sistema</div>
      <div class="form-grid-2">
        <div class="form-group"><label>Nome do Sistema</label>
          <input id="ap-nome" value="${esc(cfg_ap.nome_sistema||'')}" placeholder="Ex: TI Control">
        </div>
        <div class="form-group"><label>Slogan / Subtítulo</label>
          <input id="ap-slogan" value="${esc(cfg_ap.slogan_sistema||'')}" placeholder="Ex: Gestão de Ativos de TI">
        </div>
        <div class="form-group" style="grid-column:span 2">
          <label>Favicon do Sistema (ícone da aba do navegador)</label>
          <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:8px">
            ${cfg_ap.favicon
              ? `<div style="padding:6px 10px;background:#fff;border:1px solid var(--border);border-radius:var(--r);display:inline-flex;align-items:center;gap:8px">
                   <img src="${cfg_ap.favicon}" style="height:28px;width:28px;object-fit:contain">
                 </div>
                 <button class="btn btn-danger btn-sm" onclick="removeFaviconSistema()" type="button">Remover favicon</button>`
              : `<span style="font-size:12px;color:var(--text3)">Nenhum favicon cadastrado — usando ícone padrão</span>`}
          </div>
          <input type="file" id="ap-favicon" accept="image/png,image/jpeg,image/svg+xml,image/webp" onchange="previewAparenciaLogo(this,'ap-favicon-preview')">
          <div class="hint">PNG, JPG, WEBP ou SVG · Recomendado quadrado 32×32 ou 64×64 · Máx 300 KB</div>
          <div id="ap-favicon-preview" style="margin-top:8px"></div>
        </div>
      </div>
      <div class="modal-footer" style="padding-top:10px;margin-top:0;border-top:none;justify-content:flex-start">
        <button class="btn btn-primary" onclick="saveAparenciaIdentidade()">Salvar Identidade</button>
      </div>
    </div>
    <div class="card" style="margin-top:16px">
      <div class="section-title">Tela de Login</div>
      <div class="form-group">
        <label>Imagem de fundo</label>
        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:8px">
          ${cfg_ap.bg_login
            ? `<div style="padding:4px;background:#fff;border:1px solid var(--border);border-radius:var(--r);display:inline-flex">
                 <img src="${cfg_ap.bg_login}" style="height:48px;width:80px;object-fit:cover;border-radius:4px">
               </div>
               <button class="btn btn-danger btn-sm" onclick="removeBgLogin()" type="button">Remover fundo</button>`
            : `<span style="font-size:12px;color:var(--text3)">Nenhuma imagem de fundo cadastrada</span>`}
        </div>
        <input type="file" id="ap-bg" accept="image/png,image/jpeg,image/webp" onchange="previewAparenciaLogo(this,'ap-bg-preview');_readFile('ap-bg').then(d=>{_apLoginPreviewBg=d||'';updateLoginPreview()})">
        <div class="hint">PNG, JPG ou WEBP · Recomendado 1920×1080 · Máx 8 MB</div>
        <div id="ap-bg-preview" style="margin-top:8px"></div>
      </div>
      <div style="margin-top:16px;display:flex;gap:20px;align-items:flex-start;flex-wrap:wrap">
        <div style="width:172px;flex-shrink:0">
          <label style="display:block;margin-bottom:10px">Transparência do Box</label>
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
            <input type="range" id="ap-box-transp" class="ap-range" min="0" max="100"
              value="${cfg_ap.login_box_transparencia||0}"
              oninput="apRangeUpdate(+this.value)"
              style="flex:1;background:linear-gradient(to right,#2563eb ${cfg_ap.login_box_transparencia||0}%,var(--bg4) ${cfg_ap.login_box_transparencia||0}%)">
          </div>
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
            <input type="number" id="ap-box-transp-num" min="0" max="100"
              value="${cfg_ap.login_box_transparencia||0}"
              oninput="if(+this.value>=0&&+this.value<=100)apRangeUpdate(+this.value)"
              style="flex:1;min-width:0">
            <div style="display:flex;align-items:center;justify-content:center;min-width:52px;height:34px;background:var(--blue-bg);color:var(--blue-text);border:1px solid var(--blue-border);border-radius:var(--r);font-size:14px;font-weight:700;gap:1px;flex-shrink:0">
              <span id="ap-box-transp-badge">${cfg_ap.login_box_transparencia||0}</span><span style="font-size:10px">%</span>
            </div>
          </div>
          <div class="hint" style="font-size:11px">0% opaco · 100% transparente</div>
        </div>
        <div style="flex:1;min-width:200px;max-width:500px">
          <div style="font-size:11px;font-weight:600;color:var(--text3);text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px">Pré-visualização</div>
          <div id="ap-login-preview" style="width:100%;aspect-ratio:16/9;border-radius:12px;border:1px solid var(--border);overflow:hidden;display:flex;align-items:center;justify-content:center;background-color:#0f172a;background-size:cover;background-position:center;${cfg_ap.bg_login?`background-image:url(${cfg_ap.bg_login})`:''}">
            <div id="ap-login-preview-box" style="background:rgba(255,255,255,${((100-(cfg_ap.login_box_transparencia||0))/100).toFixed(2)});border-radius:10px;padding:16px 20px;width:158px;box-shadow:0 8px 30px rgba(0,0,0,.35);border:1px solid rgba(255,255,255,.12);transition:background .08s">
              <div style="display:flex;align-items:center;gap:7px;margin-bottom:12px">
                <div style="width:22px;height:22px;background:#e2e8f0;border-radius:6px;flex-shrink:0"></div>
                <div style="flex:1">
                  <div style="height:6px;background:#334155;border-radius:3px;margin-bottom:4px"></div>
                  <div style="width:55%;height:4px;background:#94a3b8;border-radius:2px"></div>
                </div>
              </div>
              <div style="height:5px;background:#e2e8f0;border-radius:3px;margin-bottom:6px"></div>
              <div style="height:5px;background:#e2e8f0;border-radius:3px;margin-bottom:6px"></div>
              <div style="height:5px;background:#e2e8f0;border-radius:3px;margin-bottom:14px"></div>
              <div style="height:28px;background:#2563eb;border-radius:6px;display:flex;align-items:center;justify-content:center">
                <div style="width:40px;height:4px;background:rgba(255,255,255,.6);border-radius:2px"></div>
              </div>
            </div>
          </div>
          <div style="margin-top:8px;display:flex;gap:8px">
            <button class="btn btn-primary btn-sm" onclick="saveAparenciaLogin()">Salvar Login</button>
          </div>
        </div>
        <div style="width:220px;flex-shrink:0">
          <div style="font-size:11px;font-weight:600;color:var(--text3);text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px">Esquema de Cores</div>
          <div class="hint" style="margin-bottom:12px">Deixe em branco para usar o padrão.</div>
          <div class="form-group"><label>Cor Primária</label>
            <div style="display:flex;align-items:center;gap:8px">
              <input type="color" id="ap-cor-input" value="${cfg_ap.cor_primaria||'#2563eb'}" oninput="$('ap-cor').value=this.value" style="width:36px;height:32px;padding:2px;border:1px solid var(--border);border-radius:var(--r);cursor:pointer;flex-shrink:0">
              <input id="ap-cor" value="${esc(cfg_ap.cor_primaria||'')}" placeholder="#2563eb" oninput="if(/^#[0-9a-fA-F]{6}$/.test(this.value))$('ap-cor-input').value=this.value" style="flex:1;min-width:0">
            </div>
          </div>
          <div class="form-group"><label>Cor dos Botões</label>
            <div style="display:flex;align-items:center;gap:8px">
              <input type="color" id="ap-cor-botao-input" value="${cfg_ap.cor_botao||'#2563eb'}" oninput="$('ap-cor-botao').value=this.value" style="width:36px;height:32px;padding:2px;border:1px solid var(--border);border-radius:var(--r);cursor:pointer;flex-shrink:0">
              <input id="ap-cor-botao" value="${esc(cfg_ap.cor_botao||'')}" placeholder="#2563eb" oninput="if(/^#[0-9a-fA-F]{6}$/.test(this.value))$('ap-cor-botao-input').value=this.value" style="flex:1;min-width:0">
            </div>
          </div>
          <div class="form-group"><label>Hover do Menu</label>
            <div style="display:flex;align-items:center;gap:8px">
              <input type="color" id="ap-cor-hover-input" value="${cfg_ap.cor_hover||'#f1f5f9'}" oninput="$('ap-cor-hover').value=this.value" style="width:36px;height:32px;padding:2px;border:1px solid var(--border);border-radius:var(--r);cursor:pointer;flex-shrink:0">
              <input id="ap-cor-hover" value="${esc(cfg_ap.cor_hover||'')}" placeholder="#f1f5f9" oninput="if(/^#[0-9a-fA-F]{6}$/.test(this.value))$('ap-cor-hover-input').value=this.value" style="flex:1;min-width:0">
            </div>
          </div>
          <div style="display:flex;gap:8px;margin-top:4px;flex-wrap:wrap">
            <button class="btn btn-primary btn-sm" onclick="saveAparenciaCores()">Salvar Cores</button>
            <button class="btn btn-default btn-sm" onclick="resetAparenciaCores()">Restaurar</button>
          </div>
        </div>
      </div>
    </div>
  </div>`;

  const panelPerfis = `<div id="cfg-panel-perfis" style="display:none">
    <div class="flex-between mb-16" style="flex-wrap:wrap;gap:10px">
      <div style="font-size:13px;color:var(--text2)">${Object.keys(perfis).length} perfis configurados · clique em <strong>Editar</strong> para ajustar permissões</div>
      <button class="btn btn-primary btn-sm" onclick="novoPerfilModal()">+ Novo Perfil</button>
    </div>
    <div class="grid-4">${perfilCards}</div>
  </div>`;

  const panelEmail = `<div id="cfg-panel-email" style="display:none">
    <div class="card">
      <div class="flex-between" style="margin-bottom:12px;gap:14px;align-items:flex-start">
        <div>
          <div class="section-title" style="margin-bottom:4px">Configurações de E-mail (SMTP)</div>
          <div style="font-size:12px;color:var(--text3)">Envio de links de assinatura e notificações pela aplicação.</div>
        </div>
        <label class="switch-control" for="email-enabled">
          <input type="checkbox" id="email-enabled" ${cfg_email.enabled?'checked':''}>
          <span class="switch-slider"></span>
          <span>
            <span class="switch-title">${cfg_email.enabled?'Ativo':'Inativo'}</span>
            <span class="switch-sub">Envio de e-mail</span>
          </span>
        </label>
      </div>
      <div class="info-box blue" style="margin-bottom:14px">
        Configure e ative o SMTP diretamente pela aplicação. A senha salva pela tela fica armazenada no banco da aplicação; use senha de app quando o provedor exigir.
        ${cfg_email.password_configurado ? '<span style="color:var(--green-text);font-weight:600;margin-left:8px">Senha configurada</span>' : '<span style="color:var(--red-text);font-weight:600;margin-left:8px">Senha não configurada</span>'}
      </div>
      <div class="form-grid-2">
        <div class="form-group"><label>Servidor SMTP</label><input id="email-host" value="${esc(cfg_email.host||'')}" placeholder="smtp.gmail.com"></div>
        <div class="form-group"><label>Porta</label><input id="email-port" type="number" value="${cfg_email.port||587}" placeholder="587"></div>
        <div class="form-group"><label>Usuário SMTP</label><input id="email-user" value="${esc(cfg_email.user||'')}" placeholder="ti@empresa.com"></div>
        <div class="form-group"><label>Senha SMTP</label>
          <input id="email-password" type="password" placeholder="${cfg_email.password_configurado?'Manter senha atual':'Não configurada'}" autocomplete="new-password">
        </div>
        <div class="form-group"><label>Nome remetente</label><input id="email-from-name" value="${esc(cfg_email.from_name||'')}" placeholder="TI Empresa"></div>
        <div class="form-group"><label>E-mail remetente</label><input id="email-from-email" value="${esc(cfg_email.from_email||'')}" placeholder="noreply@empresa.com"></div>
        <div class="form-group"><label>E-mail para teste</label><input id="email-test-to" value="" placeholder="seu.email@empresa.com"></div>
      </div>
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;flex-wrap:wrap">
        <input type="checkbox" id="email-tls" ${cfg_email.tls!==false?'checked':''} style="width:auto;margin-left:16px">
        <label for="email-tls" style="margin:0;font-size:13px">Usar TLS/STARTTLS</label>
        ${cfg_email.password_configurado ? '<input type="checkbox" id="email-clear-password" style="width:auto;margin-left:16px"><label for="email-clear-password" style="margin:0;font-size:13px;color:var(--red-text)">Apagar senha salva</label>' : ''}
      </div>
      <div class="flex-gap">
        <button class="btn btn-primary btn-sm" onclick="saveEmailCfg()">Salvar E-mail</button>
        <button class="btn btn-default btn-sm" onclick="saveEmailCfg(true)">Salvar e Testar</button>
      </div>
      <div style="margin-top:18px">
        <div class="flex-between" style="gap:12px;align-items:flex-end;flex-wrap:wrap;margin-bottom:2px">
          <div>
            <div class="section-title" style="margin-bottom:4px">Templates de E-mail</div>
            <div style="font-size:12px;color:var(--text3)">Personalize os textos enviados nos links de assinatura sem alterar código.</div>
          </div>
          <button class="btn btn-primary btn-sm" onclick="saveEmailTemplates()" type="button">Salvar Templates</button>
        </div>
        ${emailTemplateCard('assinatura','Termo de Responsabilidade','Usado ao enviar link de assinatura para alocação de ativo.',['empresa','colaborador','ativo','link'],tplAss)}
        ${emailTemplateCard('devolucao','Termo de Devolução','Usado ao enviar link de assinatura para devolução de equipamentos.',['empresa','colaborador','link'],tplDev)}
      </div>
    </div>
  </div>`;

  const defaultTermoAvulsoModelo = tipo => ({
    titulo: `TERMO DE ${String(tipo||'AVULSO').toUpperCase()}`,
    preambulo: `Eu, {colaborador}, do setor {setor}, unidade {unidade}, declaro estar ciente e de acordo com as regras referentes a {tipo}, com validade até {validade}.`,
    clausulas: [
      'O recurso, acesso ou obrigação descrito neste termo é pessoal e intransferível.',
      'O uso deve respeitar as políticas internas, normas de segurança da informação e orientações da área de TI.',
      'O descumprimento das regras poderá resultar em revogação do acesso e medidas administrativas cabíveis.',
    ],
    rodape: '{empresa} — Termo {tipo} emitido em {data} pelo Sistema de Gestão de TI',
  });
  const avulsoTipos = _settings.termos_avulsos_tipos || [];
  avulsoTipos.forEach(tipo=>{
    if(!_termoAvulsoModelos[tipo]) _termoAvulsoModelos[tipo] = defaultTermoAvulsoModelo(tipo);
  });
  _settings.termos_avulsos_modelos = {..._termoAvulsoModelos};
  const termModels = [
    {kind:'tr', title:'Recebimento', subtitle:'Entrega de equipamentos ao colaborador', cfg:cfg_tr, color:'blue'},
    {kind:'td', title:'Devolução', subtitle:'Retorno e conferência de equipamentos', cfg:cfg_td, color:'green'},
    {kind:'te', title:'Empréstimo', subtitle:'Uso temporário com devolução prevista', cfg:cfg_te, color:'amber'},
    ...avulsoTipos.map((tipo,idx)=>({
      kind:`ta:${encodeURIComponent(tipo)}`,
      title:tipo,
      subtitle:'Modelo personalizado com template próprio',
      cfg:_termoAvulsoModelos[tipo] || defaultTermoAvulsoModelo(tipo),
      color:['purple','blue','green','amber','gray'][idx % 5],
      avulso:true,
      tipo,
    })),
  ];
  const termModelCard = model => {
    const clauseCount = Array.isArray(model.cfg?.clausulas) ? model.cfg.clausulas.length : 0;
    const title = model.cfg?.titulo || `Termo de ${model.title}`;
    return `<article class="term-template-card" data-term-kind="${escAttr(model.kind)}">
      <div class="term-template-top">
        <div class="term-template-icon">${svgIcon('clipboard')}</div>
        <div style="min-width:0">
          <div class="term-template-title">${esc(model.title)}</div>
          <div class="term-template-desc">${esc(model.subtitle)}</div>
        </div>
      </div>
      <div class="term-template-desc" title="${escAttr(title)}">${esc(title)}</div>
      <div class="term-template-meta">
        ${badge(`${clauseCount} cláusula${clauseCount===1?'':'s'}`, model.color)}
        ${badge(model.avulso ? 'Modelo personalizado' : 'Padrão do sistema','gray')}
      </div>
      <div class="term-template-actions">
        <button class="btn btn-primary btn-sm" type="button" onclick="editTermConfig(${jsArg(model.kind)})">${inlineIcon('edit')} Editar</button>
        <button class="btn btn-default btn-sm" type="button" onclick="previewTermConfig(${jsArg(model.kind)})">${inlineIcon('eye')} Prévia</button>
        <button class="btn btn-default btn-sm" type="button" onclick="loadTermExample(${jsArg(model.kind)})">${inlineIcon('clipboard')} Exemplo</button>
        ${model.avulso ? `<button class="btn btn-danger btn-sm btn-icon" type="button" title="Remover modelo" onclick="removeTipoTermoConfig(${jsArg(model.tipo)})">${svgIcon('trash')}</button>` : ''}
      </div>
    </article>`;
  };

  const panelTermos = `<div id="cfg-panel-termos" style="display:none;flex-direction:column;gap:16px">
    <section id="terms-manager" class="terms-manager">
      <div class="terms-manager-head">
        <div>
          <div class="terms-manager-title">Modelos de Termos</div>
          <div class="terms-manager-sub">Recebimento, devolução e empréstimo são modelos padrão do sistema. Os demais termos também têm template próprio e independente.</div>
        </div>
        <button class="btn btn-primary" type="button" onclick="addTipoTermoConfig()">${inlineIcon('plus')} Novo modelo</button>
      </div>
      <div class="term-template-grid">
        ${termModels.map(termModelCard).join('')}
      </div>
    </section>
    <div id="term-editor-shell" class="term-editor-shell">
      <div class="term-editor-column">
        <div class="term-editor-head">
          <div>
            <div class="term-editor-title" id="term-editor-title">Editor do Termo</div>
            <div class="term-editor-sub" id="term-editor-sub">Selecione um modelo acima para editar.</div>
          </div>
          <div class="term-editor-actions">
            <button class="btn btn-default btn-sm" type="button" onclick="closeTermEditor()">${inlineIcon('undo')} Voltar</button>
            <select id="term-preview-kind" style="width:auto" onchange="selectTermConfig(this.value)">
              <option value="tr">Recebimento</option>
              <option value="td">Devolução</option>
              <option value="te">Empréstimo</option>
              ${avulsoTipos.map(tipo=>`<option value="ta:${encodeURIComponent(tipo)}">${esc(tipo)}</option>`).join('')}
            </select>
            <button class="btn btn-default btn-sm" type="button" onclick="previewTermConfig($('term-preview-kind')?.value || 'tr')">${inlineIcon('eye')} Prévia</button>
          </div>
        </div>
    <div class="card term-config-card" data-term-kind="tr">
      <div class="section-title">Personalização — Termo de Recebimento</div>
      <div class="info-box blue" style="margin-bottom:14px">
        <strong>Variáveis disponíveis:</strong> <code>{colaborador}</code> <code>{setor}</code> <code>{unidade}</code> <code>{ativo}</code> <code>{data}</code> <code>{empresa}</code> <code>{termo}</code><br>
        <span style="font-size:11px;opacity:.8">Clique em <strong>Carregar Exemplo</strong> para pré-preencher com um modelo completo que você pode editar livremente.</span>
      </div>
      <div class="form-grid-2">
        <div class="form-group" style="grid-column:span 2"><label>Título do Termo</label>
          <input id="tr-titulo" value="${esc(cfg_tr.titulo||'TERMO DE RESPONSABILIDADE DE EQUIPAMENTO')}">
        </div>
        <div class="form-group" style="grid-column:span 2"><label>Preâmbulo (texto após o título, antes do ativo)</label>
          <textarea id="tr-preambulo" style="width:100%;min-height:80px;resize:vertical;padding:8px;border:1px solid var(--border);border-radius:var(--r);font-family:inherit;background:var(--bg2);color:var(--text)">${esc(cfg_tr.preambulo||'')}</textarea>
        </div>
        <div class="form-group" style="grid-column:span 2"><label>Cláusulas (uma por linha)</label>
          <textarea id="tr-clausulas" style="width:100%;min-height:140px;resize:vertical;padding:8px;border:1px solid var(--border);border-radius:var(--r);font-family:inherit;background:var(--bg2);color:var(--text)">${(cfg_tr.clausulas||[]).join('\n')}</textarea>
        </div>
        <div class="form-group" style="grid-column:span 2"><label>Rodapé do PDF</label>
          <input id="tr-rodape" value="${esc(cfg_tr.rodape||'')}">
        </div>
      </div>
      <div class="flex-gap">
        <button class="btn btn-primary btn-sm" onclick="saveTermoRecebimento()">Salvar Termo de Recebimento</button>
        <button class="btn btn-default btn-sm" onclick="carregarExemploTR()">Carregar Exemplo</button>
      </div>
    </div>
    <div class="card term-config-card" data-term-kind="td">
      <div class="section-title">Personalização — Termo de Devolução</div>
      <div class="info-box blue" style="margin-bottom:14px">
        <strong>Variáveis disponíveis:</strong> <code>{colaborador}</code> <code>{setor}</code> <code>{unidade}</code> <code>{ativo}</code> <code>{data}</code> <code>{empresa}</code> <code>{termo}</code><br>
        <span style="font-size:11px;opacity:.8">Clique em <strong>Carregar Exemplo</strong> para pré-preencher com um modelo completo que você pode editar livremente.</span>
      </div>
      <div class="form-grid-2">
        <div class="form-group" style="grid-column:span 2"><label>Título</label>
          <input id="td-titulo" value="${esc(cfg_td.titulo||'TERMO DE DEVOLUÇÃO DE EQUIPAMENTOS')}">
        </div>
        <div class="form-group" style="grid-column:span 2"><label>Preâmbulo</label>
          <textarea id="td-preambulo" style="width:100%;min-height:80px;resize:vertical;padding:8px;border:1px solid var(--border);border-radius:var(--r);font-family:inherit;background:var(--bg2);color:var(--text)">${esc(cfg_td.preambulo||'')}</textarea>
        </div>
        <div class="form-group" style="grid-column:span 2"><label>Cláusulas adicionais (uma por linha)</label>
          <textarea id="td-clausulas" style="width:100%;min-height:120px;resize:vertical;padding:8px;border:1px solid var(--border);border-radius:var(--r);font-family:inherit;background:var(--bg2);color:var(--text)">${(cfg_td.clausulas||[]).join('\n')}</textarea>
        </div>
        <div class="form-group" style="grid-column:span 2"><label>Declaração (frase de encerramento antes da assinatura)</label>
          <input id="td-declaracao" value="${esc(cfg_td.declaracao||'Declaro ter devolvido todos os equipamentos listados acima em plenas condições.')}">
        </div>
        <div class="form-group" style="grid-column:span 2"><label>Rodapé do PDF</label>
          <input id="td-rodape" value="${esc(cfg_td.rodape||'')}">
        </div>
      </div>
      <div class="flex-gap">
        <button class="btn btn-primary btn-sm" onclick="saveTermoDevolucao()">Salvar Termo de Devolução</button>
        <button class="btn btn-default btn-sm" onclick="carregarExemploTD()">Carregar Exemplo</button>
      </div>
    </div>

    <div class="card term-config-card" data-term-kind="te">
      <div class="section-title">Personalização — Termo de Empréstimo</div>
      <div class="info-box blue" style="margin-bottom:14px">
        <strong>Variáveis:</strong> <code>{colaborador}</code> <code>{setor}</code> <code>{unidade}</code> <code>{ativo}</code> <code>{data}</code> <code>{empresa}</code> <code>{dataDevolucao}</code>
      </div>
      <div class="form-grid-2">
        <div class="form-group" style="grid-column:span 2"><label>Título</label>
          <input id="te-titulo" value="${esc(cfg_te.titulo||'TERMO DE EMPRÉSTIMO DE EQUIPAMENTO')}">
        </div>
        <div class="form-group" style="grid-column:span 2"><label>Preâmbulo</label>
          <textarea id="te-preambulo" style="width:100%;min-height:80px;resize:vertical;padding:8px;border:1px solid var(--border);border-radius:var(--r);font-family:inherit;background:var(--bg2);color:var(--text)">${esc(cfg_te.preambulo||'')}</textarea>
        </div>
        <div class="form-group" style="grid-column:span 2"><label>Cláusulas (uma por linha)</label>
          <textarea id="te-clausulas" style="width:100%;min-height:120px;resize:vertical;padding:8px;border:1px solid var(--border);border-radius:var(--r);font-family:inherit;background:var(--bg2);color:var(--text)">${(cfg_te.clausulas||[]).join('\n')}</textarea>
        </div>
        <div class="form-group" style="grid-column:span 2"><label>Rodapé do PDF</label>
          <input id="te-rodape" value="${esc(cfg_te.rodape||'')}">
        </div>
      </div>
      <button class="btn btn-primary btn-sm" onclick="saveTermoEmprestimo()">Salvar Termo de Empréstimo</button>
    </div>

    <div class="card term-config-card" data-term-kind="ta">
      <div class="section-title">Personalização — <span id="ta-editor-label">Termo</span></div>
      <div class="info-box blue" style="margin-bottom:14px">
        <strong>Variáveis:</strong> <code>{colaborador}</code> <code>{setor}</code> <code>{unidade}</code> <code>{empresa}</code> <code>{tipo}</code> <code>{validade}</code> <code>{data}</code>
      </div>
      <div class="form-grid-2">
        <div class="form-group" style="grid-column:span 2"><label>Título</label>
          <input id="ta-titulo" value="">
        </div>
        <div class="form-group" style="grid-column:span 2"><label>Preâmbulo</label>
          <textarea id="ta-preambulo" style="width:100%;min-height:80px;resize:vertical;padding:8px;border:1px solid var(--border);border-radius:var(--r);font-family:inherit;background:var(--bg2);color:var(--text)"></textarea>
        </div>
        <div class="form-group" style="grid-column:span 2"><label>Cláusulas (uma por linha)</label>
          <textarea id="ta-clausulas" style="width:100%;min-height:120px;resize:vertical;padding:8px;border:1px solid var(--border);border-radius:var(--r);font-family:inherit;background:var(--bg2);color:var(--text)"></textarea>
        </div>
        <div class="form-group" style="grid-column:span 2"><label>Rodapé do PDF</label>
          <input id="ta-rodape" value="">
        </div>
      </div>
      <button class="btn btn-primary btn-sm" onclick="saveTermoAvulsoModelo()">Salvar Modelo</button>
    </div>
      </div>
    </div>
  </div>`;

  const panelBackup = `<div id="cfg-panel-backup" style="display:none">
    <div class="card">
      <div class="flex-between" style="margin-bottom:12px;gap:14px;align-items:flex-start;flex-wrap:wrap">
        <div>
          <div class="section-title" style="margin-bottom:4px">Backup da Aplicação</div>
          <div style="font-size:12px;color:var(--text3)">Configure backups lógicos em JSON gerados e armazenados pela própria aplicação.</div>
        </div>
        <label class="switch-control" for="backup-enabled">
          <input type="checkbox" id="backup-enabled" ${cfg_backup.enabled?'checked':''}>
          <span class="switch-slider"></span>
          <span>
            <span class="switch-title">${cfg_backup.enabled?'Ativo':'Inativo'}</span>
            <span class="switch-sub">Backup automático</span>
          </span>
        </label>
      </div>
      <div class="grid-3" style="margin-bottom:16px">
        <div style="border:1px solid var(--border);border-radius:var(--r);padding:12px;background:var(--bg3)">
          <div style="font-size:11px;color:var(--text3);font-weight:700;text-transform:uppercase;margin-bottom:4px">Última execução</div>
          <div style="font-size:14px;font-weight:700;color:var(--text)">${cfg_backup.last_run ? fmtDateTime(cfg_backup.last_run) : 'Nunca executado'}</div>
        </div>
        <div style="border:1px solid var(--border);border-radius:var(--r);padding:12px;background:var(--bg3)">
          <div style="font-size:11px;color:var(--text3);font-weight:700;text-transform:uppercase;margin-bottom:4px">Status</div>
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">${backupStatusBadge}<span style="font-size:12px;color:var(--text2)">${esc(cfg_backup.last_error || cfg_backup.last_status || 'Sem execução')}</span></div>
        </div>
        <div style="border:1px solid var(--border);border-radius:var(--r);padding:12px;background:var(--bg3)">
          <div style="font-size:11px;color:var(--text3);font-weight:700;text-transform:uppercase;margin-bottom:4px">Frequência atual</div>
          <div style="font-size:14px;font-weight:700;color:var(--text)">${backupFreqLabel[cfg_backup.frequency] || 'Diário'} · ${esc(backupScheduleLabel)}</div>
          <div style="font-size:11px;color:var(--text3);margin-top:3px">Retenção ${cfg_backup.retention || 7} arquivo(s)</div>
        </div>
      </div>
      <div class="form-grid-2">
        <div class="form-group"><label>Frequência</label>
          <select id="backup-frequency" onchange="updateBackupScheduleFields()">
            <option value="daily" ${cfg_backup.frequency==='daily'?'selected':''}>Diário</option>
            <option value="weekly" ${cfg_backup.frequency==='weekly'?'selected':''}>Semanal</option>
            <option value="monthly" ${cfg_backup.frequency==='monthly'?'selected':''}>Mensal</option>
          </select>
        </div>
        <div class="form-group"><label>Horário de execução</label>
          <input id="backup-schedule-time" type="time" value="${escAttr(backupScheduleTime)}">
        </div>
        <div class="form-group" id="backup-weekly-day-group" style="display:${cfg_backup.frequency==='weekly'?'block':'none'}"><label>Dia da semana</label>
          <select id="backup-weekly-day">
            ${backupWeekdayLabel.map((label,idx)=>`<option value="${idx}" ${backupWeeklyDay===idx?'selected':''}>${label}</option>`).join('')}
          </select>
        </div>
        <div class="form-group" id="backup-monthly-day-group" style="display:${cfg_backup.frequency==='monthly'?'block':'none'}"><label>Dia do mês</label>
          <input id="backup-monthly-day" type="number" min="1" max="31" value="${backupMonthlyDay}">
        </div>
        <div class="form-group"><label>Retenção de arquivos</label>
          <input id="backup-retention" type="number" min="1" max="90" value="${cfg_backup.retention || 7}">
        </div>
      </div>
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;flex-wrap:wrap">
        <input type="checkbox" id="backup-include-audit" ${cfg_backup.include_audit?'checked':''} style="width:auto">
        <label for="backup-include-audit" style="margin:0;font-size:13px">Incluir log de auditoria no backup</label>
      </div>
      <div class="flex-gap" style="flex-wrap:wrap;margin-bottom:18px">
        <button class="btn btn-primary btn-sm" onclick="saveBackupCfg()" type="button">Salvar Backup</button>
        <button class="btn btn-success btn-sm" onclick="runBackupNow()" type="button">Gerar Agora</button>
        <a class="btn btn-primary" href="/api/backup.json" download>Baixar Backup JSON</a>
      </div>
      <div class="info-box blue" style="margin-bottom:14px">
        O backup lógico fica em <span class="mono">instance/backups</span> e não substitui snapshots do banco/servidor. Use retenção baixa em ambientes com pouco espaço em disco.
      </div>
      <div class="section-title" style="margin-top:4px">Backups Armazenados</div>
      <div style="margin-bottom:20px">${backupFilesHtml}</div>
      <div class="section-title" style="margin-top:4px">Importar / Restaurar Backup</div>
      <div style="margin-bottom:8px;font-size:12px;color:var(--text3)">Valide ou restaure um arquivo de backup JSON externo. Um backup automático é gerado antes de qualquer restauração.</div>
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:16px">
        <input type="file" id="backup-restore-file" accept=".json" style="flex:1;min-width:200px;font-size:13px">
        <button class="btn btn-default btn-sm" onclick="validateBackupUpload()" type="button">Validar Arquivo</button>
        <button class="btn btn-warning btn-sm" onclick="confirmRestoreBackupUpload()" type="button">Restaurar de Arquivo</button>
      </div>
      <div class="section-title">Exportações CSV</div>
      <div class="flex-gap" style="flex-wrap:wrap">
        <a class="btn btn-default" href="/api/export/assets.csv" download>Ativos CSV</a>
        <a class="btn btn-default" href="/api/export/colaboradores.csv" download>Colaboradores CSV</a>
        <a class="btn btn-default" href="/api/export/alocacoes.csv" download>Alocações CSV</a>
      </div>
    </div>
  </div>`;

  const panelUpdates = `<div id="cfg-panel-updates" style="display:none">
    <div class="card">
      <div class="flex-between" style="margin-bottom:14px;gap:14px;align-items:flex-start;flex-wrap:wrap">
        <div>
          <div class="section-title" style="margin-bottom:4px">Atualização do Sistema</div>
          <div style="font-size:12px;color:var(--text3)">A atualização é manual: o administrador verifica, decide e aplica quando quiser.</div>
        </div>
        ${updateBadge}
      </div>
      <div class="grid-3" style="margin-bottom:16px">
        <div style="border:1px solid var(--border);border-radius:var(--r);padding:12px;background:var(--bg3)">
          <div style="font-size:11px;color:var(--text3);font-weight:700;text-transform:uppercase;margin-bottom:4px">Versão atual</div>
          <div style="font-size:14px;font-weight:700;color:var(--text)">${esc(updateState.currentVersion||APP_VERSION||'local')}</div>
        </div>
        <div style="border:1px solid var(--border);border-radius:var(--r);padding:12px;background:var(--bg3)">
          <div style="font-size:11px;color:var(--text3);font-weight:700;text-transform:uppercase;margin-bottom:4px">Versão disponível</div>
          <div style="font-size:14px;font-weight:700;color:var(--text)">${esc(updateState.availableVersion || (updateState.updateAvailable ? 'Disponível no remoto' : updateState.currentVersion || APP_VERSION || 'local'))}</div>
        </div>
        <div style="border:1px solid var(--border);border-radius:var(--r);padding:12px;background:var(--bg3)">
          <div style="font-size:11px;color:var(--text3);font-weight:700;text-transform:uppercase;margin-bottom:4px">${updateState.supported?'Repositório':'Modo'}</div>
          <div style="font-size:14px;font-weight:700;color:var(--text)">${updateState.supported?'Disponível':'Manual pelo servidor'}</div>
        </div>
        <div style="border:1px solid var(--border);border-radius:var(--r);padding:12px;background:var(--bg3)">
          <div style="font-size:11px;color:var(--text3);font-weight:700;text-transform:uppercase;margin-bottom:4px">Estado</div>
          <div style="font-size:12px;color:var(--text2)">${updateDetails}</div>
        </div>
      </div>
      <div class="info-box blue" style="margin-bottom:14px">
        ${esc(updateState.message || 'Clique em Verificar atualizações para consultar o repositório remoto.')}
        ${updateState.dirty ? '<br><span style="font-size:12px;color:var(--amber-text)">Atenção: há alterações locais no servidor — serão descartadas e substituídas pela versão do repositório ao aplicar.</span>' : ''}
        ${updateState.ahead ? `<br><span style="font-size:12px;color:var(--text3)">O servidor possui ${updateState.ahead} commit(s) local(is) não enviado(s) ao remoto — serão substituídos pela versão do repositório ao aplicar.</span>` : ''}
      </div>
      <div class="flex-gap" style="flex-wrap:wrap">
        <button class="btn btn-default btn-sm" onclick="checkSystemUpdate()" type="button" ${!updateState.supported ? 'disabled' : ''}>Verificar atualizações</button>
        ${updateState.supported
          ? `<button id="btn-apply-update" class="btn btn-primary btn-sm" onclick="confirmApplySystemUpdate()" type="button" ${!updateState.canApply ? 'disabled' : ''}>Aplicar atualização</button>`
          : `<button class="btn btn-primary btn-sm" onclick="showManualUpdateInstructions()" type="button">Ver instruções</button>`}
      </div>
      <div style="margin-top:14px;font-size:12px;color:var(--text3)">
        ${esc(updateApplyHint)} Antes de atualizar, gere backup. Após aplicar, reinicie/recrie a aplicação para carregar o novo código.
      </div>
    </div>
  </div>`;

  $('content').innerHTML = tabBar + panelGeral + panelOperacao + panelAparencia + panelPerfis + panelEmail + panelTermos + panelBackup + panelUpdates;
  cfgTab(_cfgTab);
}

function cfgTab(tab){
  _cfgTab = tab;
  const panels = {
    geral: 'grid', operacao: 'grid', aparencia: 'block', perfis: 'block', email: 'block', termos: 'flex', backup: 'block', updates: 'block'
  };
  Object.keys(panels).forEach(t=>{
    const panel = document.getElementById('cfg-panel-'+t);
    const btn   = document.getElementById('cfg-tab-'+t);
    if(!panel||!btn) return;
    const active = t===tab;
    panel.style.display        = active ? panels[t] : 'none';
    btn.style.color            = active ? 'var(--blue)' : 'var(--text2)';
    btn.style.borderBottomColor = active ? 'var(--blue)' : 'transparent';
    btn.style.fontWeight       = active ? '700' : '600';
  });
  if(tab==='termos') setTimeout(()=>initTermsPanel(), 0);
}

