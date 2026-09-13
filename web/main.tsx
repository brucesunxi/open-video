import React,{useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {BookOpen,GraduationCap,Library,Presentation,Settings2,Plus,ArrowUpRight,ArrowRight,Play,Pause,ChevronLeft,ChevronRight,Download,Send,Mic,Square,FileText,Upload,Check,CheckCircle2,Volume2,RotateCcw,Monitor,Server,ShieldCheck,X,Quote,Sparkles,FolderOpen} from 'lucide-react';
import {api,post,type Teacher,type Knowledge,type Course,type Session,type Asset,type Config,type Source} from './types';
import {Avatar} from './Avatar';
import {Speaker} from './speech';
import {Realtime} from './Realtime';
import {TeacherMaterials} from './TeacherMaterials';
import './style.css';

const labels:Record<string,string>={READY:'准备就绪',LECTURING:'正在讲课',PAUSED:'已暂停',ANSWERING:'回答问题',FINISHED:'本课已完成'};
const pages=[['classroom','互动课堂',Monitor],['teachers','教师与素材',GraduationCap],['knowledge','教学知识库',Library],['courses','课程与课件',Presentation],['settings','服务与部署',Settings2]] as const;
const blank:Teacher={id:'',name:'',subject:'',bio:'',style:'',voice_profile_id:'',avatar_asset_id:'',consent:false};

function SchoolBrand(){
  return <div className="brand school-brand"><span className="brand-icon" title="临时书本标志，非学校正式校徽"><BookOpen size={23}/></span><div>星河实验小学<span>北京市朝阳区 · 智慧课堂</span></div></div>;
}

function App(){
  const [authorized,setAuthorized]=useState<boolean|null>(null),[token,setToken]=useState(''),[username,setUsername]=useState(''),[authMode,setAuthMode]=useState('password');
  const [page,setPage]=useState('classroom'),[teachers,setTeachers]=useState<Teacher[]>([]),[teacherId,setTeacherId]=useState('');
  const [docs,setDocs]=useState<Knowledge[]>([]),[courses,setCourses]=useState<Course[]>([]),[assets,setAssets]=useState<Asset[]>([]);
  const [config,setConfig]=useState<Config|null>(null),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
  const [session,setSession]=useState<Session|null>(null),[courseId,setCourseId]=useState(''),[question,setQuestion]=useState('');
  const [speaking,setSpeaking]=useState(false),[voice,setVoice]=useState('browser'),[caption,setCaption]=useState(''),[recording,setRecording]=useState(false);
  const [editingTeacher,setEditingTeacher]=useState<Teacher|null>(null),[editCourse,setEditCourse]=useState<Course|null>(null);
  const [docTitle,setDocTitle]=useState(''),[docText,setDocText]=useState(''),[courseTitle,setCourseTitle]=useState(''),[selectedDocs,setSelectedDocs]=useState<string[]>([]);
  const [sessions,setSessions]=useState<Session[]>([]);
  const [classMode,setClassMode]=useState('lesson');
  const [playbackBlocked,setPlaybackBlocked]=useState(false);
  const [video,setVideo]=useState<HTMLVideoElement|null>(null);
  const [preparingSpeech,setPreparingSpeech]=useState(false);
  const speaker=useRef(new Speaker()),epoch=useRef(0),current=useRef<Session|null>(null),askAbort=useRef<AbortController|null>(null),recorder=useRef<MediaRecorder|null>(null),media=useRef<MediaStream|null>(null),currentTeacher=useRef(teacherId);
  const teacher=teachers.find(t=>t.id===teacherId),course=courses.find(c=>c.id===(session?.course_id||courseId));
  const clonedVoiceReady=Boolean(config?.tts.configured&&teacher?.consent&&teacher?.voice_profile_id);
  useEffect(()=>{setVoice(clonedVoiceReady?'gpu':'browser');},[teacherId,clonedVoiceReady]);
  const slide=course?.slides[session?.slide_index||0],avatar=assets.find(a=>a.id===teacher?.avatar_asset_id);
  current.current=session;
  currentTeacher.current=teacherId;
  speaker.current.onChange=value=>{setSpeaking(value);if(value)setPreparingSpeech(false);};
  speaker.current.onWaiting=()=>setPreparingSpeech(true);
  speaker.current.onVideo=setVideo;
  speaker.current.onPlaybackBlocked=setPlaybackBlocked;
  function report(e:unknown){setError((e as Error).message||'操作失败，请重试。');}
  async function run(fn:()=>Promise<void>){setBusy(true);setError('');try{await fn();}catch(e){report(e);}finally{setBusy(false);}}
  function stop(){epoch.current++;askAbort.current?.abort();speaker.current.stop();setPreparingSpeech(false);setCaption('');}
  async function refresh(id=teacherId){
    if(!id)return;
    const [d,c,a,s]=await Promise.all([api<Knowledge[]>(`/teachers/${id}/documents`),api<Course[]>(`/teachers/${id}/courses`),api<Asset[]>(`/teachers/${id}/assets`),api<Session[]>(`/teachers/${id}/sessions`)]);
    if(currentTeacher.current!==id)return;
    setDocs(d);setCourses(c);setAssets(a);setSessions(s);setSelectedDocs(d.filter(x=>x.approved).map(x=>x.id));
  }
  async function bootstrap(){
    const [t,c]=await Promise.all([api<Teacher[]>('/teachers'),api<Config>('/config')]);setTeachers(t);setConfig(c);
    const saved=localStorage.getItem('teacherId');setTeacherId(t.find(x=>x.id===saved)?.id||t[0]?.id||'');
  }
  useEffect(()=>{api('/auth').then(v=>{setAuthMode(v.mode||'password');setAuthorized(v.authorized);}).catch(report);return()=>{speaker.current.stop();media.current?.getTracks().forEach(t=>t.stop());};},[]);
  useEffect(()=>{if(authorized)void run(bootstrap);},[authorized]);
  useEffect(()=>{
    stop();setSession(null);setCourseId('');setEditCourse(null);setEditingTeacher(null);setQuestion('');setDocs([]);setCourses([]);setAssets([]);setSessions([]);
    if(teacherId){localStorage.setItem('teacherId',teacherId);void run(()=>refresh(teacherId));}
  },[teacherId]);
  useEffect(()=>{if(notice){const t=setTimeout(()=>setNotice(''),4000);return()=>clearTimeout(t);}},[notice]);
  useEffect(()=>{if(!courseId&&courses.length)setCourseId(courses.find(c=>c.status==='published')?.id||'');},[courses]);
  // Reloading restores progress but never auto-plays audio without a user gesture.
  async function restore(s:Session){stop();const live=await api<Session>(`/sessions/${s.id}`);let paused=live;
    if(!['FINISHED','READY','PAUSED'].includes(live.state))paused=await post(`/sessions/${live.id}/action`,{revision:live.revision,action:'pause'});
    setSession(paused);setCourseId(paused.course_id||'');setNotice('已恢复到上次课件页，点击继续即可讲课。');}
  async function ensureSession(){if(current.current&&current.current.state!=='FINISHED')return current.current;
    const s=await post<Session>('/sessions',{teacher_id:teacherId,course_id:courseId||null});setSession(s);current.current=s;return s;}
  async function perform(action:string,s=current.current){if(!s)return null;const next=await post<Session>(`/sessions/${s.id}/action`,{revision:s.revision,action});if(current.current?.id!==s.id||currentTeacher.current!==s.teacher_id)return null;setSession(next);current.current=next;return next;}
  async function pause(){stop();const s=current.current;if(!s||s.state==='FINISHED')return;for(let i=0;i<3;i++){const fresh=await api<Session>(`/sessions/${s.id}`);if(fresh.state==='FINISHED')return;try{await perform('pause',fresh);return;}catch(e){if(i===2)throw e;}}}
  function narrate(s:Session){
    const c=courses.find(x=>x.id===s.course_id);if(!c||s.state!=='LECTURING')return;
    const text=c.slides[s.slide_index].narration;setCaption(text);const generation=epoch.current;
    if(voice==='silent')return; // Reader controls page changes in silent mode.
    void speaker.current.play(text,teacherId,voice,()=>{
      if(generation!==epoch.current)return;
      setPreparingSpeech(false);
      void run(async()=>{const next=await perform('next',current.current);if(next) narrate(next);});
    },e=>{report(e);void pause().catch(report);},true);
  }
  async function start(){stop();const s=await ensureSession();const next=await perform(s.state==='READY'?'start':'resume',s);if(next)narrate(next);}
  async function flip(direction:string){stop();const s=await ensureSession();const next=await perform(direction,s);if(next)narrate(next);}
  async function ask(){
    if(!question.trim())return;stop();const generation=epoch.current;const text=question.trim();setQuestion('');
    const s=await ensureSession();askAbort.current=new AbortController();
    // Optimistic question display, authoritative revision comes from server response.
    setSession({...s,state:'ANSWERING',messages:[...s.messages,{role:'user',text}]});
    try{
      const result=await api<{session:Session;answer:string;speech_text?:string}>(`/sessions/${s.id}/ask`,{method:'POST',body:JSON.stringify({revision:s.revision,question:text}),signal:askAbort.current.signal});
      if(generation!==epoch.current)return;
      setSession(result.session);current.current=result.session;setCaption(result.answer);
      void speaker.current.play(result.speech_text ?? result.answer,teacherId,voice,()=>{if(generation===epoch.current){setPreparingSpeech(false);void run(async()=>{await perform('answer_done');});}},e=>{report(e);void pause().catch(report);});
    }catch(e){if(generation===epoch.current){setSession(await api(`/sessions/${s.id}`));throw e;}}
  }
  async function microphone(){
    if(recording){recorder.current?.stop();setRecording(false);return;}
    if(!config?.asr.configured)throw new Error('GPU 语音识别尚未连接，请先用文字提问。');
    await pause();const gen=epoch.current;
    const stream=await navigator.mediaDevices.getUserMedia({audio:true});media.current=stream;
    const rec=new MediaRecorder(stream);recorder.current=rec;const chunks:BlobPart[]=[];
    rec.ondataavailable=e=>chunks.push(e.data);
    rec.onstop=()=>{stream.getTracks().forEach(t=>t.stop());setRecording(false);void run(async()=>{
      const form=new FormData();form.append('file',new Blob(chunks,{type:rec.mimeType}),'recording.webm');
      const result=await api('/transcribe',{method:'POST',body:form});if(gen===epoch.current)setQuestion(result.text);
    });};rec.start();setRecording(true);setTimeout(()=>{if(rec.state==='recording')rec.stop();},60000);
  }
  function switchPage(p:string){if(page==='classroom'&&current.current&&current.current.state!=='FINISHED')void pause().catch(report);setPage(p);}

  if(authorized===false)return <div className="login"><SchoolBrand/><h1>登录教师工作台</h1><p>{authMode==='password'?'使用演示账号登录，开始你的教学体验。':'请输入工作台访问令牌。'}</p><form onSubmit={e=>{e.preventDefault();void run(async()=>{await post('/login',authMode==='password'?{username,password:token}:{token});setToken('');setError('');setAuthorized(true);});}}>{authMode==='password'&&<label>用户名<input required autoComplete="username" maxLength={80} aria-label="用户名" value={username} onChange={e=>setUsername(e.target.value)}/></label>}<label>{authMode==='password'?'密码':'访问令牌'}<input required type="password" maxLength={256} autoComplete="current-password" aria-label={authMode==='password'?'密码':'访问令牌'} value={token} onChange={e=>setToken(e.target.value)}/></label><button className="primary" disabled={busy}>登录 <ArrowRight size={16}/></button></form>{error&&<p role="alert" className="error">{error}</p>}</div>;
  return <div className="app">
    <aside className="sidebar"><SchoolBrand/>
      <div className="workspace-label">我的教学空间 <span>LOCAL</span></div>
      <nav>{pages.map(([id,label,Icon])=><button key={id} disabled={busy} className={page===id?'active':''} onClick={()=>switchPage(id)}><Icon size={19}/>{label}{page===id&&<i/>}</button>)}</nav>
      <div className="side-note"><span className="small-label">让知识拥有温度</span><p>一个老师，一种风格。<br/>从一份讲义，开始一堂课。</p><div className="tiny-book"><BookOpen size={28}/><span>LEARN<br/>TOGETHER</span></div></div>
      <div className="teacher-switch"><div className="initial">{teacher?.name[0]||'师'}</div><div><small>当前教师</small><select disabled={busy} aria-label="切换教师" value={teacherId} onChange={e=>setTeacherId(e.target.value)}>{!teachers.length&&<option value="">尚未创建</option>}{teachers.map(t=><option value={t.id} key={t.id}>{t.name}</option>)}</select></div></div>
    </aside>
    <div className="main"><header><div><span>工作空间</span><ChevronRight size={14}/><strong>{pages.find(x=>x[0]===page)?.[1]}</strong></div><div className="header-right"><span className="status-dot"/>本地工作台 <span className="divider"/> <span className="mode-tag">{config?.llm.configured?'模型已配置':'资料引用模式'}</span>{config?.auth_enabled&&<button disabled={busy} onClick={()=>void run(async()=>{stop();setClassMode('lesson');await post('/logout');setToken('');setAuthorized(false);})}>退出登录</button>}</div></header>
      <main>
        <div className="page-title"><div><div className="eyebrow">YOUR TEACHING WORKSPACE</div><h1>{({classroom:'把一堂好课，带到眼前',teachers:'每位老师，都有自己的表达',knowledge:'让每一次回答，都有依据',courses:'把知识组织成一堂好课',settings:'连接你的教学引擎'} as Record<string,string>)[page]}</h1><p>{({classroom:'讲课、提问、继续探索。知识与表达，在这里相遇。',teachers:'整理老师的经历、教学特点、声音与形象素材。',knowledge:'先导入，再审核。只有已审核的资料参与问答和课程。',courses:'从讲义提炼草稿，审核讲稿，再发布与导出。',settings:'本地运行业务与课堂，GPU 服务器提供独立的模型能力。'} as Record<string,string>)[page]}</p></div>
          {page==='teachers'&&<button disabled={busy} className="primary" onClick={()=>setEditingTeacher({...blank})}><Plus size={16}/>添加老师</button>}
          {page==='classroom'&&teacher&&<button onClick={()=>switchPage('courses')}><Presentation size={16}/>管理课程<ArrowUpRight size={15}/></button>}
        </div>
        {!teachers.length&&page!=='settings'&&!editingTeacher ? <div className="welcome panel"><div className="welcome-art"><Avatar speaking={false} gesture="idle"/></div><div><span className="pill">从这里开始</span><h2>你的第一位虚拟教师</h2><p>准备老师的讲话视频、个人介绍和课程讲义。<br/>也可以先使用示例老师，体验完整的教学流程。</p><div className="actions"><button className="primary" disabled={busy} onClick={()=>void run(async()=>{await post('/demo');await bootstrap();setNotice('示例老师和课程已准备好。');})}>体验示例课堂<ArrowRight size={16}/></button><button onClick={()=>{setPage('teachers');setEditingTeacher({...blank});}}>创建我的老师</button></div><small>示例角色与浏览器声音仅用于演示，不代表老师克隆效果。</small></div></div>:null}

        {page==='classroom'&&teacher&&<div className="class-mode"><button className={classMode==='lesson'?'primary':''} onClick={()=>setClassMode('lesson')}>讲课与插问</button><button className={classMode==='realtime'?'primary':''} onClick={()=>{void pause().catch(report);setClassMode('realtime');}}>实时对话</button></div>}
        {page==='classroom'&&teacher&&classMode==='realtime'&&<Realtime key={teacher.id} teacher={teacher} avatar={avatar} config={config}/>}
        {page==='classroom'&&teacher&&classMode==='lesson'&&<>
          <div className="class-toolbar"><div className="select-course"><Presentation size={18}/><select aria-label="选择课堂课程" value={courseId} disabled={busy} onChange={e=>{stop();const old=current.current;if(old&&old.state!=='FINISHED')void perform('pause',old).catch(report);setSession(null);current.current=null;setCourseId(e.target.value);}}><option value="">自由问答 · 全部已审核资料</option>{courses.filter(c=>c.status==='published').map(c=><option key={c.id} value={c.id}>{c.title} · v{c.version}</option>)}</select></div><span className="subtle">{course?.slides.length||0} 页课件</span><div className="spacer"/><select className="voice-select" aria-label="声音模式" value={voice} onChange={e=>{void pause().catch(report);setVoice(e.target.value);}}><option value="browser">浏览器演示声音</option><option value="silent">静音阅读</option><option value="gpu" disabled={!config?.tts.configured}>老师克隆声音{!config?.tts.configured?' · 待连接':''}</option></select></div>
          <div className="class-grid"><section className="stage-column"><div className="stage panel"><div className="stage-top"><span><span className={`status-dot ${speaking?'pulse':''}`}/>{preparingSpeech?'正在生成老师声音与画面':session?labels[session.state]:'课堂准备中'}</span><span className="pill pale"><ShieldCheck size={13}/>知识库限定</span></div>
            <div className="teaching-scene"><div className="presenter"><Avatar video={video} url={avatar?.url} kind={avatar?.kind} speaking={speaking} gesture={session?.state==='ANSWERING'?'think':slide?.gesture||'idle'}/><div className="presenter-name">{teacher.name}<small>{teacher.subject||'教师'}</small></div></div>
              <div className="slide-card"><span className="slide-kicker">{course?'一起学习 / '+String((session?.slide_index||0)+1).padStart(2,'0'):'一起探索'}</span><h2>{slide?.title||'每一个好问题，都是学习的开始。'}</h2><div className="slide-rule"/>{slide?<ul>{slide.bullets.map((b,i)=><li key={i}><span>{String(i+1).padStart(2,'0')}</span>{b}</li>)}</ul>:<p className="empty-copy">在右侧提出问题，老师会从已审核的教学资料中寻找依据。<br/><br/>选择一门已发布的课程，也可以开始连续讲课。</p>}<div className="slide-footer"><BookOpen size={14}/>{course?.title||'教学知识库'}<span>{course?`${(session?.slide_index||0)+1} / ${course.slides.length}`:'Q & A'}</span></div></div>
            </div><div className="caption">{caption||'准备好了，就开始今天的学习吧。'}</div>
            {playbackBlocked&&<div className="playback-prompt" role="status"><span>声音和画面已准备好，手机浏览器需要你点击后播放。</span><button className="primary" onClick={()=>speaker.current.resume()}>点击播放老师声音与动画</button></div>}<div className="stage-controls"><button className="icon-btn" title="上一页" aria-label="上一页" disabled={busy||!course||!session||session.state==='FINISHED'} onClick={()=>void run(()=>flip('previous'))}><ChevronLeft/></button>
              <button className="primary play-button" disabled={(!course||busy)&&session?.state!=='ANSWERING'} onClick={()=>void run(async()=>{if(speaking||session?.state==='LECTURING'||session?.state==='ANSWERING')await pause();else await start();})}>{speaking||session?.state==='LECTURING'||session?.state==='ANSWERING'?<><Pause size={16}/>暂停</>:<><Play size={16}/>{session?.state==='PAUSED'?'继续讲课':session?.state==='FINISHED'?'重新开始':'开始讲课'}</>}</button>
              <button className="icon-btn" title="下一页" aria-label="下一页" disabled={busy||!course||session?.state==='FINISHED'} onClick={()=>void run(()=>flip('next'))}><ChevronRight/></button><span className="control-divider"/><button className="text-btn" disabled={busy||!session} onClick={()=>void run(async()=>{stop();if(session&&session.state!=='FINISHED')await perform('finish');setSession(null);current.current=null;})}><RotateCcw size={15}/>新会话</button>
              {course&&<a className="icon-btn export-button" title="下载 PPTX" aria-label="下载 PPTX" href={`/api/courses/${course.id}/export.pptx`}><Download size={18}/></a>}
            </div>
          </div><div className="stage-meta"><span><Volume2 size={14}/>{voice==='browser'?'当前使用浏览器演示声音，不是老师克隆音色':voice==='silent'?'静音阅读 · 使用翻页按钮浏览':'通过 GPU 服务合成老师声音'}</span><span>{video?'老师说话动画':preparingSpeech?'动画准备中':avatar?.kind==='vrm'?'VRM 角色 · 基础动作':avatar?.kind==='image'?(voice==='gpu'?'老师参考形象 · 播放时显示动画':'参考照片 · 浏览器声音不驱动口型'):'本地演示角色'}</span></div>
          {sessions.some(s=>s.state!=='FINISHED')&&!session&&<div className="resume-card"><div><RotateCcw size={17}/><span>上次课堂进度已保存</span></div><button className="text-btn" onClick={()=>void run(()=>restore(sessions.find(s=>s.state!=='FINISHED')!))}>恢复课堂<ArrowRight size={14}/></button></div>}
          {avatar?.kind==='image'&&voice==='browser'&&clonedVoiceReady&&<div className="resume-card"><span>启用老师克隆声音，讲课时同步播放人物动画。</span><button onClick={()=>void run(async()=>{await pause();setVoice('gpu');setNotice('已启用老师声音与动画，点击继续讲课。');})}>启用声音与动画</button></div>}
          <div className="lesson-tip"><span className="tip-icon"><Sparkles size={20}/></span><div><strong>把问题留给好奇心</strong><p>讲课时可以随时提问。回答结束后，点击“继续讲课”回到当前知识点。</p></div></div></section>
          <aside className="chat panel"><div className="chat-title"><div><h3>课堂对话</h3><span>跟随资料，深入一点</span></div><span className="pill">{docs.filter(d=>d.approved).length} 份资料</span></div>
            <div className="messages" aria-live="polite">{!session?.messages.length?<div className="chat-empty"><span><Quote size={24}/></span><h3>你好，我们开始吧</h3><p>可以问一个问题，<br/>也可以先听老师讲一讲。</p>{['这节课主要讲什么？','蒸发是什么？','杯壁的水珠从哪里来？'].map(q=><button key={q} onClick={()=>setQuestion(q)}>{q}<ArrowUpRight size={14}/></button>)}</div>:session.messages.map((m,i)=><div key={i} className={`message ${m.role}`}><small>{m.role==='user'?'你':teacher.name}</small><div className="message-body">{m.text}</div>{m.sources?.length?<details className="sources"><summary><FileText size={12}/>{m.sources.length} 条资料依据</summary>{m.sources.map((s:Source)=><div key={s.id}><b>{s.title} · {s.page?`第 ${s.page} 页`:`段落 ${s.section}`}</b><p>{s.text}</p></div>)}</details>:null}</div>)}{busy&&session?.state==='ANSWERING'&&<p className="thinking">正在查阅课程资料…</p>}</div>
            <form className="chat-input" onSubmit={e=>{e.preventDefault();void run(ask);}}><textarea aria-label="课堂问题" placeholder="输入问题，和老师聊一聊…" value={question} onChange={e=>setQuestion(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();if(!busy)void run(ask);}}}/><div><span>Enter 发送 · Shift + Enter 换行</span><button type="button" className={`icon-btn ${recording?'recording':''}`} title={recording?'结束录音':'语音提问'} aria-label="语音提问" onClick={()=>void run(microphone)}>{recording?<Square size={16}/>:<Mic size={17}/>}</button><button className="send" aria-label="发送问题" disabled={busy||!question.trim()}><Send size={17}/></button></div></form>
          </aside></div>
        </>}

        {page==='teachers'&&(teacher||editingTeacher)&&<div className="editor-grid"><section className="panel form-panel"><div className="section-title"><h2>{editingTeacher?.id===''?'添加老师':'教师档案'}</h2><GraduationCap size={22}/></div>
          <form onSubmit={e=>{e.preventDefault();void run(async()=>{const t=editingTeacher||teacher!;const saved=await api<Teacher>(t.id?`/teachers/${t.id}`:'/teachers',{method:t.id?'PUT':'POST',body:JSON.stringify(t)});await bootstrap();setTeacherId(saved.id);setEditingTeacher(null);setNotice('教师档案已保存。');});}}>
            <div className="two-col"><label>老师姓名<input required maxLength={60} value={(editingTeacher||teacher)?.name||''} onChange={e=>setEditingTeacher({...editingTeacher||teacher!,name:e.target.value})}/></label><label>学科 / 领域<input value={(editingTeacher||teacher)?.subject||''} onChange={e=>setEditingTeacher({...editingTeacher||teacher!,subject:e.target.value})}/></label></div>
            <label>个人介绍与教学经历<textarea rows={4} placeholder="记录经过确认的经历、教学背景与公开信息…" value={(editingTeacher||teacher)?.bio||''} onChange={e=>setEditingTeacher({...editingTeacher||teacher!,bio:e.target.value})}/></label>
            <label>教学特点<textarea rows={4} placeholder="例如：擅长用生活中的例子引导学生思考…" value={(editingTeacher||teacher)?.style||''} onChange={e=>setEditingTeacher({...editingTeacher||teacher!,style:e.target.value})}/></label>
            <label>声音档案 ID<input placeholder="GPU 语音服务建立档案后填写" value={(editingTeacher||teacher)?.voice_profile_id||''} onChange={e=>setEditingTeacher({...editingTeacher||teacher!,voice_profile_id:e.target.value})}/></label>
            <label>课堂形象<select value={(editingTeacher||teacher)?.avatar_asset_id||''} onChange={e=>setEditingTeacher({...editingTeacher||teacher!,avatar_asset_id:e.target.value})}><option value="">本地演示角色</option>{assets.filter(a=>['image','vrm'].includes(a.kind)).map(a=><option key={a.id} value={a.id}>{a.filename} · {a.kind==='vrm'?'VRM 动态角色':'静态参考图'}</option>)}</select></label>
            <fieldset className="avatar-gallery"><legend>选择老师形象</legend><p className="subtle">点击预览图选择，再保存档案。声音和教学资料保持不变。</p><div className="avatar-gallery-grid">{assets.filter(a=>a.kind==='image').map(a=><button type="button" key={a.id} className={`avatar-choice ${(editingTeacher||teacher)?.avatar_asset_id===a.id?'selected':''}`} aria-pressed={(editingTeacher||teacher)?.avatar_asset_id===a.id} onClick={()=>setEditingTeacher({...editingTeacher||teacher!,avatar_asset_id:a.id})}><img src={a.url} alt={(a.filename==='cartoon-teacher-v2.png'?'柔和写实（原版）':a.filename.replace(/\.[^.]+$/,''))} loading="lazy"/><span>{(a.filename==='cartoon-teacher-v2.png'?'柔和写实（原版）':a.filename.replace(/\.[^.]+$/,''))}</span><small>{(editingTeacher||teacher)?.avatar_asset_id===a.id?'已选择 · 保存后使用':'点击选择'}</small></button>)}</div></fieldset>
            <label className="check-label"><input type="checkbox" checked={(editingTeacher||teacher)?.consent||false} onChange={e=>setEditingTeacher({...editingTeacher||teacher!,consent:e.target.checked})}/>已获得老师对素材、声音及形象用于本项目的授权</label>
            <button className="primary" disabled={busy}><Check size={16}/>保存档案</button>
          </form></section>{teacher&&editingTeacher?.id!==''?<TeacherMaterials key={teacher.id} teacher={teacher} assets={assets} config={config} busy={busy} run={run} refresh={async()=>{await refresh();const t=await api<Teacher[]>('/teachers');setTeachers(t);setEditingTeacher(previous=>previous?{...previous,voice_profile_id:t.find(x=>x.id===previous.id)?.voice_profile_id||previous.voice_profile_id}:null);}}/>:<section className="panel form-panel"><h2>老师素材</h2><p className="empty-copy">先保存老师档案，再上传视频、声音和形象。</p></section>}</div>}

        {page==='knowledge'&&teacher&&<div className="editor-grid"><section className="panel form-panel"><div className="section-title"><h2>教学资料</h2><span className="pill">{docs.length} 份</span></div>{docs.length===0&&<div className="empty-copy">还没有教学资料。导入一份讲义，让老师有据可答。</div>}{docs.map(d=><div className="document-card" key={d.id}><div><FileText size={21}/><h3>{d.title}</h3><span className={`pill ${d.approved?'':'amber'}`}>{d.approved?'已审核':'待审核'}</span></div><p>{d.chunks.length} 个知识段落 · v{d.version}</p><details><summary>预览提取内容</summary>{d.chunks.map(c=><p className="document-text" key={c.id}><small>{c.page?`第 ${c.page} 页`:`段落 ${c.section}`}</small>{c.text}</p>)}</details>{!d.approved&&<button className="primary small" disabled={busy} onClick={()=>void run(async()=>{await post(`/documents/${d.id}/approve`);await refresh();})}><Check size={14}/>确认内容并审核</button>}</div>)}</section><section className="panel form-panel"><h2>导入新资料</h2><label className="dropzone"><Upload size={27}/><b>选择教学文档</b><span>TXT / MD / DOCX / 文字 PDF · 最大 15MB</span><input type="file" accept=".txt,.md,.docx,.pdf" disabled={busy} onChange={e=>{const f=e.target.files?.[0];if(f)void run(async()=>{const form=new FormData();form.append('file',f);await api(`/teachers/${teacherId}/documents/upload`,{method:'POST',body:form});await refresh();setNotice('已提取资料，请预览并审核。');});e.target.value='';}}/></label><div className="or">或直接粘贴文字</div><form onSubmit={e=>{e.preventDefault();void run(async()=>{await post('/documents',{teacher_id:teacherId,title:docTitle,text:docText});setDocTitle('');setDocText('');await refresh();});}}><label>资料名称<input required value={docTitle} onChange={e=>setDocTitle(e.target.value)} placeholder="例如：水的三态 · 第 1 课讲义"/></label><label>资料内容<textarea required rows={10} minLength={5} value={docText} onChange={e=>setDocText(e.target.value)} placeholder="粘贴老师确认过的知识内容…"/></label><button className="primary" disabled={busy}><Plus size={16}/>保存待审核资料</button></form><p className="footnote">教学风格请填写在教师档案。学科知识需要单独导入，避免把老师简介当成课程依据。</p></section></div>}

        {page==='courses'&&teacher&&<>
          {!editCourse?<div className="editor-grid"><section className="panel form-panel"><h2>我的课程</h2>{!courses.length&&<p className="empty-copy">从右侧选择资料，建立第一份课程草稿。</p>}{courses.map(c=><div className="course-row" key={c.id}><span className="course-icon"><Presentation size={24}/></span><div><h3>{c.title}</h3><p>{c.slides.length} 页 · v{c.version} · {c.status==='published'?'已发布':'草稿'}</p></div><button onClick={()=>setEditCourse(structuredClone(c))}>编辑 / 查看<ArrowRight size={14}/></button></div>)}</section><section className="panel form-panel"><h2>从讲义创建课件</h2><p className="subtle">将原文整理为可编辑草稿，保留来源与逐页讲稿。</p><form onSubmit={e=>{e.preventDefault();void run(async()=>{const c=await post<Course>('/courses',{teacher_id:teacherId,title:courseTitle,document_ids:selectedDocs});await refresh();setEditCourse(c);});}}><label>课程名称<input required placeholder="为这堂课起个名字" value={courseTitle} onChange={e=>setCourseTitle(e.target.value)}/></label><label>选择已审核资料</label><div className="doc-choices">{docs.filter(d=>d.approved).map(d=><label className="check-label" key={d.id}><input type="checkbox" checked={selectedDocs.includes(d.id)} onChange={e=>setSelectedDocs(e.target.checked?[...selectedDocs,d.id]:selectedDocs.filter(x=>x!==d.id))}/>{d.title}</label>)}{!docs.some(d=>d.approved)&&<p>请先到知识库导入并审核资料。</p>}</div><button className="primary" disabled={busy||!selectedDocs.length}><Presentation size={16}/>创建课程草稿</button></form><p className="footnote">当前按资料段落整理，最多生成前 12 页，不是完整的 AI 教案生成。发布前请检查讲解顺序与措辞。</p></section></div>:<div className="panel form-panel"><div className="section-title"><button className="text-btn" onClick={()=>setEditCourse(null)}><ChevronLeft size={16}/>返回课程列表</button><div className="actions"><a className="button" href={`/api/courses/${editCourse.id}/export.pptx`}><Download size={16}/>导出 PPTX</a>{editCourse.status==='draft'?<><button disabled={busy} onClick={()=>void run(async()=>{const c=await api<Course>(`/courses/${editCourse.id}`,{method:'PUT',body:JSON.stringify(editCourse)});setEditCourse(c);await refresh();setNotice('草稿已保存。');})}>保存草稿</button><button className="primary" disabled={busy} onClick={()=>void run(async()=>{await api(`/courses/${editCourse.id}`,{method:'PUT',body:JSON.stringify(editCourse)});const c=await post<Course>(`/courses/${editCourse.id}/publish`);await refresh();setEditCourse(c);setNotice('课程已发布，可以开始讲课。');})}><Check size={16}/>审核并发布</button></>:<button onClick={()=>void run(async()=>{const c=await post<Course>(`/courses/${editCourse.id}/clone`);await refresh();setEditCourse(c);})}>复制为新版本</button>}</div></div><label>课程名称<input value={editCourse.title} disabled={editCourse.status==='published'} onChange={e=>setEditCourse({...editCourse,title:e.target.value})}/></label>{editCourse.status==='published'&&<p className="footnote">此版本已冻结。需要修改时，请先复制为新版本。</p>}{editCourse.slides.map((s,i)=><div className="slide-editor" key={s.id}><span className="page-number">{String(i+1).padStart(2,'0')}</span><div><label>知识点标题<input disabled={editCourse.status==='published'} value={s.title} onChange={e=>setEditCourse({...editCourse,slides:editCourse.slides.map((x,j)=>j===i?{...x,title:e.target.value}:x)})}/></label><label>课件要点 · 每行一条<textarea disabled={editCourse.status==='published'} rows={3} value={s.bullets.join('\n')} onChange={e=>setEditCourse({...editCourse,slides:editCourse.slides.map((x,j)=>j===i?{...x,bullets:e.target.value.split('\n')}:x)})}/></label></div><div><label>老师讲稿<textarea disabled={editCourse.status==='published'} rows={6} value={s.narration} onChange={e=>setEditCourse({...editCourse,slides:editCourse.slides.map((x,j)=>j===i?{...x,narration:e.target.value}:x)})}/></label><small className="source-line">资料依据：{editCourse.sources.filter(x=>s.source_ids.includes(x.id)).map(x=>`${x.title} · 段落 ${x.section}`).join('；')}</small></div></div>)}</div>}
        </>}

        {page==='settings'&&<div className="settings-layout"><div className="service-grid">{[['语言模型',config?.llm.configured,config?.llm.model||'DeepSeek','组织有引用依据的回答'],['老师声音',config?.tts.configured,'Qwen3-TTS 适配接口','GPU 服务器合成老师声音'],['语音识别',config?.asr.configured,'ASR 适配接口','将学生语音转换为问题'],['真人驱动',false,'OpenTalking / FasterLivePortrait','单独接入并验证 WebRTC 视频流']].map(([title,configured,name,desc])=><div className="panel service-card" key={String(title)}><div><Server size={22}/><span className={`pill ${configured?'':'amber'}`}>{configured?'已配置 · 待端到端验收':'待连接'}</span></div><h2>{title}</h2><b>{name}</b><p>{desc}</p></div>)}</div><div className="panel form-panel"><h2>本地业务，云端模型</h2><div className="architecture"><span><Monitor/>本地工作台</span><ArrowRight/><span><ShieldCheck/>教师 API</span><ArrowRight/><span><Server/>优云智算 GPU</span></div><p>在项目根目录复制 <code>.env.example</code> 为 <code>.env</code>，配置模型服务地址与密钥后重启后台。密钥不会返回页面。</p><pre>LLM_BASE_URL=https://api.deepseek.com{ '\n'}LLM_MODEL=deepseek-chat{'\n'}LLM_API_KEY=你的密钥{'\n'}TTS_BASE_URL=http://GPU内网地址:8020{'\n'}ASR_BASE_URL=http://GPU内网地址:8030</pre><p>语音服务协议见 <code>docs/model-services.md</code>；部署步骤见 <code>docs/deployment.md</code>。GPU 地址不能直接填入未适配的模型 WebUI。</p><div className="info-note"><ShieldCheck size={18}/><span>当前为单管理员工作台。{config?.auth_enabled?'访问令牌已开启。':'访问令牌未开启，仅用于本机访问。'}外网部署时必须开启认证并配置 HTTPS。</span></div><button onClick={()=>void run(async()=>setConfig(await api('/config')))}><RotateCcw size={16}/>刷新配置状态</button></div></div>}
      </main><footer>星河实验小学 · 智慧课堂 <span>v0.1 · 本地开发版</span><span>让每一份教学经验，都能继续传递。</span></footer>
    </div>
    {busy&&<div className="working" role="status"><span/>正在处理…</div>}
    {error&&<div className="toast error" role="alert"><span>{error}</span><button aria-label="关闭错误" onClick={()=>setError('')}><X size={16}/></button></div>}
    {notice&&<div className="toast"><CheckCircle2 size={18}/>{notice}</div>}
  </div>;
}
createRoot(document.getElementById('root')!).render(<App/>);
