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

  const VOICE_LABELS={idle:['eckos_voice_ready','Tap the orb to talk'],connecting:['eckos_voice_connecting','Connecting…'],listening:['eckos_voice_listening','Listening…'],thinking:['eckos_voice_thinking','Thinking…'],speaking:['eckos_voice_speaking','Speaking…'],muted:['eckos_voice_muted','Muted'],reconnecting:['eckos_voice_reconnecting','Reconnecting…'],error:['eckos_voice_error','Voice unavailable — tap to retry']};
  const voice={state:'idle',peer:null,channel:null,stream:null,audioContext:null,analyser:null,meterFrame:0,muted:false,explicitStop:false,reconnects:0,reconnectTimer:0,generation:0,userCaption:'',assistantCaption:'',handledCalls:new Set()};
  function byId(id){return global.document&&global.document.getElementById(id);}
  function visible(el){return !!el&&!el.hidden&&el.getAttribute('aria-hidden')!=='true'&&(!el.style||el.style.display!=='none');}
  function setVoiceState(state,caption){voice.state=state;const shell=global.document&&global.document.querySelector('.eckos-voice-status');if(shell)shell.dataset.eckosVoiceState=state;const label=VOICE_LABELS[state]||VOICE_LABELS.error,status=byId('eckosVoiceStatusText');if(status)status.textContent=translatedLabel(label[0],label[1]);const transcript=byId('eckosVoiceTranscript');if(transcript&&caption!==undefined)transcript.textContent=String(caption||'').slice(-500);const active=!['idle','error'].includes(state),orb=byId('eckosVoiceOrb');if(orb){orb.setAttribute('aria-label',active?'Stop live voice':'Start live voice');orb.title=active?'Stop live voice':'Start live voice';}const mute=byId('eckosVoiceMute'),end=byId('eckosVoiceEnd');if(mute)mute.hidden=!active;if(end)end.hidden=!active;}
  function sendRealtime(event){if(voice.channel&&voice.channel.readyState==='open')voice.channel.send(JSON.stringify(event));}
  function functionResult(callId,result){sendRealtime({type:'conversation.item.create',item:{type:'function_call_output',call_id:callId,output:JSON.stringify(result)}});sendRealtime({type:'response.create'});}
  function pendingHumanAction(){if(visible(byId('approvalCard')))return 'Hermes is waiting for an approval. Use the approval card.';if(visible(byId('clarifyCard')))return 'Hermes is waiting for a clarification. Use the clarification card.';return '';}
  async function sendToHermes(message){const blocked=pendingHumanAction();if(blocked)return {ok:false,error:'human_action_required',message:blocked};const composer=byId('msg');if(!composer||typeof global.send!=='function')return {ok:false,error:'hermes_unavailable'};const text=String(message||'').trim();if(!text)return {ok:false,error:'empty_message'};composer.value=text.slice(0,8000);composer.dispatchEvent(new Event('input',{bubbles:true}));await global.send();return {ok:true,status:'sent_to_native_hermes_session'};}
  async function executeFunctionCall(item){const callId=item&&item.call_id;if(!callId||voice.handledCalls.has(callId))return;voice.handledCalls.add(callId);let args={};try{args=JSON.parse(item.arguments||'{}');}catch(_){functionResult(callId,{ok:false,error:'invalid_arguments'});return;}try{if(item.name==='render_eckos_dashboard')functionResult(callId,applyDashboard(args));else if(item.name==='send_to_hermes')functionResult(callId,await sendToHermes(args.message));else functionResult(callId,{ok:false,error:'unknown_tool'});}catch(_){functionResult(callId,{ok:false,error:'tool_failed'});}}
  function handleRealtimeEvent(raw){let event;try{event=JSON.parse(raw.data);}catch(_){return;}if(event.type==='input_audio_buffer.speech_started'){voice.userCaption='';setVoiceState(voice.muted?'muted':'listening','');}else if(event.type==='input_audio_buffer.speech_stopped')setVoiceState('thinking',voice.userCaption);else if(event.type==='conversation.item.input_audio_transcription.completed'){voice.userCaption=String(event.transcript||'').slice(-4000);setVoiceState('thinking',voice.userCaption);}else if(event.type==='response.audio_transcript.delta'||event.type==='response.output_audio_transcript.delta'){voice.assistantCaption=(voice.assistantCaption+String(event.delta||'')).slice(-4000);setVoiceState('speaking',voice.assistantCaption);}else if(event.type==='output_audio_buffer.started')setVoiceState('speaking',voice.assistantCaption);else if(event.type==='response.created'){voice.assistantCaption='';setVoiceState('thinking',voice.userCaption);}else if(event.type==='response.done'){const output=event.response&&Array.isArray(event.response.output)?event.response.output:[];for(const item of output)if(item&&item.type==='function_call')executeFunctionCall(item);if(!output.some(item=>item&&item.type==='function_call'))setVoiceState(voice.muted?'muted':'listening',voice.assistantCaption);}else if(event.type==='error'){voice.explicitStop=true;teardownVoice(false);setVoiceState('error','Realtime session error');}}
  function stopMeter(){if(voice.meterFrame)global.cancelAnimationFrame(voice.meterFrame);voice.meterFrame=0;if(voice.audioContext)voice.audioContext.close().catch(function(){});voice.audioContext=null;voice.analyser=null;}
  function startMeter(stream){const AudioContext=global.AudioContext||global.webkitAudioContext;if(!AudioContext)return;try{voice.audioContext=new AudioContext();voice.analyser=voice.audioContext.createAnalyser();voice.analyser.fftSize=256;voice.audioContext.createMediaStreamSource(stream).connect(voice.analyser);const values=new Uint8Array(voice.analyser.frequencyBinCount),tick=function(){if(!voice.analyser)return;voice.analyser.getByteFrequencyData(values);const level=values.reduce((sum,value)=>sum+value,0)/(values.length*255),shell=global.document.querySelector('.eckos-voice-status');if(shell)shell.style.setProperty('--voice-level',String(Math.min(1,level*3)));voice.meterFrame=global.requestAnimationFrame(tick);};tick();}catch(_){stopMeter();}}
  function teardownVoice(reset=true){global.clearTimeout(voice.reconnectTimer);voice.reconnectTimer=0;stopMeter();if(voice.channel)try{voice.channel.close();}catch(_){}if(voice.peer)try{voice.peer.close();}catch(_){}if(voice.stream)for(const track of voice.stream.getTracks())track.stop();const audio=byId('eckosVoiceAudio');if(audio)audio.srcObject=null;voice.peer=null;voice.channel=null;voice.stream=null;voice.muted=false;if(reset)setVoiceState('idle','');}
  function stopVoice(){voice.explicitStop=true;voice.generation+=1;teardownVoice(true);}
  function scheduleReconnect(){if(voice.reconnectTimer)return;if(voice.explicitStop||voice.reconnects>=2)return setVoiceState('error','Connection lost');voice.reconnects+=1;setVoiceState('reconnecting','Connection lost');voice.reconnectTimer=global.setTimeout(startVoice,500*voice.reconnects);}
  async function startVoice(){if(!global.RTCPeerConnection||!global.navigator||!global.navigator.mediaDevices)return setVoiceState('error','WebRTC microphone unavailable');const generation=++voice.generation;voice.explicitStop=false;teardownVoice(false);setVoiceState(voice.reconnects?'reconnecting':'connecting','');try{const stream=await global.navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}});if(generation!==voice.generation||voice.explicitStop){for(const track of stream.getTracks())track.stop();return;}voice.stream=stream;startMeter(stream);const peer=new RTCPeerConnection();voice.peer=peer;for(const track of stream.getTracks())peer.addTrack(track,stream);peer.ontrack=function(event){const audio=byId('eckosVoiceAudio');if(audio)audio.srcObject=event.streams[0];};peer.onconnectionstatechange=function(){if(['failed','disconnected'].includes(peer.connectionState))scheduleReconnect();};const channel=peer.createDataChannel('oai-events');voice.channel=channel;channel.onmessage=handleRealtimeEvent;channel.onopen=function(){voice.reconnects=0;setVoiceState('listening','');};const offer=await peer.createOffer();await peer.setLocalDescription(offer);const response=await global.fetch('api/eckos/realtime/calls',{method:'POST',headers:{'Content-Type':'application/sdp'},body:offer.sdp,credentials:'include'});if(generation!==voice.generation||voice.explicitStop)return;if(!response.ok)throw new Error('realtime_exchange_failed');const answer={type:'answer',sdp:await response.text()};if(generation!==voice.generation||voice.explicitStop)return;await peer.setRemoteDescription(answer);}catch(_){if(generation!==voice.generation||voice.explicitStop)return;voice.explicitStop=true;teardownVoice(false);setVoiceState('error','Check microphone permission and connection');}}
  function toggleMute(){if(!voice.stream)return;voice.muted=!voice.muted;for(const track of voice.stream.getAudioTracks())track.enabled=!voice.muted;const button=byId('eckosVoiceMute');if(button)button.textContent=voice.muted?'Unmute':'Mute';setVoiceState(voice.muted?'muted':'listening');}
  function bindVoice(){const orb=byId('eckosVoiceOrb');if(orb)orb.addEventListener('click',function(){if(!['idle','error'].includes(voice.state))stopVoice();else startVoice();});const mute=byId('eckosVoiceMute');if(mute)mute.addEventListener('click',toggleMute);const end=byId('eckosVoiceEnd');if(end)end.addEventListener('click',stopVoice);global.addEventListener('beforeunload',stopVoice,{once:true});}

  function initialize(){
    const root=global.document&&global.document.documentElement;
    if(!root||root.dataset.mode!=='eckos') return;
    applyDashboard();
    bindVoice();
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
