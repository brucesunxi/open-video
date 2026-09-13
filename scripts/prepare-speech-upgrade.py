"""Run on GPU host; additive dependencies and public weights only."""
import os, subprocess, tarfile
from pathlib import Path
root = Path('/workspace/teacher-deploy')
for archive, target in [('faster-qwen-v030.tar.gz', 'vendor/faster-qwen'), ('musetalk-core.tar.gz', 'avatar/MuseTalk')]:
    directory = root / target
    directory.mkdir(parents=True, exist_ok=True)
    with tarfile.open(root / archive) as source:
        source.extractall(directory, filter='data')
env = dict(os.environ, NO_PROXY='*', no_proxy='*', HF_ENDPOINT='https://hf-mirror.com', HF_HUB_OFFLINE='0')
subprocess.run([str(root/'venvs/tts/bin/python'), '-m', 'pip', 'install', '--no-deps', '--index-url',
    'https://pypi.tuna.tsinghua.edu.cn/simple', 'diffusers==0.30.2'], env=env, check=True)
os.environ.update(env)
from huggingface_hub import snapshot_download
models = root/'models/MuseTalk'
for repo, destination, patterns in [
    ('TMElyralab/MuseTalk', models, ['musetalkV15/musetalk.json', 'musetalkV15/unet.pth']),
    ('stabilityai/sd-vae-ft-mse', models/'sd-vae', ['config.json', 'diffusion_pytorch_model.bin']),
    ('openai/whisper-tiny', models/'whisper', ['config.json', 'model.safetensors', 'preprocessor_config.json']),
]:
    snapshot_download(repo, local_dir=str(destination), allow_patterns=patterns, max_workers=2)
print('Upgrade code and weights ready', flush=True)
