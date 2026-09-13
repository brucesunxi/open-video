"""Launch isolated candidate services; no production configuration changes."""
import os, socket, subprocess, sys
from pathlib import Path
root=Path('/workspace/teacher-deploy')
kind=sys.argv[1]
port,module=(8021,'tts_service_candidate') if kind=='tts' else (8041,'musetalk_service')
with socket.socket() as sock:
    if sock.connect_ex(('127.0.0.1',port))==0:raise SystemExit('candidate already running')
env=dict(os.environ,HF_HUB_OFFLINE='1',PYTHONUNBUFFERED='1',TTS_ENGINE='cuda-graph',
         TTS_MODEL_PATH=str(root/'models/Qwen3-TTS-12Hz-1.7B-Base'),VOICE_PROFILE_DIR=str(root/'data/voices'))
with (root/f'logs/{kind}-candidate.log').open('ab') as log:
    child=subprocess.Popen([str(root/'venvs/tts/bin/python'),'-m','uvicorn',module+':app','--host','127.0.0.1','--port',str(port)],
        cwd=root/'gpu',env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
(root/f'{kind}-candidate.pid').write_text(str(child.pid))
print(kind,'candidate',child.pid)
