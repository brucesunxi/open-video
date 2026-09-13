"""Loopback-only teacher voice service. Reference profiles stay on server disk."""
import io
import json
import os
import re
import subprocess
import tempfile
import threading
import time
import uuid
import sys
import logging
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path

import imageio_ffmpeg
import soundfile as sf
import torch
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from qwen_tts import Qwen3TTSModel

model = None
prompt_model = None
fast = os.environ.get('TTS_ENGINE', 'standard') == 'cuda-graph'
lock = threading.Lock()
prompts = OrderedDict()
root = Path(os.environ.get('VOICE_PROFILE_DIR', '/workspace/teacher-deploy/data/voices'))

@asynccontextmanager
async def lifespan(app):
    global model, prompt_model
    root.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(4)
    if fast:
        sys.path.insert(0, os.environ.get('FASTER_QWEN_REPO', '/workspace/teacher-deploy/vendor/faster-qwen'))
        from faster_qwen3_tts import FasterQwen3TTS
        model = FasterQwen3TTS.from_pretrained(os.environ['TTS_MODEL_PATH'],
            device='cuda:0', dtype=torch.bfloat16, attn_implementation='sdpa')
        model._warmup(prefill_len=100)  # pinned v0.3.0 API; capture before health becomes ready
        prompt_model = model.model
    else:
        model = Qwen3TTSModel.from_pretrained(os.environ['TTS_MODEL_PATH'],
            device_map='cuda:0', dtype=torch.bfloat16, attn_implementation='sdpa')
        prompt_model = model
    # Prepare saved teacher prompts and the decoder before accepting the first chat.
    if fast:
        profiles=sorted(root.glob('*/profile.json'),key=lambda p:p.stat().st_mtime)[-4:]
        for path in profiles:
            profile=json.loads(path.read_text())
            if not profile.get('consent') or not re.fullmatch('[a-f0-9]{32}',path.parent.name):continue
            prompts[path.parent.name]=prompt_model.create_voice_clone_prompt(
                ref_audio=str(path.parent/'reference.wav'),ref_text=profile['transcript'],x_vector_only_mode=False)
        if prompts:
            model.generate_voice_clone(text='你好，同学。',language='Chinese',voice_clone_prompt=next(iter(prompts.values())),
                max_new_tokens=128,append_silence=False)
    yield

app = FastAPI(lifespan=lifespan)

@app.get('/health')
def health():
    return {'ready': model is not None, 'model': Path(os.environ['TTS_MODEL_PATH']).name,
            'engine': 'cuda-graph' if fast else 'standard'}

@app.post('/profiles')
def register(file: UploadFile, transcript: str = Form(...), consent: bool = Form(False)):
    if not consent: raise HTTPException(400, '请先确认老师的声音使用授权。')
    if not transcript.strip() or len(transcript)>2000:
        raise HTTPException(400, '请填写参考录音对应的准确文字，最多 2000 字。')
    raw=file.file.read(15*1024*1024+1)
    if len(raw)>15*1024*1024: raise HTTPException(413, '参考录音超过 15MB。')
    with tempfile.TemporaryDirectory() as temp:
        source=Path(temp)/'upload'; source.write_bytes(raw)
        target=Path(temp)/'reference.wav'
        try:
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-nostdin', '-v','error',
                '-protocol_whitelist','file,pipe','-i',str(source),'-t','31','-vn','-ac','1','-ar','24000',str(target)],
                check=True,capture_output=True,timeout=20)
            info=sf.info(target)
        except (subprocess.SubprocessError,OSError,RuntimeError):
            raise HTTPException(400, '无法读取参考录音。')
        if not 3<=info.duration<=30: raise HTTPException(400, '请选择 3–30 秒清晰、单人讲话的录音。')
        pid=uuid.uuid4().hex
        directory=root/pid; directory.mkdir(mode=0o700)
        (directory/'reference.wav').write_bytes(target.read_bytes())
        (directory/'profile.json').write_text(json.dumps({'transcript':transcript.strip(),'consent':True,
            'created_at':time.time()},ensure_ascii=False))
    return {'voice_profile_id':pid,'duration':info.duration}

class Synthesis(BaseModel):
    text: str = Field(min_length=1,max_length=2000)
    voice_profile_id: str
    format: str = 'wav'

@app.post('/synthesize')
def synthesize(body: Synthesis):
    if not re.fullmatch('[a-f0-9]{32}',body.voice_profile_id): raise HTTPException(404,'音色不存在。')
    directory=root/body.voice_profile_id
    if not (directory/'profile.json').is_file(): raise HTTPException(404,'音色不存在。')
    if not lock.acquire(blocking=False): raise HTTPException(429,'声音服务正在生成，请稍后重试。')
    try:
        started=time.perf_counter()
        if body.voice_profile_id not in prompts:
            profile=json.loads((directory/'profile.json').read_text())
            prompts[body.voice_profile_id]=prompt_model.create_voice_clone_prompt(
                ref_audio=str(directory/'reference.wav'),ref_text=profile['transcript'],x_vector_only_mode=False)
            while len(prompts)>4: prompts.popitem(last=False)
        prompts.move_to_end(body.voice_profile_id)
        extra={}
        if fast:
            profile=json.loads((directory/'profile.json').read_text())
            extra={'ref_text':profile['transcript'],'append_silence':False}
        wavs,rate=model.generate_voice_clone(text=body.text,language='Chinese',
            voice_clone_prompt=prompts[body.voice_profile_id],max_new_tokens=2048,**extra)
        elapsed=time.perf_counter()-started
        logging.getLogger('teacher.tts').warning('tts engine=%s chars=%d seconds=%.3f audio=%.3f',
            'cuda-graph' if fast else 'standard',len(body.text),elapsed,len(wavs[0])/rate)
        out=io.BytesIO(); sf.write(out,wavs[0],rate,format='WAV',subtype='PCM_16')
        return Response(out.getvalue(),media_type='audio/wav',headers={
            'X-Inference-Seconds':str(round(time.perf_counter()-started,3))})
    finally:
        lock.release()
