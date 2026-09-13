import React,{useEffect,useState} from 'react';
import {api,post,type Course,type Teacher} from './types';
import {speechChunks} from './speech';
type Job={id:string;status:string;completed:number;total:number;page:number;message:string};
export function CourseMedia({course,teacher}:{course:Course;teacher:Teacher}){
 const key=`course-media:${course.id}:${teacher.voice_profile_id}:${teacher.avatar_asset_id}`;
 const [job,setJob]=useState<Job|null>(null),[error,setError]=useState(''),[starting,setStarting]=useState(false);
 useEffect(()=>{
  let cancelled=false,timer:ReturnType<typeof setTimeout>;
  const poll=async(id:string)=>{try{const next=await api<Job>(`/media-jobs/${id}`);if(cancelled)return;setJob(next);if(['queued','preparing'].includes(next.status))timer=setTimeout(()=>void poll(id),2500);}catch{if(!cancelled)setError('准备状态暂时无法获取，请稍后重新检查。');}};
  void post<Job|null>(`/courses/${course.id}/media-status`,{chunks:course.slides.map(s=>speechChunks(s.narration,true))}).then(next=>{if(cancelled)return;setJob(next);if(next&&['queued','preparing'].includes(next.status))timer=setTimeout(()=>void poll(next.id),2500);}).catch(()=>{if(!cancelled)setError('准备状态暂时无法获取。');});
  return()=>{cancelled=true;clearTimeout(timer);};
 },[key,job?.id]);
 const start=async()=>{setStarting(true);setError('');try{const next=await post<Job>(`/courses/${course.id}/prepare-media`,{chunks:course.slides.map(s=>speechChunks(s.narration,true))});localStorage.setItem(key,next.id);setJob(next);}catch(e){setError((e as Error).message);}finally{setStarting(false);}};
 const running=starting||Boolean(job&&['queued','preparing'].includes(job.status));
 return <div className="course-media" role="status"><div><strong>课前准备动画</strong><span>提前生成本课声音与动画，讲课时直接复用；更换素材后请重新准备。</span></div><button onClick={()=>void start()} disabled={running}>{running?'正在准备…':job?.status==='ready'?'检查并补齐缓存':'提前生成整课动画'}</button>{job&&<><progress value={job.completed} max={job.total}/><span>{job.completed} / {job.total} 段 · 第 {job.page} 页 · {job.message}</span></>}{error&&<span className="error">{error}</span>}</div>;
}
