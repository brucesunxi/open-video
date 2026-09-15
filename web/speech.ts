export type ReadyPage={url:string;duration:number;segments:{start:number;duration:number;offset:number;length:number}[]};
// Prefer punctuation and linguistic word boundaries; never cut by a fixed character count.
export function speechChunks(text:string,continuous=false):string[]{
  let remaining=text.trim();const chunks:string[]=[];
  const Segmenter=(Intl as unknown as {Segmenter?:new(locale:string,options:{granularity:string})=>{segment:(text:string)=>Iterable<{index:number;segment:string}>}}).Segmenter;
  while(remaining){
    const target=chunks.length||continuous?55:28,max=80;
    const marks=Array.from(remaining.matchAll(/[。！？!?；;，,\n]/g)).map(m=>m.index!+m[0].length);
    let end=marks.find(x=>x>=target&&x<=max);
    if(!end){const before=marks.filter(x=>x<=max);end=before.at(-1);}
    if(remaining.length<=max&&!end)end=remaining.length;
    if(!end){
      const boundaries=Segmenter?Array.from(new Segmenter('zh',{granularity:'word'}).segment(remaining)).map(x=>x.index+x.segment.length):[];
      end=boundaries.filter(x=>x<=max).at(-1)||Math.min(remaining.length,200);
    }
    // Avoid leaving a tiny final fragment to be synthesised on its own.
    if(remaining.length-end<=12&&remaining.length<=max)end=remaining.length;
    const part=remaining.slice(0,end);if(part.trim())chunks.push(part);
    remaining=remaining.slice(end);
  }
  return chunks;
}

// One HTTP stream carries successive complete, synchronised audio/video pieces.
// The server can prepare the next piece while the first travels over the network.
export async function* speechMedia(response:Response):AsyncGenerator<Blob>{
  if(!response.ok){const data=await response.json().catch(()=>({}));throw new Error(data.detail||'声音服务不可用。');}
  if(!response.body||!response.headers.get('content-type')?.startsWith('text/event-stream'))throw new Error('声音服务没有返回分段播放流。');
  const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='',index=0;
  try{
    while(true){
      const part=await reader.read();
      if(part.done)throw new Error('声音传输提前结束，请重新发送。');
      buffer+=decoder.decode(part.value,{stream:true});
      if(buffer.length>72*1024*1024)throw new Error('声音片段过大。');
      let boundary:number;
      while((boundary=buffer.indexOf('\n\n'))!==-1){
        const event=buffer.slice(0,boundary);buffer=buffer.slice(boundary+2);
        if(!event.startsWith('data: '))continue;
        const value=JSON.parse(event.slice(6));
        if(value.error)throw new Error(value.error);
        if(value.done)return;
        if(value.index!==index++||typeof value.data!=='string'||typeof value.mime!=='string'||
          !/^(audio\/|video\/mp4)/.test(value.mime))throw new Error('声音片段顺序或格式异常。');
        const binary=atob(value.data),bytes=Uint8Array.from(binary,c=>c.charCodeAt(0));
        if(!bytes.length)throw new Error('声音片段为空。');
        yield new Blob([bytes],{type:value.mime});
      }
    }
  }finally{await reader.cancel().catch(()=>{});reader.releaseLock();}
}
// One audio owner for both classroom narration and Q&A. Generation guards defeat late callbacks.
export class Speaker {
  private generation=0;
  private preloaded=new Map<string,HTMLVideoElement>();
  preload(url:string){
    if(this.preloaded.has(url)||this.url===url)return;
    const video=document.createElement('video');video.playsInline=true;video.preload='auto';video.src=url;video.load();
    this.preloaded.set(url,video);
    while(this.preloaded.size>2){const key=this.preloaded.keys().next().value!;const old=this.preloaded.get(key)!;old.src='';old.load();this.preloaded.delete(key);}
  }

