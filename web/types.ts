export type Teacher={id:string; name:string;subject:string;bio:string;style:string;voice_profile_id:string;avatar_asset_id:string;consent:boolean};
export type Source={id:string;text:string;title:string;document_id:string;page:number|null;section:number;version:number};
export type Knowledge={id:string;title:string;approved:boolean;teacher_id:string;chunks:Source[];version:number};
export type Slide={id:string;title:string;bullets:string[];board_anchors?:string[];narration:string;source_ids:string[];gesture:string};
export type Course={id:string;title:string;version:number;status:string;slides:Slide[];sources:Source[];teacher_id:string};
export type Message={role:string;text:string;sources?:Source[];mode?:string};
export type Session={id:string;teacher_id:string;course_id:string|null;state:string;revision:number;slide_index:number;messages:Message[]};
export type Asset={id:string;kind:string;filename:string;size:number;url:string};
export type Config={mode:string;llm:{configured:boolean;model:string};tts:{configured:boolean};asr:{configured:boolean};avatar:{configured:boolean;integration:string};auth_enabled:boolean};

export async function api<T=any>(path:string, options:RequestInit={}):Promise<T>{
  const headers:Record<string,string> = options.body instanceof FormData ? {} : {'Content-Type':'application/json'};
  const r=await fetch('/api'+path,{...options,headers:{...headers,...options.headers}});
  if(!r.ok){const data=await r.json().catch(()=>({}));throw new Error(typeof data.detail==='string'?data.detail:`请求未成功（${r.status}）`);}
  return r.json();
}
export const post=<T=any>(p:string,body:unknown={})=>api<T>(p,{method:'POST',body:JSON.stringify(body)});
