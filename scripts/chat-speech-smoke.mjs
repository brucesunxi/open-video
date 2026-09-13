import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
const note='（本回答未引用老师知识库资料）';
const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
try{
 for(const mode of ['realtime','lesson']){
  const page=await browser.newPage();page.setDefaultTimeout(10000);
  await page.addInitScript(()=>{window.speechSynthesis.speak=u=>{window.spoken=u.text;u.onstart?.();};window.speechSynthesis.cancel=()=>{};});
  await page.route('**/api/sessions/*/ask',async route=>{const res=await route.fetch();const data=await res.json();data.answer='你好，很高兴和你聊天！\n\n'+note;data.speech_text='你好，很高兴和你聊天！';data.session.messages.at(-1).text=data.answer;await route.fulfill({json:data});});
  await page.goto('http://127.0.0.1:8011');
  if(mode==='realtime'){
   await page.getByRole('button',{name:'实时对话',exact:true}).click();
   await page.getByLabel('实时对话文字').fill('你好');
   await page.locator('form').last().evaluate(f=>f.requestSubmit());
  }else{
   await page.getByLabel('声音模式').selectOption('browser');
   await page.getByLabel('课堂问题').fill('你好');await page.getByLabel('发送问题').click();
  }
  await page.waitForFunction(()=>!!window.spoken);
  assert.equal(await page.evaluate(()=>window.spoken),'你好，很高兴和你聊天！');
  await page.getByText(note,{exact:false}).first().waitFor();
  console.log('PASS display-only notice:',mode);await page.close();
 }
}finally{await browser.close();}
