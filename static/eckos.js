// EckOS is an alternate presentation of the existing Hermes WebUI shell.
// It owns no runtime, transport, session, or action-resolution state.
(function(global){
  'use strict';

  const PANEL_REGISTRY=Object.freeze({
    conversation:Object.freeze({selector:'#messages',labelKey:'eckos_panel_conversation'}),
    activity:Object.freeze({selector:'#liveRunStatus',labelKey:'eckos_panel_activity'}),
    approvals:Object.freeze({selector:'#approvalCard',labelKey:'eckos_panel_approvals'}),
    clarifications:Object.freeze({selector:'#clarifyCard',labelKey:'eckos_panel_clarifications'}),
    agents:Object.freeze({selector:'#sessionList',labelKey:'eckos_panel_agents'}),
    cron:Object.freeze({selector:'#cronList',labelKey:'eckos_panel_cron'}),
    mcp:Object.freeze({selector:'#mcpServerList',labelKey:'eckos_panel_mcp'}),
    workspace:Object.freeze({selector:'.rightpanel',labelKey:'eckos_panel_workspace'}),
    usage:Object.freeze({selector:'#ctxIndicatorWrap',labelKey:'eckos_panel_usage'}),
    profile:Object.freeze({selector:'#titlebarProfileBtn',labelKey:'eckos_panel_profile'}),
  });
  const PANEL_IDS=Object.freeze(Object.keys(PANEL_REGISTRY));
  const DEFAULT_PANELS=Object.freeze(['conversation','activity','approvals','clarifications']);

  function unknownPanel(panel){
    return {ok:false,error:'unknown_panel',panel};
  }

  function normalizeDashboard(input){
    const config=input&&typeof input==='object'?input:{};
    const requested=config.panels===undefined?DEFAULT_PANELS:config.panels;
    if(!Array.isArray(requested)) return {ok:false,error:'invalid_panels'};

    const panels=[];
    for(const rawPanel of requested){
      if(typeof rawPanel!=='string'||!Object.prototype.hasOwnProperty.call(PANEL_REGISTRY,rawPanel)){
        return unknownPanel(String(rawPanel));
      }
      if(!panels.includes(rawPanel)) panels.push(rawPanel);
    }

    const focus=config.focus===undefined?(panels[0]||'conversation'):config.focus;
    if(typeof focus!=='string'||!Object.prototype.hasOwnProperty.call(PANEL_REGISTRY,focus)){
      return unknownPanel(String(focus));
    }
    return {ok:true,panels,focus};
  }

  function translatedLabel(key,fallback){
    return typeof global.t==='function'?global.t(key):fallback;
  }

  function syncPanelButtons(focus){
    const nav=global.document&&global.document.getElementById('eckosPanelNav');
    if(!nav) return;
    for(const button of nav.querySelectorAll('.eckos-panel-button')){
      button.setAttribute('aria-current',String(button.dataset.eckosPanel===focus));
    }
  }

  function focusPanel(panel){
    if(typeof panel!=='string'||!Object.prototype.hasOwnProperty.call(PANEL_REGISTRY,panel)){
      return unknownPanel(String(panel));
    }
    const root=global.document&&global.document.documentElement;
    if(!root||root.dataset.mode!=='eckos') return {ok:false,error:'inactive_mode'};

    root.dataset.eckosFocus=panel;
    syncPanelButtons(panel);
    const target=global.document.querySelector(PANEL_REGISTRY[panel].selector);
    if(target&&typeof target.scrollIntoView==='function') target.scrollIntoView({block:'nearest'});
    return {ok:true,panel};
  }

  function renderPanelButtons(panels,focus){
    const nav=global.document&&global.document.getElementById('eckosPanelNav');
    if(!nav) return;
    const fragment=global.document.createDocumentFragment();
    for(const panel of panels){
      const entry=PANEL_REGISTRY[panel];
      const button=global.document.createElement('button');
      button.type='button';
      button.className='eckos-panel-button';
      button.dataset.eckosPanel=panel;
      button.setAttribute('aria-current',String(panel===focus));
      button.textContent=translatedLabel(entry.labelKey,panel);
      button.addEventListener('click',function(){ focusPanel(panel); });
      fragment.appendChild(button);
    }
    nav.replaceChildren(fragment);
  }

  function applyDashboard(input){
    const normalized=normalizeDashboard(input);
    if(!normalized.ok) return normalized;

    const root=global.document&&global.document.documentElement;
    if(!root||root.dataset.mode!=='eckos') return {ok:false,error:'inactive_mode'};
    root.dataset.eckosPanels=normalized.panels.join(' ');
    root.dataset.eckosFocus=normalized.focus;
    renderPanelButtons(normalized.panels,normalized.focus);
    return normalized;
  }

  function initialize(){
    const root=global.document&&global.document.documentElement;
    if(!root||root.dataset.mode!=='eckos') return;
    applyDashboard();
  }

  global.EckOS=Object.freeze({
    panelIds:PANEL_IDS,
    normalizeDashboard,
    applyDashboard,
    focusPanel,
  });

  if(global.document){
    if(global.document.readyState==='loading') global.document.addEventListener('DOMContentLoaded',initialize,{once:true});
    else initialize();
  }
})(typeof window!=='undefined'?window:this);
