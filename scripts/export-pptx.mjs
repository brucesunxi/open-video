import pptxgen from 'pptxgenjs';
let input=''; for await (const piece of process.stdin) input+=piece;
const course=JSON.parse(input);
const pptx=new pptxgen(); pptx.layout='LAYOUT_WIDE'; pptx.author='知课 Teacher Studio'; pptx.subject=course.title;
pptx.title=course.title; pptx.lang='zh-CN'; pptx.theme={headFontFace:'Microsoft YaHei',bodyFontFace:'Microsoft YaHei',lang:'zh-CN'};
const bg='F7F8F4', ink='213D35', green='247864';
function base(title, n) {
  const s=pptx.addSlide(); s.background={color:bg};
  s.addShape(pptx.ShapeType.rect,{x:0,y:0,w:.16,h:7.5,fill:{color:green},line:{color:green}});
  s.addText('知课  /  '+course.teacher_snapshot.name,{x:.6,y:.35,w:10,h:.3,fontSize:12,color:green});
  s.addText(title,{x:.6,y:1,w:12,h:1,fontSize:30,bold:true,color:ink,breakLine:false,fit:'shrink'});
  s.addText(`${course.status==='draft'?'草稿 · ':''}第 ${n} 页  /  v${course.version}`,{x:.6,y:7,w:12,h:.25,fontSize:10,color:'737E76'});return s;
}
for(const [i, slide] of course.slides.entries()) {
  const s=base(slide.title,i+1);
  s.addText(slide.bullets.map(text=>({text,options:{bullet:{indent:18},breakLine:true}})),
    {x:.75,y:2.3,w:11.8,h:3.7,fontSize:23,color:ink,paraSpaceAfterPt:22,fit:'shrink',valign:'top'});
  const sources=course.sources.filter(x=>slide.source_ids.includes(x.id));
  s.addText('依据：'+sources.map(x=>`${x.title} · ${x.page?'第'+x.page+'页':'段落'+x.section}`).join('；'),
     {x:.75,y:6.4,w:11.8,h:.4,fontSize:11,color:'737E76',fit:'shrink'});
  s.addNotes(`${slide.narration}\n\n资料依据\n${sources.map(x=>`${x.title} v${x.version}\n${x.text}`).join('\n\n')}`);
}
await pptx.writeFile({fileName:process.argv[2]});
