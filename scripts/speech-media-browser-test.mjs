import {chromium} from '@playwright/test';import fs from 'node:fs';import ts from 'typescript';import assert from 'node:assert/strict';
const path=process.env.TEST_VIDEO||'output/teacher-materials/cartoon-speaking-live.mp4';
const data=fs.readFileSync(path).toString('base64');
const code=ts.transpileModule(fs.readFileSync('web/speech.ts','utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText;
const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--autoplay-policy=no-user-gesture-required']});
try{const page=await browser.newPage();await page.goto('http://127.0.0.1:8011');
const result=await page.evaluate(async({code,data})=>{
 const {Speaker,speechChunks}=await import('data:text/javascript;base64,'+btoa(unescape(encodeURIComponent(code))));
 const text='湿衣服里的水分蒸发到了空气中，我们可以观察到衣服慢慢变干。'.repeat(3);
 const chunks=speechChunks(text);window.fetch=async()=>new Response(chunks.map((_,i)=>'data: '+JSON.stringify({index:i,mime:'video/mp4',data})+'\n\n').join('')+'data: {"done":true}\n\n',{headers:{'Content-Type':'text/event-stream'}});
 const speaker=new Speaker(),shown=[],gaps=[];let lastEnd=0;
 const host=document.createElement('div');document.body.append(host);
 speaker.onVideo=video=>{if(video){shown.push(video.readyState);if(lastEnd)gaps.push(performance.now()-lastEnd);video.addEventListener('ended',()=>lastEnd=performance.now(),{once:true});host.replaceChildren(video);}else host.replaceChildren();};
 await new Promise((resolve,reject)=>{speaker.play(text,'test','gpu',resolve,reject);});return {shown,gaps,count:chunks.length};
},{code,data});assert.equal(result.shown.length,result.count);assert.ok(result.shown.every(n=>n>=2));assert.ok(result.gaps.every(ms=>ms<250),JSON.stringify(result));console.log('PASS decoded video switches:',JSON.stringify(result));
}finally{await browser.close();}
