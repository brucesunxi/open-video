import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1050}});
page.setDefaultTimeout(10000);
page.on('pageerror',e=>console.error(e.message));
try{
  await page.addInitScript(()=>{
    window.SpeechRecognition=window.webkitSpeechRecognition=class {
      start(){window.testRecognition=this;window.listeningCount=(window.listeningCount||0)+1;}
      abort(){window.testRecognition=null;}
    };
    window.speechSynthesis.speak=u=>{window.testUtterance=u;u.onstart?.();};
    window.speechSynthesis.cancel=()=>{window.testUtterance=null;};
  });
  await page.goto(process.env.STUDIO_URL||'http://127.0.0.1:8011');
  await page.getByRole('button',{name:'实时对话',exact:true}).click();
  await page.getByRole('button',{name:'开始实时对话',exact:true}).click();
  await page.waitForFunction(()=>!!window.testRecognition);
  await page.evaluate(()=>{const r=[{transcript:'蒸发是什么？'}];r.isFinal=false;window.testRecognition.onresult({resultIndex:0,results:[r]});window.testRecognition.onend();});
  await page.waitForFunction(()=>!!window.testUtterance);
  assert.equal(await page.evaluate(()=>!!window.testRecognition),false,'麦克风识别应在老师说话期间停止');
  await page.evaluate(()=>window.testUtterance.onend());
  await page.waitForFunction(()=>window.listeningCount>=2&&!!window.testRecognition);
  await page.evaluate(()=>{const r=[{transcript:'凝固是什么？'}];r.isFinal=true;window.testRecognition.onresult({resultIndex:0,results:[r]});});
  await page.getByRole('status').filter({hasText:'老师正在回答'}).waitFor();
  await page.getByRole('button',{name:'打断并说话'}).click();
  await page.waitForFunction(()=>window.listeningCount>=3&&!!window.testRecognition);
  assert.equal(await page.evaluate(()=>window.testUtterance),null,'打断必须取消音频');
  await page.getByRole('button',{name:'结束对话',exact:true}).click();
  await page.getByRole('status').filter({hasText:'对话已暂停'}).waitFor();
  assert.equal(await page.evaluate(()=>!!window.testRecognition),false);
  await page.getByRole('button',{name:'开始实时对话',exact:true}).click();
  await page.waitForFunction(()=>!!window.testRecognition);
  await page.screenshot({path:'test-results/realtime-desktop.png',fullPage:true});
  await page.getByRole('button',{name:'讲课与插问',exact:true}).click();
  assert.equal(await page.evaluate(()=>!!window.testRecognition),false,'离开模式必须停止麦克风');
  console.log('REALTIME PASS: automatic submit, reply, listen again, interruption, stop, navigation cleanup (mocked browser audio APIs)');
}catch(e){await page.screenshot({path:'test-results/realtime-failure.png',fullPage:true});throw e;}finally{await browser.close();}
