"""Publish a revised opening only after its video is ready; reuse unchanged pages."""
import hashlib,json,sys,subprocess,shutil
from pathlib import Path
import httpx
from dotenv import load_dotenv
app=Path(__file__).resolve().parents[1];sys.path.insert(0,str(app));load_dotenv(app/'.env')
from server.auth import COOKIE,make_session
from server.course_playback import playback_signature,join_page,read_page
root=app.parent/'data';lesson=json.loads((app/'lessons/fraction-division-integer.json').read_text())
with httpx.Client(base_url='http://127.0.0.1:8010',timeout=240,trust_env=False,cookies={COOKIE:make_session()}) as c:
 def req(method,path,**kw):
  r=c.request(method,'/api'+path,**kw);r.raise_for_status();return r.json()
 teacher=next(t for t in req('GET','/teachers') if t['id']=='teacher_e3b3015cdcfd4b72')
 courses=req('GET',f"/teachers/{teacher['id']}/courses")
 old=next(t for t in courses if t['title']==lesson['title'] and t['status']=='published')
 if old['slides'][0]['narration']==lesson['slides'][0]['narration']:
  print('Already published',old['id']);raise SystemExit()
 updated=req('POST',f"/courses/{old['id']}/clone")
 slides=updated['slides'];slides[0].update(narration=lesson['slides'][0]['narration'],board_anchors=lesson['slides'][0]['board_anchors'])
 updated=req('PUT',f"/courses/{updated['id']}",json={'title':old['title'],'slides':slides})
 asset=next(a for a in req('GET',f"/teachers/{teacher['id']}/assets") if a['id']==teacher['avatar_asset_id'])
 raw=c.get(asset['url']);raw.raise_for_status()
 signature=playback_signature(updated,teacher,hashlib.sha256(raw.content).hexdigest())
 old_signature=req('GET',f"/courses/{old['id']}/playback")['signature']
 folder=root/'course-playback'/signature;folder.mkdir(exist_ok=True,parents=True)
 for i in range(1,len(slides)):
  assert slides[i]==old['slides'][i]
  assert read_page(root,old_signature,i),'Old page not prepared'
  for ext in ['json','mp4']:shutil.copy2(root/'course-playback'/old_signature/f'{i}.{ext}',folder/f'{i}.{ext}')
 node="import fs from 'node:fs';import {speechChunks} from './deploy/speech-chunks.mjs';process.stdout.write(JSON.stringify(speechChunks(JSON.parse(fs.readFileSync(0,'utf8')),true)));"
 chunks=json.loads(subprocess.check_output(['node','--input-type=module','-e',node],cwd=app,input=json.dumps(slides[0]['narration']).encode()))
 clips=[]
 for i,text in enumerate(chunks):
  r=c.post('/api/speech',json={'teacher_id':teacher['id'],'text':text,'animate':True});r.raise_for_status();assert r.headers['content-type'].startswith('video/')
  clips.append((text,r.content));print('Opening segment',i+1,'/',len(chunks),flush=True)
 join_page(root,signature,0,clips)
 latest=next(t for t in req('GET','/teachers') if t['id']==teacher['id'])
 assert all(latest[k]==teacher[k] for k in ('avatar_asset_id','voice_profile_id','consent'))
 assert req('GET',f"/courses/{updated['id']}/playback")['ready']
 published=req('POST',f"/courses/{updated['id']}/publish")
 print('Published',published['id'],'version',published['version'],'10 pages ready; 9 unchanged pages reused')
