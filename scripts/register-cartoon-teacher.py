"""Run on the user's GPU host after the explicitly authorized media upload."""
import json,sys
from pathlib import Path
import httpx
from dotenv import load_dotenv
root=Path('/workspace/teacher-deploy');app=root/'teacher-studio'
sys.path.insert(0,str(app));load_dotenv(app/'.env')
from server.auth import make_session,COOKIE
media=Path('/tmp')
with httpx.Client(base_url='http://127.0.0.1:8010',timeout=240,trust_env=False,cookies={COOKIE:make_session()}) as client:
 def call(method,url,**kw):
  response=client.request(method,url,**kw);response.raise_for_status();return response.json()
 teachers=call('GET','/api/teachers')
 teacher=next((t for t in teachers if t['name']=='慈祥老师 · 卡通'),None)
 if teacher is None:
  teacher=call('POST','/api/teachers',json={'name':'慈祥老师 · 卡通','subject':'互动教学','bio':'根据用户提供的老师照片制作卡通形象，使用授权的视频录音建立音色。','style':'语气亲切耐心，先举易懂的例子，再解释知识点，适时鼓励学生提问。','consent':True})
 assets=call('GET',f"/api/teachers/{teacher['id']}/assets")
 result={}
 for filename,kind in [('voice-reference-normalized.wav','voice'),('cartoon-teacher-v2.png','image'),('teacher-reference-30s-55s.mp4','video')]:
  asset=next((a for a in assets if a['filename']==filename),None)
  if asset is None:
   with (media/filename).open('rb') as f:asset=call('POST',f"/api/teachers/{teacher['id']}/assets",data={'kind':kind},files={'file':(filename,f)})
  result[kind]=asset['id']
 teacher=call('PUT',f"/api/teachers/{teacher['id']}",json={**{k:teacher.get(k,'') for k in ['name','subject','bio','style','voice_profile_id']},'consent':True,'avatar_asset_id':result['image']})
 transcript=(media/'teacher-voice-transcript.txt').read_text().strip()
 if not teacher.get('voice_profile_id'):
  teacher=call('POST',f"/api/teachers/{teacher['id']}/voice-profile",json={'asset_id':result['voice'],'transcript':transcript})
 (root/'cartoon-teacher-registration.json').write_text(json.dumps({'teacher_id':teacher['id'],'assets':result},ensure_ascii=False))
 print('Teacher ready:',teacher['id'],'voice profile registered:',bool(teacher.get('voice_profile_id')),flush=True)
