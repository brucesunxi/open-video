import {useEffect,useRef} from 'react';
import type {Slide} from './types';
// Anchors refer to the unchanged narration, never to elapsed wall-clock time.
const anchors:Record<string,string[]>={
 '从熟悉的加法出发':['两个苹果','七分之二','你发现了吗'],
 '一张纸，两个不同的分法':['两张同样大小','一张平均','另一张平均','这两份一样大吗'],
 '换一种分法，大小不变':['原来的一半','原来的三分之一','现在每一小份','注意'],
 '你已经会算了':['所以','三个六分之一','分母为什么','会说出'],
 '为什么不能得到五分之二？':['有人','这提醒','五分之二比','六分之五比'],
 '把发现整理成方法':['叫作通分','分数的基本性质','公分母','最后'],
 '换一道题，你来迁移':['四分之一加','四和六','四分之一变成','现在请你'],
 '带着一个道理走出去':['六分之一加','二分之一加四分之一','不必','今天我们']
};
export function boardOffsets(slide:Slide){return slide.bullets.map((_,i)=>{const anchor=slide.board_anchors?.[i] || anchors[slide.title]?.[i];const offset=anchor?slide.narration.indexOf(anchor):-1;return offset>=0?offset:Math.floor(slide.narration.length*i/slide.bullets.length);});}
function Maths({text}:{text:string}){return <>{text.split(/(\d+\/\d+)/g).map((part,i)=>/^\d+\/\d+$/.test(part)?<span className="board-fraction" key={i} aria-label={part}><span>{part.split('/')[0]}</span><span>{part.split('/')[1]}</span></span>:<span key={i}>{part}</span>)}</>;}
export function LessonBoard({slide,offset,all=false,embedded=false}:{slide:Slide;offset:number;all?:boolean;embedded?:boolean}){
 const offsets=boardOffsets(slide);const visible=offsets.map(o=>all||offset>=o);const active=offsets.reduce((best,o,i)=>visible[i]&&(best<0||o>=offsets[best])?i:best,-1);
 const board=useRef<HTMLElement>(null);
 useEffect(()=>{if(!embedded||!board.current)return;const line=board.current.querySelector<HTMLElement>('.board-line.current');if(line)board.current.scrollTop=Math.max(0,line.offsetTop-board.current.offsetTop-board.current.clientHeight+line.offsetHeight+16);},[active,embedded,slide.id]);
 const preview=!all&&!visible.some(Boolean);
 const previewPoints=slide.bullets.filter(b=>b.trim()).slice(0,3);
 return <section ref={board} className={`lesson-board ${embedded?'embedded-board':''}`} aria-label="同步课堂板书"><header><span>随讲板书</span><span>想一想 · 说理由</span></header><h2>{slide.title}</h2>{preview?<div className="board-preview"><div className="board-preview-label">这一页，先看一看</div>{previewPoints.length?<ol>{previewPoints.map((text,i)=><li key={i}><span className="preview-index">0{i+1}</span><p><Maths text={text}/></p></li>)}</ol>:<p className="preview-empty">带着好奇，听老师讲一讲。</p>}<div className="board-preview-hint">带着问题开始 · 跟着老师一起想</div></div>:<div className="board-writing">{slide.bullets.map((b,i)=><div key={i} className={`board-line ${visible[i]?'written':''} ${active===i?'current':''}`} aria-hidden={!visible[i]}><span className="board-number">{i+1}</span><p><Maths text={b}/></p></div>)}</div>}</section>;
}
