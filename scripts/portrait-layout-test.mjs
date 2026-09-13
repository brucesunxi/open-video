import {chromium} from '@playwright/test';import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});const page=await browser.newPage();
await page.route('**/api/teachers',async route=>{const r=await route.fetch();const data=await r.json();await route.fulfill({json:data.map(t=>({...t,avatar_asset_id:'layout-image'}))});});
await page.route('**/api/teachers/*/assets',route=>route.fulfill({json:[{id:'layout-image',kind:'image',url:'/layout-image.svg',filename:'portrait.svg',size:100}]}));
let dims=[480,640];await page.route('**/layout-image.svg',route=>route.fulfill({contentType:'image/svg+xml',body:`<svg xmlns="http://www.w3.org/2000/svg" width="${dims[0]}" height="${dims[1]}"><rect width="100%" height="100%" fill="#93bbae"/><rect x="5" y="5" width="${dims[0]-10}" height="${dims[1]-10}" fill="none" stroke="#255545" stroke-width="10"/></svg>`}));
try{
 for(const width of [1440,390])for(const ratio of [[480,640],[1200,600],[600,600]]){
  dims=ratio;await page.setViewportSize({width,height:950});await page.goto('http://127.0.0.1:8011');
  for(const mode of ['讲课与插问','实时对话']){
   await page.getByRole('button',{name:mode,exact:true}).click();await page.locator('.photo-avatar img').waitFor();
   const geometry=await page.locator('.photo-avatar').evaluate(el=>{const img=el.querySelector('img'),r=el.getBoundingClientRect();return {ratio:r.width/r.height,fit:getComputedStyle(img).objectFit,width:r.width,height:r.height};});
   assert.ok(Math.abs(geometry.ratio-16/9)<.01);assert.equal(geometry.fit,'contain');
   if(mode==='讲课与插问'){const stacked=await page.locator('.teaching-scene').evaluate(el=>el.querySelector('.slide-card').getBoundingClientRect().top>=el.querySelector('.presenter').getBoundingClientRect().bottom);assert.ok(stacked,'人物应在课件上方');}
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
   if(width===1440&&ratio[0]===480&&mode==='实时对话')await page.screenshot({path:'test-results/portrait-fit-desktop.png',fullPage:true});
   const videoBox=await page.locator('.photo-avatar').evaluate(el=>{el.className='portrait-video';el.replaceChildren(document.createElement('video'));const r=el.getBoundingClientRect();return {width:r.width,height:r.height};});
   assert.equal(videoBox.width,geometry.width);assert.equal(videoBox.height,geometry.height);
  }
 }
 console.log('PASS: portrait/landscape/square images in both modes, desktop/mobile, stable video frame, no overflow');
}finally{await browser.close();}
