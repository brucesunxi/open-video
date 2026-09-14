import {useEffect,useRef,useState} from 'react';
import {Mic,Square,Hand,Send} from 'lucide-react';
import {api,post,type Teacher,type Session,type Asset,type Config} from './types';
import {Avatar} from './Avatar';
import {Speaker} from './speech';

type Phase='idle'|'listening'|'thinking'|'speaking'|'synthesizing'|'paused';
const names:Record<Phase,string>={idle:'准备对话',listening:'正在听你说',thinking:'正在查阅资料',speaking:'老师正在回答',synthesizing:'正在生成老师声音与画面',paused:'对话已暂停'};

// One turn at a time. Stop listening during playback to avoid transcribing the teacher.
export function Realtime({teacher,avatar,config}:{teacher:Teacher;avatar?:Asset;config:Config|null}){
  const [phase,setPhase]=useState<Phase>('idle'),[session,setSession]=useState<Session|null>(null),[draft,setDraft]=useState(''),[partial,setPartial]=useState(''),[error,setError]=useState('');
  const [input,setInput]=useState('auto'),[voice,setVoice]=useState('browser'),[speaking,setSpeaking]=useState(false);
  const clonedVoiceReady=Boolean(config?.tts.configured&&teacher.consent&&teacher.voice_profile_id);
  useEffect(()=>{setVoice(clonedVoiceReady?'gpu':'browser');},[teacher.id,clonedVoiceReady]);
  const [playbackBlocked,setPlaybackBlocked]=useState(false);
  const [video,setVideo]=useState<HTMLVideoElement|null>(null);
  const [preparing,setPreparing]=useState(false);
  useEffect(()=>{
    if(!config?.avatar.configured||!teacher.consent||avatar?.kind!=='image')return;
    const controller=new AbortController();setPreparing(true);
    void api(`/teachers/${teacher.id}/prepare-avatar`,{method:'POST',signal:controller.signal})
      .catch(()=>{}).finally(()=>{if(!controller.signal.aborted)setPreparing(false);});
    return ()=>controller.abort();
  },[teacher.id,teacher.avatar_asset_id,teacher.consent,avatar?.kind,config?.avatar.configured]);
  const active=useRef(false),generation=useRef(0),s=useRef<Session|null>(null),speaker=useRef(new Speaker()),abort=useRef<AbortController|null>(null),cleanup=useRef<()=>void>(()=>{}),timer=useRef<ReturnType<typeof setTimeout>|null>(null);
  const route=useRef<'browser'|'gpu'>('browser');
  const [routeLabel,setRouteLabel]=useState('浏览器识别'),[fallbackNote,setFallbackNote]=useState('');
  const listenRef=useRef<()=>void>(()=>{});
  speaker.current.onChange=value=>{setSpeaking(value);if(value)setPhase('speaking');};
  speaker.current.onVideo=setVideo;
  speaker.current.onPlaybackBlocked=setPlaybackBlocked;
  speaker.current.onWaiting=()=>{if(active.current)setPhase('synthesizing');};
  const valid=(g:number)=>active.current&&g===generation.current;
  function clearInput(){if(timer.current)clearTimeout(timer.current);timer.current=null;cleanup.current();cleanup.current=()=>{};setPartial('');}
  function halt(){active.current=false;generation.current++;clearInput();abort.current?.abort();speaker.current.stop();}
  async function settle(){const old=s.current;if(!old)return;for(let i=0;i<3;i++){const fresh=await api<Session>(`/sessions/${old.id}`);try{const next=await post<Session>(`/sessions/${old.id}/action`,{revision:fresh.revision,action:'pause'});s.current=next;setSession(next);return;}catch(e){if(i===2)throw e;}}}
  function fail(e:unknown){halt();setPhase('paused');setError((e as Error).message||'对话中断，请重新开始。');void settle().catch(()=>{});}
  async function stop(){halt();setPhase('paused');try{await settle();}catch(e){setError((e as Error).message);}}
  useEffect(()=>()=>{halt();const old=s.current;if(old)void api<Session>(`/sessions/${old.id}`).then(f=>post(`/sessions/${old.id}/action`,{revision:f.revision,action:'pause'})).catch(()=>{});},[]);
  function again(g:number){if(valid(g))timer.current=setTimeout(()=>{if(valid(g))listenRef.current();},500);}
  async function answer(text:string,g:number){
    if(!valid(g)||!text.trim())return;clearInput();setDraft('');setPhase('thinking');
    try{
      if(!s.current){const created=await post<Session>('/sessions',{teacher_id:teacher.id,course_id:null});if(!valid(g))return;s.current=created;}
      const old=s.current!;setSession({...old,state:'ANSWERING',messages:[...old.messages,{role:'user',text}]});
      abort.current=new AbortController();
      const result=await api<{session:Session;answer:string;speech_text?:string}>(`/sessions/${old.id}/ask`,{method:'POST',body:JSON.stringify({revision:old.revision,question:text}),signal:abort.current.signal});
      if(!valid(g))return;s.current=result.session;setSession(result.session);setPhase(voice==='gpu'?'synthesizing':'speaking');
      await speaker.current.play(result.speech_text ?? result.answer,teacher.id,voice,()=>{void (async()=>{
        if(!valid(g))return;
        try{const next=await post<Session>(`/sessions/${result.session.id}/action`,{revision:result.session.revision,action:'answer_done'});if(!valid(g))return;s.current=next;setSession(next);again(g);}catch(e){if(valid(g))fail(e);}
      })();},e=>{if(valid(g))fail(e);});
    }catch(e){if(valid(g))fail(e);}
  }
  async function listen(){
    const g=generation.current;if(!valid(g))return;clearInput();setPhase('listening');
    if(route.current==='browser'){
      let submitted=false,heardSpeech=false,lastPreview='',watchdog:ReturnType<typeof setTimeout>|undefined;
      const fallback=(reason:string,permission=false)=>{
        if(!valid(g)||submitted)return;submitted=true;clearInput();
        if(permission){fail(new Error('麦克风或语音权限被拒绝，请在浏览器设置中允许后重试。GPU 识别也需要麦克风权限；可先用文字提问。'));return;}
        if(input!=='auto'||!config?.asr.configured){fail(new Error(`${reason}。${input==='auto'?'GPU 兜底尚未配置':'当前为仅浏览器模式'}，请使用文字提问或稍后重试。`));return;}
        // Sticky for this conversation: never oscillate or submit late browser transcripts.
        generation.current++;route.current='gpu';setRouteLabel('GPU 识别 · 自动兜底');
        setFallbackNote(`${reason}，已切换 GPU 识别。请重新说一遍刚才的问题。`);
        void listen();
      };
      const Recognition=(window as any).SpeechRecognition||(window as any).webkitSpeechRecognition;
      if(!Recognition){fallback('浏览器不支持语音识别');return;}
      let rec:any;
      const arm=(ms:number)=>{clearTimeout(watchdog);watchdog=setTimeout(()=>fallback('浏览器识别响应超时'),ms);};
      try{
        rec=new Recognition();rec.lang='zh-CN';rec.interimResults=true;rec.continuous=false;
        cleanup.current=()=>{clearTimeout(watchdog);rec.onstart=null;rec.onspeechstart=null;rec.onresult=null;rec.onerror=null;rec.onend=null;try{rec.abort();}catch{}};
        rec.onstart=()=>clearTimeout(watchdog); // Silence is not a service failure.
        rec.onspeechstart=()=>{if(valid(g)){heardSpeech=true;arm(20000);}};
        rec.onresult=(event:any)=>{if(!valid(g)||submitted)return;let final='',preview='';for(let i=event.resultIndex;i<event.results.length;i++){if(event.results[i].isFinal)final+=event.results[i][0].transcript;else preview+=event.results[i][0].transcript;}lastPreview=preview.trim();setPartial(preview);if(final.trim()){submitted=true;void answer(final.trim(),g);}else arm(15000);};
        rec.onerror=(event:any)=>{if(!valid(g)||submitted)return;if(event.error==='no-speech'){clearTimeout(watchdog);return;}fallback(`浏览器识别失败（${event.error}）`,event.error==='not-allowed'||event.error==='audio-capture');};
        rec.onend=()=>{
          clearTimeout(watchdog);if(!valid(g)||submitted)return;
          if(lastPreview){submitted=true;void answer(lastPreview,g);}
          else if(heardSpeech)fallback('已检测到说话，但浏览器没有返回识别文字');
          else again(g);
        };
        arm(20000);rec.start();
      }catch(e){fallback('浏览器识别无法启动',(e as Error).name==='NotAllowedError');}return;
    }
    // GPU input: echo-cancelled microphone, end a turn after one second of silence.
    try{
      const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
      if(!valid(g)){stream.getTracks().forEach(t=>t.stop());return;}
      const context=new AudioContext();cleanup.current=()=>{stream.getTracks().forEach(t=>t.stop());void context.close();};await context.resume();
      if(!valid(g)){stream.getTracks().forEach(t=>t.stop());await context.close();return;}
      const analyser=context.createAnalyser();analyser.fftSize=2048;context.createMediaStreamSource(stream).connect(analyser);
      const rec=new MediaRecorder(stream),chunks:BlobPart[]=[];let speech=false,lastSound=performance.now(),began=lastSound,interval:ReturnType<typeof setInterval>;
      const dispose=()=>{clearInterval(interval);stream.getTracks().forEach(t=>t.stop());void context.close();};
      cleanup.current=()=>{rec.onstop=null;if(rec.state!=='inactive')rec.stop();dispose();};
      rec.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};
      rec.onerror=()=>fail(new Error('录音失败，请检查麦克风。'));
      rec.onstop=()=>{dispose();cleanup.current=()=>{};if(!valid(g))return;if(!speech){again(g);return;}
        setPhase('thinking');abort.current=new AbortController();const form=new FormData();form.append('file',new Blob(chunks,{type:rec.mimeType}),rec.mimeType.includes('mp4')?'voice.mp4':'voice.webm');
        void api<{text:string}>('/transcribe',{method:'POST',body:form,signal:abort.current.signal}).then(r=>{if(valid(g)){if(r.text.trim())void answer(r.text,g);else again(g);}}).catch(e=>{if(valid(g))fail(new Error('GPU 识别失败：'+(e as Error).message+'。请稍后重试或使用文字提问。'));});};
      rec.start();const samples=new Float32Array(analyser.fftSize);
      interval=setInterval(()=>{analyser.getFloatTimeDomainData(samples);const rms=Math.sqrt(samples.reduce((sum,x)=>sum+x*x,0)/samples.length),now=performance.now();if(rms>.018){speech=true;lastSound=now;}if((speech&&now-lastSound>1000)||now-began>20000){if(rec.state==='recording')rec.stop();}},100);
    }catch(e){if(valid(g))fail(new Error('GPU 录音无法启动：'+(e as Error).message+'。请检查麦克风权限，或使用文字提问。'));}
  }
  listenRef.current=()=>void listen();
  async function begin(){halt();route.current=input==='gpu'?'gpu':'browser';setRouteLabel(route.current==='gpu'?'GPU 识别':'浏览器识别');setFallbackNote('');const g=generation.current;setError('');try{await settle();if(g!==generation.current)return;active.current=true;void listen();}catch(e){fail(e);}}
  async function interrupt(){halt();const g=generation.current;setPhase('paused');try{await settle();if(g!==generation.current)return;active.current=true;void listen();}catch(e){fail(e);}}
  async function send(){const text=draft.trim();if(!text)return;halt();const g=generation.current;setError('');try{await settle();if(g!==generation.current)return;active.current=true;void answer(text,g);}catch(e){fail(e);}}
  return <section className="realtime panel">
    <div className="realtime-heading"><div><h2>和{teacher.name}实时对话</h2><p>说完一句自动发送，老师回答后继续聆听。优先参考老师知识库，也可以自由聊天；未引用资料时会显示文字提示。</p></div><span className="pill" role="status">{preparing&&phase==='idle'?'正在预备老师形象，下次对话可复用':names[phase]}</span></div>
    <div className="realtime-grid"><div className="realtime-stage"><Avatar video={video} url={avatar?.url} kind={avatar?.kind} speaking={speaking} gesture={phase==='thinking'?'think':'idle'}/><h3>{teacher.name}</h3><p className="live-partial">{partial||({listening:'请说话，我在听…',thinking:'正在组织回答…',speaking:'想插话时，点击“打断并说话”',synthesizing:'正在准备下一段声音与画面，可以点击打断取消',idle:'点击开始对话，允许使用麦克风',paused:'可以重新开始，或输入文字'}[phase])}</p>
      {playbackBlocked&&<div className="playback-prompt" role="status"><span>声音和画面已准备好，手机浏览器需要你点击后播放。</span><button className="primary" onClick={()=>speaker.current.resume()}>点击播放老师声音与动画</button></div>}{error&&<p className="error" role="alert">{error}</p>}
      <div className="actions"><button className="primary" onClick={()=>void (active.current?stop():begin())}>{active.current?<><Square size={16}/>结束对话</>:<><Mic size={16}/>开始实时对话</>}</button><button disabled={!['thinking','speaking','synthesizing'].includes(phase)} onClick={()=>void interrupt()}><Hand size={16}/>打断并说话</button></div>

    </div><div className="realtime-conversation"><h3 className="conversation-title">课堂对话</h3><div className={`messages ${session?.messages.length?'has-messages':'is-empty'}`} aria-live="polite">{!session?.messages.length&&<p>可以先问一个知识点，也可以聊聊你没听懂的地方。</p>}{session?.messages.map((m,i)=><div className={`message ${m.role}`} key={i}><small>{m.role==='user'?'你':teacher.name}</small><div className="message-body">{m.text}</div>{m.sources?.length?<details className="sources"><summary>{m.sources.length} 条资料依据</summary>{m.sources.map(x=><p key={x.id}><b>{x.title}</b><br/>{x.text}</p>)}</details>:null}</div>)}</div><form className="chat-input" onSubmit={e=>{e.preventDefault();void send();}}><textarea aria-label="实时对话文字" placeholder="也可以打字，发送后老师会回答…" value={draft} onChange={e=>setDraft(e.target.value)}/><button className="primary" disabled={!draft.trim()}><Send size={16}/>发送</button></form></div></div>
    <details className="realtime-settings"><summary>语音与识别设置</summary>      <div className="two-col"><label>语音识别<select aria-label="实时识别方式" disabled={active.current} value={input} onChange={e=>setInput(e.target.value)}><option value="auto">优先浏览器 · GPU 自动兜底</option><option value="browser">仅浏览器识别</option><option value="gpu" disabled={!config?.asr.configured}>GPU 识别{!config?.asr.configured?' · 待连接':''}</option></select></label><label>老师声音<select disabled={active.current} value={voice} onChange={e=>setVoice(e.target.value)}><option value="browser">浏览器演示声音</option><option value="gpu" disabled={!config?.tts.configured}>老师克隆声音{!config?.tts.configured?' · 待连接':''}</option></select></label></div>
      <p className="asr-route" data-testid="asr-route" data-route={routeLabel}>北京简融易数科技</p>{fallbackNote&&<p role="status">{fallbackNote}</p>}

    </details>
  </section>;
}
