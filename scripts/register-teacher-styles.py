"""Register authorized style variants without changing the selected avatar or voice."""
import sys,json,time
from pathlib import Path
import httpx
from dotenv import load_dotenv
root=Path('/workspace/teacher-deploy');app=root/'teacher-studio'
sys.path.insert(0,str(app));load_dotenv(app/'.env')
from server.auth import make_session,COOKIE
styles={'crayon':'蜡笔绘本','comic':'温暖漫画','watercolor':'水彩童书','animation':'圆润动画'}
with httpx.Client(timeout=240,trust_env=False,cookies={COOKIE:make_session()}) as c:
 teachers=c.get('http://127.0.0.1:8010/api/teachers').json()
 teacher=next(t for t in teachers if t['id']=='teacher_e3b3015cdcfd4b72')
 url=f"http://127.0.0.1:8010/api/teachers/{teacher['id']}/assets"
 assets=c.get(url).json();results=[]
 for style,title in styles.items():
  raw=Path('/tmp',style+'.jpg').read_bytes()
  started=time.monotonic()
  response=c.post('http://127.0.0.1:8040/render',files={'image':(style+'.jpg',raw,'image/jpeg'),'audio':('voice.wav',Path('/tmp/cartoon-test.wav').read_bytes(),'audio/wav')})

  if response.status_code!=200:
   print(style,response.status_code,response.text,flush=True);continue
  Path('/tmp',style+'-preview.mp4').write_bytes(response.content)
  name=title+'.jpg'
  if not any(a['filename']==name for a in assets):
   response=c.post(url,data={'kind':'image'},files={'file':(name,raw,'image/jpeg')});response.raise_for_status()
  results.append({'style':style,'name':title,'rendered':True,'seconds':round(time.monotonic()-started,2)})
  print(results[-1],flush=True)
 (root/'teacher-styles-validation.json').write_text(json.dumps(results,ensure_ascii=False))
