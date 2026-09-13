"""GPU host upgrade: validate prerequisites, retain old code, restart managed services."""
import os, signal, subprocess, sys, tarfile, time, shutil
from pathlib import Path
root=Path('/workspace/teacher-deploy');app=root/'teacher-studio'
python=app/'.venv/bin/python';manager=app/'deploy/services.py'
required=[root/'models/MuseTalk/musetalkV15/unet.pth',root/'models/MuseTalk/whisper/model.safetensors',
          root/'vendor/faster-qwen/faster_qwen3_tts/model.py',root/'teacher-studio-source.tar.gz',root/'teacher-studio-web-dist.tar.gz']
for path in required:
    if not path.is_file() or not path.stat().st_size:raise SystemExit(f'Missing prerequisite: {path}')
backup=root/'backups'/f'speech-code-{int(time.time())}';backup.mkdir(parents=True)
for path in [root/'gpu/tts_service.py',root/'gpu/avatar_service.py',manager,app/'server/app.py']:
    shutil.copy2(path,backup/(path.parent.name+'-'+path.name))
for service in ('avatar','tts','studio'):
    subprocess.run([str(python),str(manager),'stop',service],check=True)
for name,module in [('tts','tts_service_candidate:app'),('avatar','musetalk_service:app')]:
    pidfile=root/f'{name}-candidate.pid'
    if not pidfile.exists():continue
    pid=int(pidfile.read_text());proc=Path('/proc')/str(pid)
    try:cmd=(proc/'cmdline').read_bytes().split(b'\0')
    except FileNotFoundError:continue
    if module.encode() not in cmd or str(root/'venvs/tts/bin/python').encode() not in cmd:
        raise SystemExit('Candidate PID identity changed; not signalled')
    os.kill(pid,signal.SIGTERM)
    for _ in range(100):
        try:
            if (proc/'stat').read_text().split(') ',1)[1].split()[0]=='Z':break
        except FileNotFoundError:break
        time.sleep(.1)
    else:raise SystemExit('Candidate still stopping; no duplicate started')
with tarfile.open(root/'teacher-studio-source.tar.gz') as archive:archive.extractall(root,filter='data')
with tarfile.open(root/'teacher-studio-web-dist.tar.gz') as archive:archive.extractall(app,filter='data')
for name in ('tts_service.py','avatar_service.py','musetalk_service.py'):
    shutil.copy2(app/'gpu'/name,root/'gpu'/name)
for service in ('tts','avatar','studio'):
    subprocess.run([str(python),str(manager),'start',service],check=True)
print('Upgrade started; verify service health and warmup. Old code:',backup,flush=True)
