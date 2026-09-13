"""Loopback-only Qwen ASR adapter for Teacher Studio. One GPU request at a time."""
import io
import os
import subprocess
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
import imageio_ffmpeg
import soundfile as sf
import torch
from fastapi import FastAPI, UploadFile, HTTPException
from qwen_asr import Qwen3ASRModel

model = None
lock = threading.Lock()

@asynccontextmanager
async def lifespan(app):
    global model
    model = Qwen3ASRModel.from_pretrained(os.environ['ASR_MODEL_PATH'], dtype=torch.bfloat16,
        device_map='cuda:0', max_inference_batch_size=1, max_new_tokens=256)
    yield

app = FastAPI(lifespan=lifespan)

@app.get('/health')
def health():
    return {'ready': model is not None, 'model': 'Qwen3-ASR-0.6B'}

@app.post('/transcribe')
def transcribe(file: UploadFile):
    if not lock.acquire(blocking=False):
        raise HTTPException(429, '语音识别正在处理另一条录音，请稍后重试。')
    try:
        raw = file.file.read(15 * 1024 * 1024 + 1)
        if len(raw)>15*1024*1024: raise HTTPException(413, '录音超过 15MB。')
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'upload'; source.write_bytes(raw)
            out=Path(temp)/'audio.wav'
            try:
                subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-nostdin', '-v','error',
                    '-protocol_whitelist','file,pipe','-i',str(source),'-t','65','-vn','-ac','1','-ar','16000',str(out)],
                    check=True, capture_output=True, timeout=20)
            except (subprocess.SubprocessError, OSError): raise HTTPException(400,'无法读取录音格式。')
            audio, rate=sf.read(out,dtype='float32')
            if len(audio)>60*rate: raise HTTPException(400,'录音不能超过 60 秒。')
            started=time.perf_counter()
            result=model.transcribe(audio=(audio,rate),language='Chinese')
            return {'text':result[0].text,'inference_seconds':round(time.perf_counter()-started,3)}
    finally:
        lock.release()