  private audio:HTMLMediaElement|null=null;
  private abort:AbortController|null=null;
  private url:string|null=null;
  private resumePlayback:(()=>void)|null=null;
  onPlaybackBlocked:(blocked:boolean)=>void=()=>{};
  resume(){this.resumePlayback?.();}
  speaking=false;
  onChange:(value:boolean)=>void=()=>{};
  onVideo:(video:HTMLVideoElement|null)=>void=()=>{};
  onWaiting:()=>void=()=>{};
  onProgress:(text:string,offset:number)=>void=()=>{};
  stop(){
    this.generation++;this.resumePlayback=null;this.onPlaybackBlocked(false);this.onVideo(null);
    this.abort?.abort();this.abort=null;
    if(this.audio){this.audio.onended=null;this.audio.onerror=null;this.audio.pause();this.audio.src='';this.audio=null;}
    if(this.url){URL.revokeObjectURL(this.url);this.url=null;}
    window.speechSynthesis?.cancel();this.speaking=false;this.onChange(false);
  }
  async play(text:string, teacherId:string, mode:string, ended:()=>void, error:(e:Error)=>void,continuous=false,ready?:ReadyPage){
    this.stop();const generation=this.generation;
    if(continuous)this.onProgress(text,0);
    const finish=()=>{
      if(generation!==this.generation)return;
      // A speaking/blinking final frame is not a listening expression. Restore
      // the reference portrait only after the whole answer, never between pieces.
      this.onVideo(null);
      if(this.audio){this.audio.onended=null;this.audio.onerror=null;this.audio.pause();this.audio.src='';this.audio=null;}
      if(this.url){URL.revokeObjectURL(this.url);this.url=null;}
      if(continuous)this.onProgress(text,text.length);
      this.speaking=false;this.onChange(false);ended();
    };
    const fail=(message:string)=>{if(generation!==this.generation)return;this.stop();error(new Error(message));};
    if(mode==='silent'){finish();return;}
    if(mode==='browser'){
      if(!window.speechSynthesis){fail('浏览器不支持朗读，请使用 Chrome 或配置 GPU 声音。');return;}
      const utterance=new SpeechSynthesisUtterance(text);utterance.lang='zh-CN';utterance.rate=.95;
      const voice=window.speechSynthesis.getVoices().find(v=>v.lang.startsWith('zh'));if(voice)utterance.voice=voice;
      utterance.onstart=()=>{if(generation===this.generation){this.speaking=true;this.onChange(true);}};
      utterance.onboundary=e=>{if(continuous&&generation===this.generation)this.onProgress(text,e.charIndex);};
      utterance.onend=finish;utterance.onerror=()=>fail('浏览器朗读未完成。课程已暂停，可重新播放或切换静音阅读。');
      window.speechSynthesis.speak(utterance);return;
    }
    this.abort=new AbortController();const signal=this.abort.signal;
    let stream:AsyncGenerator<Blob>|undefined;
    const prepared=new Set<{media:HTMLMediaElement;url:string}>();
    const dispose=(item:{media:HTMLMediaElement;url:string})=>{item.media.onended=null;item.media.onerror=null;item.media.ontimeupdate=null;item.media.pause();item.media.src='';URL.revokeObjectURL(item.url);prepared.delete(item);};
    try{
      const chunks=ready?[text]:speechChunks(text,continuous);if(!chunks.length){finish();return;}
      this.onWaiting();
      if(!ready){
      const response=await fetch('/api/speech/stream',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({teacher_id:teacherId,chunks,animate:true}),signal:AbortSignal.any([signal,AbortSignal.timeout(900000)])});
      stream=speechMedia(response);
      }
      const next=async()=>{try{
        const result=ready?{done:false as const,value:null}:await stream!.next();if(result.done)return result;
        if(signal.aborted)return {done:true as const,value:undefined};
        const isVideo=Boolean(ready)||result.value!.type.startsWith('video/');
        const reused=Boolean(ready&&this.preloaded.has(ready.url));
        if(ready)this.url=ready.url;
        const media=ready?(this.preloaded.get(ready.url)||document.createElement('video')):isVideo?document.createElement('video'):new Audio();
        if(ready)this.preloaded.delete(ready.url);
        const item={media,url:ready?.url||URL.createObjectURL(result.value!)};prepared.add(item);
        if(isVideo)(media as HTMLVideoElement).playsInline=true;
        media.preload='auto';if(media.getAttribute?.('src')!==item.url)media.src=item.url;
        // Mobile browsers may refuse preload until play() is requested.
        // Prepared URLs must reach play() immediately, without waiting for loadeddata.
        if(!ready)await new Promise<void>((resolve,reject)=>{
          if(media.readyState>=2){resolve();return;}
          const cleanup=()=>{clearTimeout(timer);media.removeEventListener('loadeddata',ready);media.removeEventListener('error',bad);signal.removeEventListener('abort',cancel);};
          const ready=()=>{cleanup();resolve();};const bad=()=>{cleanup();reject(new Error('下一段声音或画面加载失败。'));};
          const cancel=()=>{cleanup();reject(new DOMException('aborted','AbortError'));};
          const timer=setTimeout(bad,30000);
          media.addEventListener('loadeddata',ready,{once:true});media.addEventListener('error',bad,{once:true});signal.addEventListener('abort',cancel,{once:true});
          if(signal.aborted)cancel();else if(!reused)media.load();
        });
        return {done:false as const,value:{...item,isVideo}};
      }catch(e){return {error:e as Error};}};
      let pending=next(),previous:{media:HTMLMediaElement;url:string}|null=null;
      for(let i=0;i<chunks.length;i++){
        const result=await pending;if(generation!==this.generation)return;
        if('error' in result)throw result.error;
        if(result.done)throw new Error('老师的回答未播放完整，请重试。');
        if(i+1<chunks.length)pending=next();
        const item=result.value,audio=item.media;this.url=item.url;this.audio=audio;
        const prefix=chunks.slice(0,i).join('').length;
        const progress=()=>{if(continuous&&generation===this.generation&&Number.isFinite(audio.duration)&&audio.duration>0){
          const segment=ready?.segments.slice().reverse().find(s=>audio.currentTime>=s.start);
          const offset=segment?segment.offset+Math.floor(segment.length*Math.min(1,(audio.currentTime-segment.start)/segment.duration)):prefix+Math.floor(chunks[i].length*Math.min(1,audio.currentTime/audio.duration));
          this.onProgress(text,offset);
        }};
        audio.ontimeupdate=progress;
        await new Promise<void>((resolve,reject)=>{
          let startTimer:ReturnType<typeof setTimeout>|undefined;
          const release=()=>{clearTimeout(startTimer);this.resumePlayback=null;this.onPlaybackBlocked(false);signal.removeEventListener('abort',cancel);};
          const cancel=()=>{release();resolve();};signal.addEventListener('abort',cancel,{once:true});
          audio.onended=()=>{release();resolve();};
          audio.onerror=()=>{release();reject(new Error('音频播放失败。'));};
          let starting=false;
          const attempt=()=>{
            if(starting||generation!==this.generation)return;starting=true;
            // Called synchronously by the button, preserving the browser gesture.
            startTimer=setTimeout(()=>{release();reject(new Error('视频加载时间较长，请暂停后重试，或切换网络。'));},30000);
            audio.play().then(()=>{
              clearTimeout(startTimer);starting=false;if(generation!==this.generation)return;
              // The old frame remains visible until the new clip is decoded and playing.
              this.onVideo(item.isVideo?audio as HTMLVideoElement:null);
              if(previous)dispose(previous);previous=item;
              this.resumePlayback=null;this.onPlaybackBlocked(false);this.speaking=true;this.onChange(true);
            }).catch(e=>{
              clearTimeout(startTimer);starting=false;if(generation!==this.generation)return;
              if(e?.name==='NotAllowedError'){this.resumePlayback=attempt;this.onPlaybackBlocked(true);}
              else{release();reject(e);}
            });
          };
          attempt();
        });
        if(generation!==this.generation)return;
      }
      this.speaking=false;this.onChange(false);finish();
    }catch(e){if(generation===this.generation)fail((e as Error).message);}
    finally{for(const item of prepared)dispose(item);await stream?.return(undefined);}
  }
}
