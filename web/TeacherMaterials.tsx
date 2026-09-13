import {useEffect,useRef,useState} from 'react';
import {Upload,FileText,CheckCircle2,LoaderCircle,AlertCircle} from 'lucide-react';
import {post,type Teacher,type Asset,type Config} from './types';

type Work={title:string;detail:string;state:'running'|'done'|'error';started:number;percent?:number};
function Progress({work}:{work:Work}){
  const [now,setNow]=useState(Date.now());
  useEffect(()=>{setNow(Date.now());if(work.state!=='running')return;const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[work]);
  const seconds=Math.max(0,Math.floor((now-work.started)/1000));
  return <div className={`material-progress ${work.state}`} role="status" aria-live="polite">
    <div className="material-progress-title">{work.state==='running'?<LoaderCircle className="material-spinner" size={19}/>:work.state==='done'?<CheckCircle2 size={19}/>:<AlertCircle size={19}/>}<b>{work.title}</b><span>{work.state==='running'?`已等待 ${seconds} 秒`:work.state==='done'?'已完成':'未完成'}</span></div>
    <p>{work.detail}</p>
    {work.state==='running'&&<><progress aria-label={work.title} max={100} value={work.percent}/><small>{work.percent===undefined?'正在处理，服务暂不提供百分比':`已传输 ${work.percent}% · 接收确认后才算上传成功`}{seconds>=30?'。耗时较长，请保持页面打开，完成后会自动更新。':''}</small></>}
  </div>;
}
function upload(path:string,form:FormData,onProgress:(percent?:number)=>void):Promise<void>{
  return new Promise((resolve,reject)=>{
    const xhr=new XMLHttpRequest();xhr.open('POST','/api'+path);xhr.timeout=10*60*1000;
    xhr.upload.onprogress=e=>onProgress(e.lengthComputable?Math.floor(e.loaded/e.total*100):undefined);
    xhr.upload.onload=()=>onProgress(undefined);
    xhr.onerror=()=>reject(new Error('网络连接中断，请检查网络后重新上传。'));
    xhr.ontimeout=()=>reject(new Error('上传等待超时，请刷新素材列表确认是否已保存，再重试。'));
    xhr.onload=()=>{if(xhr.status>=200&&xhr.status<300){resolve();return;}let detail='';try{detail=JSON.parse(xhr.responseText).detail;}catch{}reject(new Error(typeof detail==='string'&&detail?detail:`上传失败（${xhr.status}），请重试。`));};
    xhr.send(form);
  });
}
export function TeacherMaterials({teacher,assets,config,busy,run,refresh}:{teacher:Teacher;assets:Asset[];config:Config|null;busy:boolean;run:(fn:()=>Promise<void>)=>Promise<void>;refresh:()=>Promise<void>}){
  const [voiceAsset,setVoiceAsset]=useState(''),[transcript,setTranscript]=useState('');
  const [uploadWork,setUploadWork]=useState<Work|null>(null),[voiceWork,setVoiceWork]=useState<Work|null>(null),[audio,setAudio]=useState('');
  const url=useRef('');
  useEffect(()=>()=>{if(url.current)URL.revokeObjectURL(url.current);},[]);
  async function uploadFile(file:File,kind:string){
    const started=Date.now();setUploadWork({title:'正在上传 '+file.name,detail:'将素材安全保存到工作台。',state:'running',started,percent:0});
    try{
      if(!file.size||file.size>250*1024*1024)throw new Error('请选择非空文件，单个素材最多 250MB。');
      const form=new FormData();form.append('file',file);form.append('kind',kind);
      await upload(`/teachers/${teacher.id}/assets`,form,percent=>setUploadWork({title:percent===undefined?'服务器正在接收素材':'正在上传 '+file.name,detail:file.name,state:'running',started,percent}));
      setUploadWork({title:'素材上传完成',detail:kind==='image'?'图片已保存，请在左侧“课堂形象”中选择并保存档案。':kind==='voice'?'录音已保存。请在下方选择录音、填写原文，再建立音色。':'文件已保存，请按素材说明继续使用。',state:'done',started});
      await refresh();
    }catch(e){setUploadWork({title:'素材上传未完成',detail:(e as Error).message,state:'error',started});throw e;}
  }
  async function createVoice(){
    const started=Date.now();setVoiceWork({title:'正在建立老师音色',detail:'校验参考录音并转换音频格式，保存录音与对应文字。请勿重复提交。',state:'running',started});
    if(url.current)URL.revokeObjectURL(url.current);url.current='';setAudio('');
    try{
      await post(`/teachers/${teacher.id}/voice-profile`,{asset_id:voiceAsset,transcript});
      setVoiceWork({title:'老师音色已保存',detail:'可以生成试听或进入课堂使用。首次合成时会提取声音特征，可能需要稍等。',state:'done',started});
      await refresh();
    }catch(e){setVoiceWork({title:'音色建立未完成',detail:(e as Error).message+' 请检查录音和原文后重新提交。',state:'error',started});throw e;}
  }
  async function preview(){
    const started=Date.now();setVoiceWork({title:'正在生成试听声音',detail:'首次使用会提取声音特征，再合成试听；服务忙碌时会自动等待重试。',state:'running',started});
    try{
      const response=await fetch('/api/speech',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({teacher_id:teacher.id,text:'你好，同学。很高兴和你一起学习，让我们开始今天的课堂吧。'}),signal:AbortSignal.timeout(100000)});
      if(!response.ok){const result=await response.json();throw new Error(result.detail||'声音生成失败。');}
      const blob=await response.blob();if(!blob.size||!blob.type.startsWith('audio/'))throw new Error('没有收到有效音频。');
      if(url.current)URL.revokeObjectURL(url.current);url.current=URL.createObjectURL(blob);setAudio(url.current);
      setVoiceWork({title:'试听声音已生成',detail:'点击下方播放，检查音色是否接近老师。',state:'done',started});
    }catch(e){setVoiceWork({title:'试听生成未完成',detail:(e as Error).message+' 已保存的音色仍保留，可以重新生成试听。',state:'error',started});throw e;}
  }
  return <section className="panel form-panel"><h2>老师素材</h2><p className="subtle">上传后查看处理状态，再将声音与形象用于课堂。</p>
    <div className="upload-grid">{([['video','讲话视频','.mp4,.mov,.webm'],['voice','声音参考','.wav,.mp3,.m4a,.ogg'],['image','真人 / 卡通参考','.png,.jpg,.jpeg,.webp'],['vrm','VRM 动画角色','.vrm']] as const).map(([kind,label,accept])=><label className="upload-box" key={kind}><Upload size={21}/><b>{label}</b><small>选择文件上传</small><input type="file" aria-label={label} accept={accept} disabled={busy} onChange={e=>{const f=e.target.files?.[0];if(f)void run(()=>uploadFile(f,kind));e.target.value='';}}/></label>)}</div>
    {uploadWork&&<Progress work={uploadWork}/>}
    <div className="asset-list">{assets.map(a=><div key={a.id}><FileText size={18}/><div><a href={a.url} target="_blank" rel="noreferrer">{a.filename}</a><small>{(a.size/1024/1024).toFixed(1)} MB · {a.kind==='image'?(config?.avatar.configured?'已保存 · 可用于正面人像动画':'已保存 · 可作静态形象'):a.kind==='video'?'已保存 · 视频驱动尚未接入':a.kind==='voice'?'已保存 · 可选为音色参考':'已保存 · 可选为课堂角色'}</small></div><CheckCircle2 size={17}/></div>)}</div>
    {assets.some(a=>a.kind==='image'||a.kind==='video')&&<div className="material-info"><b>{config?.avatar.configured?'形象处理状态 · 照片动画服务已接入':'形象处理状态 · 动画驱动待接入'}</b><p>{config?.avatar.configured?'选择单人正面照片并保存课堂形象，使用老师克隆声音对话时生成头肩动画。系统会预备可复用的形象画面；口型根据实际语音生成，并保留眨眼与轻微转头。目前尚未验收卡通图，也不生成全身手势。':'照片可直接作为课堂静态形象。目前不会自动训练或生成说话动画，也没有后台动画任务在等待。VRM 角色可在课堂中呈现基础动作。'}</p></div>}
    <form onSubmit={e=>{e.preventDefault();void run(createVoice);}}><h3>建立老师音色</h3><p className="subtle">使用 3–30 秒清晰单人录音和准确原文建立参考音色，无需单独训练一个模型。</p>
      <label>参考录音<select aria-label="参考录音" required disabled={busy} value={voiceAsset} onChange={e=>setVoiceAsset(e.target.value)}><option value="">请选择声音素材</option>{assets.filter(a=>a.kind==='voice').map(a=><option key={a.id} value={a.id}>{a.filename}</option>)}</select></label>
      <label>录音原文<textarea aria-label="录音原文" required disabled={busy} maxLength={2000} rows={3} value={transcript} onChange={e=>setTranscript(e.target.value)} placeholder="与所选录音逐字对应，帮助模型还原老师的声音…"/></label>
      <button className="primary" disabled={busy||!config?.tts.configured||!teacher.consent||!assets.some(a=>a.id===voiceAsset&&a.kind==='voice')}>建立声音档案</button>
      {!teacher.consent&&<p className="footnote">请先勾选并保存左侧的老师授权。</p>}{!config?.tts.configured&&<p className="footnote">声音服务尚未连接。</p>}
    </form>
    {voiceWork?<Progress work={voiceWork}/>:teacher.voice_profile_id?<div className="material-info"><b>老师音色 · 已保存</b><p>可以生成试听，或在实时对话中选择老师克隆声音。</p></div>:null}
    {teacher.voice_profile_id&&<button disabled={busy||!teacher.consent||!config?.tts.configured} onClick={()=>void run(preview)}>{audio?'重新生成试听':'生成试听声音'}</button>}
    {audio&&<audio className="material-audio" aria-label="老师克隆声音试听" controls src={audio}/>}
    <p className="footnote">单个素材最多 250MB，音色参考最多 15MB。处理期间请保持页面打开；已保存的素材和音色会保留。</p>
  </section>;
}
