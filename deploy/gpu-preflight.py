#!/usr/bin/env python3
"""Read-only GPU server inventory. No install, process changes or secret environment dumps."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request


def command(args, timeout=12):
    try:
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, timeout=timeout)
        return {'exit': p.returncode, 'output': p.stdout[-16000:]}
    except (OSError, subprocess.TimeoutExpired) as e:
        return {'error': type(e).__name__}


report = {'kind': 'teacher-studio-gpu-preflight-v1', 'gpu': command([
    'nvidia-smi', '--query-gpu=name,memory.total,memory.used,driver_version', '--format=csv']),
    'disk': command(['df', '-h', '/root/test', '/workspace']),
    'tools': {name: shutil.which(name) for name in ['ffmpeg', 'uv', 'node', 'npm', 'nvcc']}}
report['repos'] = {}
for name in ['opentalking', 'omnirt', 'FasterLivePortrait']:
    root = Path('/root/test') / name
    report['repos'][name] = {'exists': root.exists()}
    if root.exists():
        report['repos'][name]['revision'] = command(['git', '-C', str(root), 'rev-parse', 'HEAD'])
        report['repos'][name]['changes'] = command(['git', '-C', str(root), 'status', '--short'])

report['environments'] = {}
probe = """import json, sys, importlib.metadata as m
r={'python':sys.version.split()[0]}
for name in ['torch','torchaudio','tensorrt','onnxruntime-gpu','qwen-tts','qwen-asr','fastapi','transformers']:
 try: r[name]=m.version(name)
 except m.PackageNotFoundError: r[name]=None
print(json.dumps(r))
"""
for path in ['/root/test/opentalking/.venv/bin/python', '/root/test/omnirt/.venv/bin/python',
             '/root/test/venvs/fasterliveportrait-trt8/bin/python']:
    if Path(path).exists():
        report['environments'][path] = command([path, '-c', probe])

# Match process identity; only selected runtime configuration is inspected, never credentials.
allowed = {'OMNIRT_FASTLIVEPORTRAIT_CFG', 'OMNIRT_FASTLIVEPORTRAIT_ROOT',
           'OMNIRT_FASTLIVEPORTRAIT_CHECKPOINTS_DIR', 'OMNIRT_FASTLIVEPORTRAIT_RUNTIME',
           'OMNIRT_FASTLIVEPORTRAIT_LOAD_MODELS', 'OMNIRT_QUICKTALK_RUNTIME'}
report['processes'] = []
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit():
        continue
    try:
        args = (proc / 'cmdline').read_bytes().split(b'\0')
        identities = [os.fsdecode(x) for x in args if
                      x == b'serve-avatar-ws' or x.endswith(b'/opentalking-unified')]
        if not identities:
            continue
        env = dict(os.fsdecode(x).split('=', 1) for x in (proc / 'environ').read_bytes().split(b'\0') if b'=' in x)
        item = {'pid': int(proc.name), 'program': os.fsdecode(args[0]), 'identity': identities,
                'cwd': str((proc / 'cwd').resolve()),
                'runtime': {k: env[k] for k in sorted(allowed) if k in env}}
        report['processes'].append(item)
    except OSError:
        continue

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
report['services'] = {}
for port, path in [(8000, '/health'), (8000, '/models'), (9000, '/v1/audio2video/models')]:
    try:
        with opener.open('http://127.0.0.1:%s%s' % (port, path), timeout=5) as r:
            report['services'][str(port)+path] = json.loads(r.read(64000))
    except Exception as e:
        report['services'][str(port)+path] = {'error': type(e).__name__}
# Route metadata only: do not retrieve runtime-config or API keys.
for port in [8000, 9000]:
    try:
        with opener.open('http://127.0.0.1:%s/openapi.json' % port, timeout=5) as r:
            schema = json.loads(r.read(2000000))
        report['services'][str(port)+'/routes'] = sorted(schema.get('paths', {}))
    except Exception as e:
        report['services'][str(port)+'/routes'] = {'error': type(e).__name__}
print(json.dumps(report, ensure_ascii=False, indent=2))
