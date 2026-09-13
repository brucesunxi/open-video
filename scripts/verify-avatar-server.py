"""Run on GPU server from app directory with the TTS Python. Keeps private media on server."""
import asyncio,time,tempfile,os,sys
from pathlib import Path
import httpx,cv2,numpy as np
sys.path.insert(0,str(Path.cwd()))
from server.store import Store
from server import providers
os.environ['TTS_BASE_URL']='http://127.0.0.1:8020'
store=Store(Path('/workspace/teacher-deploy/data'))
t=next(t for t in store.list('teacher') if t.get('voice_profile_id') and t.get('avatar_asset_id'));a=store.get('asset',t['avatar_asset_id'])
async def run():
 audio,mime=await providers.synthesize('你好，同学。',t)
 started=time.monotonic()
 async with httpx.AsyncClient(timeout=120,trust_env=False) as c:
  r=await c.post('http://127.0.0.1:8040/render',files={'image':('image.jpg',(store.root/'assets'/a['stored_name']).read_bytes()),'audio':('audio.wav',audio)})
 print('render_status',r.status_code,'elapsed',round(time.monotonic()-started,2),flush=True)
 if r.status_code!=200:raise RuntimeError(r.text[:1500])
 with tempfile.NamedTemporaryFile(suffix='.mp4') as f:
  f.write(r.content);f.flush();cap=cv2.VideoCapture(f.name);frames=[]
  while True:
   ok,frame=cap.read()
   if not ok:break
   frames.append(frame)
  cap.release()
  assert len(frames)>10
  change=float(np.abs(frames[0].astype(float)-frames[len(frames)//2]).mean())
  assert change>0.5
  print('frames',len(frames),'shape',frames[0].shape,'mean_change',round(change,2))
asyncio.run(run())
