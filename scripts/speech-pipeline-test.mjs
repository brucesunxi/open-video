import ts from 'typescript';import fs from 'node:fs';import assert from 'node:assert/strict';
const code=ts.transpileModule(fs.readFileSync('web/speech.ts','utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText;
const {Speaker,speechChunks,speechMedia}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
const text='你好同学！今天我们一起认识水的三态。你想先聊聊蒸发，还是凝固呢？'.repeat(3);
assert.equal(speechChunks(text).join(''),text);assert.ok(speechChunks(text)[0].length>=10&&speechChunks(text)[0].length<=80);
for(const sample of ['湿衣服里的水分蒸发到了空气中，我们可以观察到衣服慢慢变干。','今天我们一起观察湿衣服里的水分逐渐蒸发到空气中然后变成水蒸气这个过程'.repeat(5)]){assert.equal(speechChunks(sample).join(''),sample);assert.ok(!speechChunks(sample).some(p=>p.endsWith('空')));}
let requests=[],audios=[],ended=0,failed=0,controller,cancelled=false;
const encoder=new TextEncoder();
const event=(i)=>'data: '+JSON.stringify({index:i,mime:'audio/wav',data:btoa('audio-'+i)})+'\n\n';
globalThis.window={speechSynthesis:{cancel(){}}};
globalThis.fetch=async(url,options)=>{requests.push({url,body:JSON.parse(options.body),signal:options.signal});return new Response(new ReadableStream({start(c){controller=c;options.signal.addEventListener('abort',()=>{cancelled=true;c.error(new Error('aborted'));},{once:true});},cancel(){cancelled=true;}}),{headers:{'Content-Type':'text/event-stream'}});};
globalThis.Audio=class extends EventTarget{constructor(){super();audios.push(this);}load(){this.readyState=2;queueMicrotask(()=>this.dispatchEvent(new Event('loadeddata')));}play(){return Promise.resolve();}pause(){}};
const until=async(fn)=>{for(let i=0;i<100;i++){if(fn())return;await new Promise(r=>setTimeout(r,10));}throw new Error('Timed out waiting for playback');};
const speaker=new Speaker();const done=speaker.play(text,'teacher','gpu',()=>ended++,()=>failed++);
await until(()=>requests.length===1);assert.deepEqual(requests[0].body.chunks,speechChunks(text));
// An event split across network packets must still start before the response ends.
const first=event(0);controller.enqueue(encoder.encode(first.slice(0,14)));controller.enqueue(encoder.encode(first.slice(14)));
await until(()=>audios.length===1);assert.equal(ended,0);
audios[0].onended();assert.equal(ended,0,'do not finish while next piece is pending');
for(let i=1;i<speechChunks(text).length;i++){
 controller.enqueue(encoder.encode(event(i)));await until(()=>audios.length===i+1);audios[i].onended();
}
controller.enqueue(encoder.encode('data: {"done":true}\n\n'));controller.close();await done;
assert.equal(requests.length,1,'all pieces share one network request');assert.equal(ended,1);assert.equal(failed,0);
requests=[];audios=[];cancelled=false;
const interrupted=speaker.play(text,'teacher','gpu',()=>ended++,()=>failed++);
await until(()=>requests.length===1);controller.enqueue(encoder.encode(event(0)));await until(()=>audios.length===1);
speaker.stop();await interrupted;assert.ok(cancelled);assert.ok(requests[0].signal.aborted);assert.equal(ended,1);
// End-of-answer restores the neutral portrait; segment boundaries must not flash it.
requests=[];audios=[];let portrait=null;
globalThis.document={createElement(tag){assert.equal(tag,'video');return new Audio();}};
speaker.onVideo=value=>{portrait=value;};
const videoEvent=i=>'data: '+JSON.stringify({index:i,mime:'video/mp4',data:btoa('video-'+i)})+'\n\n';
const videoDone=speaker.play(text,'teacher','gpu',()=>{assert.equal(portrait,null);ended++;},()=>failed++);
await until(()=>requests.length===1);
for(let i=0;i<speechChunks(text).length;i++){
 controller.enqueue(encoder.encode(videoEvent(i)));await until(()=>audios.length===i+1&&portrait===audios[i]);
 assert.equal(portrait,audios[i]);audios[i].onended();
 if(i+1<speechChunks(text).length){await new Promise(r=>setTimeout(r,0));assert.equal(portrait,audios[i],'retain video while waiting for the next piece');}
}
controller.enqueue(encoder.encode('data: {"done":true}\n\n'));controller.close();await videoDone;
assert.equal(portrait,null,'never freeze the final mouth/blink pose');assert.equal(ended,2);assert.equal(failed,0);
assert.equal(audios.at(-1).src,'','release finished video');
// Mobile autoplay denial keeps the generated clip and resumes without synthesis.
requests=[];audios=[];let blocked=false,allowPlay=false;
globalThis.Audio=class extends EventTarget{constructor(){super();audios.push(this);}load(){this.readyState=2;queueMicrotask(()=>this.dispatchEvent(new Event('loadeddata')));}play(){return allowPlay?Promise.resolve():Promise.reject(new DOMException('gesture required','NotAllowedError'));}pause(){}};
speaker.onPlaybackBlocked=value=>{blocked=value;};
const mobile=speaker.play('你好。','teacher','gpu',()=>ended++,()=>failed++);
await until(()=>requests.length===1);controller.enqueue(encoder.encode(event(0)));
await until(()=>blocked);assert.equal(failed,0);assert.equal(ended,2);
allowPlay=true;speaker.resume();await until(()=>speaker.speaking);assert.equal(blocked,false);assert.equal(requests.length,1);
audios[0].onended();controller.enqueue(encoder.encode('data: {"done":true}\n\n'));controller.close();await mobile;assert.equal(ended,3);
requests=[];audios=[];allowPlay=false;
const stopped=speaker.play('你好。','teacher','gpu',()=>ended++,()=>failed++);
await until(()=>requests.length===1);controller.enqueue(encoder.encode(event(0)));await until(()=>blocked);
speaker.stop();speaker.resume();await stopped;assert.equal(blocked,false);assert.equal(ended,3);assert.equal(failed,0);
const malformed=new Response('data: '+JSON.stringify({index:2,mime:'audio/wav',data:btoa('audio')})+'\n\n',{headers:{'Content-Type':'text/event-stream'}});
await assert.rejects(async()=>{for await(const blob of speechMedia(malformed)){}},/顺序/);
const truncated=new Response(event(0),{headers:{'Content-Type':'text/event-stream'}});
await assert.rejects(async()=>{for await(const blob of speechMedia(truncated)){}},/提前结束/);
// Board progress follows the media clock, and stale callbacks cannot advance it.
requests=[];audios=[];allowPlay=true;let progress=[];
speaker.onProgress=(text,offset)=>progress.push(offset);
const boardText='我们先观察相同的单位。';
const boardPlay=speaker.play(boardText,'teacher','gpu',()=>{},()=>failed++,true);
await until(()=>requests.length===1);controller.enqueue(encoder.encode(event(0)));
await until(()=>audios.length===1&&speaker.speaking);
audios[0].duration=10;audios[0].currentTime=5;audios[0].ontimeupdate();
assert.equal(progress.at(-1),Math.floor(boardText.length/2));
const stale=audios[0].ontimeupdate;speaker.stop();const count=progress.length;stale();assert.equal(progress.length,count);
await boardPlay;
console.log('PASS: balanced complete text, one streaming request, partial network packets, ordered playback, cancellation, malformed/truncated stream');
