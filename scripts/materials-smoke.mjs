import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
let registered=false,fail=false,previewFail=true;
const teacher={id:'material_test',name:'测试老师',subject:'科学',bio:'',style:'',consent:true,voice_profile_id:'',avatar_asset_id:''};
const assets=[{id:'voice1',kind:'voice',filename:'参考声音.wav',size:1024,url:'/api/assets/voice1'}];
await page.route('**/api/**',async route=>{
 const p=new URL(route.request().url()).pathname;
 const json=v=>route.fulfill({json:v});
 if(p==='/api/auth')return json({authorized:true});
 if(p==='/api/config')return json({tts:{configured:true},asr:{configured:false},llm:{configured:false},avatar:{configured:false}});
 if(p==='/api/teachers')return json([{...teacher,voice_profile_id:registered?'profile1':''}]);
 if(p.endsWith('/voice-profile')){await new Promise(r=>setTimeout(r,1500));if(fail)return route.fulfill({status:400,json:{detail:'参考录音过短'}});registered=true;return json({...teacher,voice_profile_id:'profile1'});}
 if(p.endsWith('/assets')){if(route.request().method()==='POST'){await new Promise(r=>setTimeout(r,1000));assets.push({id:'image1',kind:'image',filename:'形象.png',size:100,url:'/api/assets/image1'});return json(assets.at(-1));}return json(assets);}
 if(p==='/api/speech'){await new Promise(r=>setTimeout(r,1200));if(previewFail)return route.fulfill({status:503,json:{detail:'声音服务暂时不可用'}});const wav=Buffer.alloc(4844);wav.write('RIFF');wav.writeUInt32LE(4836,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(24000,24);wav.writeUInt32LE(48000,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(4800,40);return route.fulfill({contentType:'audio/wav',body:wav});}
 return json([]);
});
try{
 await page.goto('http://127.0.0.1:8011');
 await page.getByRole('button',{name:'教师与素材',exact:true}).click();
 await page.getByLabel('真人 / 卡通参考',{exact:true}).setInputFiles({name:'形象.png',mimeType:'image/png',buffer:Buffer.from('image')});
 await page.getByRole('progressbar').waitFor();
 await page.getByText('素材上传完成',{exact:true}).waitFor();
 await page.getByText('形象处理状态 · 动画驱动待接入',{exact:true}).waitFor();
 await page.getByLabel('参考录音',{exact:true}).selectOption('voice1');
 await page.getByLabel('录音原文',{exact:true}).fill('你好同学，今天我们一起来学习。');
 await page.getByRole('button',{name:'建立声音档案',exact:true}).click();
 await page.getByRole('progressbar',{name:'正在建立老师音色'}).waitFor();
 assert.equal(await page.getByRole('button',{name:'互动课堂',exact:true}).isDisabled(),true);
 await page.screenshot({path:'test-results/material-processing-desktop.png',fullPage:true});
 await page.getByText('老师音色已保存',{exact:true}).waitFor();
 await page.getByRole('button',{name:'生成试听声音',exact:true}).click();
 await page.getByRole('progressbar',{name:'正在生成试听声音'}).waitFor();
 await page.getByText('试听生成未完成',{exact:true}).waitFor();
 assert.equal(await page.getByRole('button',{name:'生成试听声音',exact:true}).isEnabled(),true);
 previewFail=false;await page.getByRole('button',{name:'生成试听声音',exact:true}).click();await page.getByText('试听声音已生成',{exact:true}).waitFor();await page.getByLabel('老师克隆声音试听').waitFor();
 fail=true;
 await page.getByRole('button',{name:'建立声音档案',exact:true}).click();
 await page.getByText('音色建立未完成',{exact:true}).waitFor();
 await page.setViewportSize({width:390,height:844});
 await page.screenshot({path:'test-results/material-processing-mobile.png',fullPage:true});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
 await page.reload();await page.getByRole('button',{name:'教师与素材',exact:true}).click();
 await page.getByText('老师音色 · 已保存',{exact:true}).waitFor();
 assert.deepEqual(errors,[]);
 console.log('PASS: upload acknowledgement, processing, navigation guard, registration success/failure, preview failure retry, saved state after reload, mobile layout');
}finally{await browser.close();}
