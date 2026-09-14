import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
try{
for(const scenario of ['network','permission','missing','gpu-failure','silence','timeout','empty-result']){
 const page=await browser.newPage();page.setDefaultTimeout(10000);
 let requests=0;
 await page.route('**/api/config',async route=>{const r=await route.fetch();const j=await r.json();j.asr.configured=scenario!=='missing';await route.fulfill({json:j});});
 await page.route('**/api/transcribe',async route=>{requests++;await route.fulfill(scenario==='gpu-failure'?{status:502,json:{detail:'test unavailable'}}:{json:{text:'蒸发是什么？'}});});
 await page.addInitScript(()=>{
  window.SpeechRecognition=window.webkitSpeechRecognition=class {start(){window.rec=this;this.onstart?.();}abort(){window.rec=null;}};
  navigator.mediaDevices.getUserMedia=async()=>{window.gpuOpens=(window.gpuOpens||0)+1;return {getTracks:()=>[{stop(){window.trackStopped=true;}}]};};
  window.AudioContext=class {resume(){return Promise.resolve();}close(){return Promise.resolve();}createMediaStreamSource(){return {connect(){}};}createAnalyser(){let count=0;return {fftSize:2048,getFloatTimeDomainData(a){a.fill(count++===0?.1:0);}};}};
  window.MediaRecorder=class {state='inactive';mimeType='audio/webm';start(){this.state='recording';}stop(){this.state='inactive';this.ondataavailable?.({data:new Blob(['mock audio'])});this.onstop?.();}};
  window.speechSynthesis.speak=u=>{window.utterance=u;u.onstart?.();};window.speechSynthesis.cancel=()=>{};
 });
 await page.goto('http://127.0.0.1:8011');await page.getByRole('button',{name:'实时对话',exact:true}).click();
 await page.getByRole('button',{name:'开始实时对话',exact:true}).click();await page.waitForFunction(()=>!!window.rec);
 if(scenario==='empty-result'){
   await page.evaluate(()=>{window.rec.onspeechstart();window.rec.onend();});
 }else if(scenario==='timeout'){
   await page.clock.install();await page.evaluate(()=>window.rec.onspeechstart());await page.clock.fastForward(21000);
 }else await page.evaluate(code=>window.rec.onerror({error:code}),scenario==='permission'?'not-allowed':scenario==='silence'?'no-speech':'network');
 if(['network','gpu-failure','timeout','empty-result'].includes(scenario)){
   await page.locator('[data-testid="asr-route"][data-route*="自动兜底"]').waitFor();
   if(scenario==='timeout')await page.clock.resume();
   if(scenario==='gpu-failure')await page.getByRole('alert').filter({hasText:'GPU 识别失败'}).waitFor();
   else await page.locator('.message.assistant').waitFor();
   assert.equal(requests,1,'只提交一个 GPU 请求');
   assert.equal(await page.evaluate(()=>window.rec),null);
 }else if(scenario==='silence'){
   assert.equal(requests,0);assert.equal(await page.evaluate(()=>window.gpuOpens||0),0);
 }else{
   await page.getByRole('alert').waitFor();assert.equal(await page.evaluate(()=>window.gpuOpens||0),0);
 }
 await page.close();console.log('PASS',scenario);
}
}finally{await browser.close();}
