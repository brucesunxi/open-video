import {chromium} from '@playwright/test';
import {build} from 'esbuild';
import fs from 'node:fs';
import assert from 'node:assert/strict';
const bundle=await build({stdin:{contents:`import React from 'react';import {createRoot} from 'react-dom/client';import {LessonBoard,boardOffsets} from './web/LessonBoard';const root=createRoot(document.getElementById('board'));window.showBoard=(slide,offset,all)=>root.render(<LessonBoard slide={slide} offset={offset} all={all} embedded/>);window.offsets=boardOffsets;`,resolveDir:process.cwd(),loader:'tsx'},bundle:true,write:false,format:'iife',platform:'browser'});
const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
let count=0;
try{
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const courses=['fraction-division-integer','grade5-fraction-addition'].map(n=>JSON.parse(fs.readFileSync(`lessons/${n}.json`)));
 const css=fs.readFileSync('web/style.css','utf8');
 const portrait='data:image/png;base64,'+fs.readFileSync('output/teacher-standing/standing-blackboard.png').toString('base64');
 for(const width of [360,390,430,768,1440]){
 await page.setViewportSize({width,height:950});
 await page.setContent(`<style>${css}</style><div class="lesson-focus" style="margin:12px"><div class="lecture-composition standing-scene"><div class="presenter standing-presenter"><div class="photo-avatar"><img src="${portrait}"></div></div><div id="board"></div></div></div>`);
 await page.addScriptTag({content:bundle.outputFiles[0].text});
 for(const course of courses)for(const slide of course.slides){
 const offsets=await page.evaluate(s=>window.offsets(s),slide);
 // Loading before first anchor, each timed line, end, silent reading, then page reset.
 for(const [offset,all] of [[-1,false],[0,false],...offsets.map(o=>[o,false]),[slide.narration.length,false],[-1,true],[-1,false]]){
 await page.evaluate(({slide,offset,all})=>window.showBoard(slide,offset,all),{slide,offset,all});
 await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
 const geometry=await page.locator('.embedded-board').evaluate(el=>{
 const b=el.getBoundingClientRect(),line=el.querySelector('.board-line.current'),r=line?.getBoundingClientRect();
 return {scroll:el.scrollTop,overflow:el.scrollHeight-el.clientHeight,preview:!!el.querySelector('.board-preview'),font:parseFloat(getComputedStyle(el.querySelector('p')||el).fontSize),current:r?{top:r.top-b.top,bottom:r.bottom-b.top,height:r.height}:null,height:b.height,pageOverflow:document.documentElement.scrollWidth-innerWidth};});
 const label=`${width} ${slide.title} offset=${offset} all=${all}`;
 assert.ok(geometry.pageOverflow<=1,label+' horizontal page overflow');
 if(geometry.preview){assert.ok(geometry.overflow<=2,label+' preview clipped');assert.equal(geometry.scroll,0,label+' stale scroll');}
 if(!all&&geometry.current){assert.ok(geometry.current.top>=-1&&geometry.current.bottom<=geometry.height+1,label+' spoken line clipped');}
 count++;
 }
 }
 if(width===390){const slide=courses[0].slides[0];await page.evaluate(s=>window.showBoard(s,0,false),slide);await page.waitForTimeout(100);await page.screenshot({path:'test-results/embedded-board-loading-390.png'});}
 }
 assert.deepEqual(errors,[]);console.log(`PASS: ${count} board states, 18 slides, 5 screen widths; preview fits, active lines visible, silent/reset states and no overflow`);
}finally{await browser.close();}
