import assert from 'node:assert/strict';
import {mkdtemp,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {createRequire} from 'node:module';
import {build} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const work=await mkdtemp(resolve('node_modules/.board-preview-'));
try{
 const file=join(work,'board.cjs');
 await build({entryPoints:[resolve('web/LessonBoard.tsx')],outfile:file,bundle:true,platform:'node',format:'cjs',jsx:'automatic',external:['react','react/jsx-runtime']});
 const {LessonBoard,boardOffsets}=createRequire(import.meta.url)(file);
 const render=(slide,offset,all=false)=>renderToStaticMarkup(React.createElement(LessonBoard,{slide,offset,all}));
 let count=0;
 for(const name of ['fraction-division-integer','grade5-fraction-addition']){
  const course=JSON.parse(await readFile(`lessons/${name}.json`,'utf8'));
  for(const slide of course.slides){
   const before=render(slide,-1);
   assert.ok(before.includes('board-preview-label'),slide.title);
   assert.equal((before.match(/class="preview-index"/g)||[]).length,Math.min(3,slide.bullets.length));
   const embedded=renderToStaticMarkup(React.createElement(LessonBoard,{slide,offset:slide.narration.length,embedded:true}));
   assert.ok(embedded.includes('embedded-board'));
   assert.ok(embedded.includes(slide.title));
   const offsets=boardOffsets(slide);
   const first=Math.min(...offsets);
   assert.ok(!render(slide,first).includes('board-preview-label'),slide.title);
   const finished=render(slide,slide.narration.length);
   assert.equal((finished.match(/aria-hidden="false"/g)||[]).length,slide.bullets.length);
   assert.ok(!finished.includes('北京简融'),'Company attribution belongs outside the board');
   assert.ok(!render(slide,-1,true).includes('board-preview-label'),'Silent reading shows all board content');
   count++;
  }
 }
 assert.ok(render({title:'待开始',bullets:[],narration:''},-1).includes('带着好奇'));
 console.log(`PASS: ${count} lesson pages — initial preview, first-anchor transition, complete board, silent reading, empty content.`);
}finally{await rm(work,{recursive:true,force:true});}
