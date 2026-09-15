import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
const root=process.env.STUDIO_URL;
if(!root||!process.env.STUDIO_PASSWORD)throw Error('Set STUDIO_URL and STUDIO_PASSWORD');
const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
try{
 const context=await browser.newContext();
 const login=await context.request.post(root+'/api/login',{data:{username:process.env.STUDIO_USER||'admin',password:process.env.STUDIO_PASSWORD}});assert.ok(login.ok());
 const teachers=await (await context.request.get(root+'/api/teachers')).json();
 const teacher=teachers.find(t=>t.id==='teacher_e3b3015cdcfd4b72');
 const assets=await (await context.request.get(root+'/api/teachers/'+teacher.id+'/assets')).json();
 const standing=assets.find(a=>a.filename.startsWith('站姿'));assert.ok(standing);
 const page=await context.newPage();
 await page.route('**/api/teachers',route=>route.fulfill({json:teachers.map(t=>t.id===teacher.id?{...t,avatar_asset_id:standing.id}:t)}));const errors=[];page.on('pageerror',e=>errors.push(e.message));
 for(const width of [1440,390]){
 await page.setViewportSize({width,height:950});await page.goto(root,{waitUntil:'domcontentloaded',timeout:90000});
 await page.locator('.standing-scene').waitFor();
 await page.locator('.standing-scene img').evaluate(img=>img.decode());
 await page.waitForTimeout(500);
 const initial=await page.locator('.standing-scene .lesson-board').count();assert.equal(initial,0,'Idle keeps original chalk title');
 await page.getByLabel('声音模式').selectOption('silent');
 await page.locator('.embedded-board').waitFor();
 const bounds=await page.locator('.standing-scene').evaluate(el=>{const a=el.getBoundingClientRect(),b=el.querySelector('.lesson-board').getBoundingClientRect();return {ratio:a.width/a.height,right:(b.right-a.left)/a.width,overflow:document.documentElement.scrollWidth>innerWidth+1};});
 assert.ok(Math.abs(bounds.ratio-16/9)<.05);assert.ok(bounds.right<.5);assert.equal(bounds.overflow,false);
 await page.screenshot({path:`test-results/standing-lesson-${width}.png`,fullPage:true});
 await page.getByRole('button',{name:'实时对话',exact:true}).click();await page.locator('.standing-conversation').waitFor();
 await page.locator('.standing-conversation img').evaluate(img=>img.decode());
 assert.equal(await page.locator('.realtime-stage .lesson-board').count(),0);
 await page.screenshot({path:`test-results/standing-chat-${width}.png`,fullPage:true});
 }
 assert.deepEqual(errors,[]);console.log('PASS: desktop/mobile standing lecture overlay and static conversation chalkboard, no overflow/runtime errors');
}finally{await browser.close();}
