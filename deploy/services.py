"""Run on the GPU host: python deploy/services.py start|status|stop [studio|asr|tts|all]."""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
import urllib.request

root=Path(os.environ.get('TEACHER_DEPLOY_ROOT','/workspace/teacher-deploy'))
app=root/'teacher-studio'
services={
 'avatar':(8040,root/'venvs/tts/bin/python',['-m','uvicorn','musetalk_service:app','--host','127.0.0.1','--port','8040'],root/'gpu',{}),
 'studio':(8010,app/'.venv/bin/python',['scripts/start.py'],app,{}),
 'asr':(8030,root/'venvs/asr/bin/python',['-m','uvicorn','asr_service:app','--host','127.0.0.1','--port','8030'],root/'gpu',{'ASR_MODEL_PATH':str(root/'models/Qwen3-ASR-0.6B')}),
 'tts':(8020,root/'venvs/tts/bin/python',['-m','uvicorn','tts_service:app','--host','127.0.0.1','--port','8020'],root/'gpu',{'TTS_MODEL_PATH':str(root/'models/Qwen3-TTS-12Hz-1.7B-Base'),'VOICE_PROFILE_DIR':str(root/'data/voices'),'TTS_ENGINE':'cuda-graph'}),
}

def listening(port):
 with socket.socket() as s:
  s.settimeout(1);return s.connect_ex(('127.0.0.1',port))==0

def alive(pid):
 try:return (Path('/proc')/str(pid)/'stat').read_text().split(') ',1)[1].split()[0]!='Z'
 except FileNotFoundError:return False

parser=argparse.ArgumentParser();parser.add_argument('action',choices=['start','status','stop']);parser.add_argument('service',nargs='?',default='all',choices=[*services,'all']);args=parser.parse_args()
for name in (['asr','tts','avatar','studio'] if args.service=='all' else [args.service]):
 port,python,command,cwd,extra=services[name];pidfile=root/(name+'.pid')
 if args.action=='status':
  try:
   op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
   route='/api/health' if name=='studio' else '/health'
   with op.open(f'http://127.0.0.1:{port}{route}',timeout=3) as response: print(name,response.read().decode())
  except Exception as e:print(name,'not ready:',type(e).__name__)
 elif args.action=='start':
  if listening(port):print(name,'already listening');continue
  if pidfile.exists() and alive(int(pidfile.read_text())):print(name,'process exists, check log');continue
  if not python.is_file():raise SystemExit(f'Missing environment: {python}')
  (root/'logs').mkdir(exist_ok=True)
  env=dict(os.environ,**extra,PYTHONUNBUFFERED='1')
  if name!='studio':env['HF_HUB_OFFLINE']='1'
  with (root/'logs'/(name+'.log')).open('ab') as log:
   child=subprocess.Popen([str(python),*command],cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
  pidfile.write_text(str(child.pid));print(name,'started',child.pid,'check status after warmup')
 else:
  if not pidfile.exists():print(name,'no pid record');continue
  pid=int(pidfile.read_text())
  if not alive(pid):print(name,'already stopped');continue
  raw=(Path('/proc')/str(pid)/'cmdline').read_bytes().split(b'\0')
  if str(python).encode() not in raw or not all(x.encode() in raw for x in command):raise SystemExit(f'{name}: PID identity mismatch; no signal sent')
  os.kill(pid,signal.SIGTERM)
  for _ in range(50):
   if not alive(pid):break
   time.sleep(.2)
  else:raise SystemExit(f'{name}: still stopping; inspect log')
  print(name,'stopped')
