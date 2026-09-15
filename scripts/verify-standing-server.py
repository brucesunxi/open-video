"""Read-only post-rollout checks on the GPU server."""
import sys
from pathlib import Path
import httpx
from dotenv import load_dotenv
app=Path(__file__).resolve().parents[1];sys.path.insert(0,str(app));load_dotenv(app/'.env')
from server.auth import COOKIE,make_session
with httpx.Client(base_url='http://127.0.0.1:8010',cookies={COOKIE:make_session()},trust_env=False,timeout=120) as c:
 def get(path):
  r=c.get(path);r.raise_for_status();return r.json()
 teacher=next(t for t in get('/api/teachers') if t['id']=='teacher_e3b3015cdcfd4b72')
 asset=next(a for a in get('/api/teachers/'+teacher['id']+'/assets') if a['id']==teacher['avatar_asset_id'])
 assert asset['filename'].startswith('站姿'), 'Standing portrait not active yet'
 print('Default:',asset['filename'])
 for course in get('/api/teachers/'+teacher['id']+'/courses'):
  if course['status']!='published':continue
  media=get('/api/courses/'+course['id']+'/playback')
  assert media['ready'],course['title']
  print(course['title'],len(media['pages']),'pages ready')
  r=c.get(media['pages'][0]['url']);r.raise_for_status()
  Path('/tmp/standing-validation-'+course['id']+'.mp4').write_bytes(r.content)
 r=c.post('/api/speech',json={'teacher_id':teacher['id'],'text':'同学们好，我们一起学数学。','animate':True})
 r.raise_for_status();assert r.headers.get('content-type','').startswith('video/')
 Path('/tmp/standing-realtime-validation.mp4').write_bytes(r.content)
 print('Realtime speech returns video with audio')
