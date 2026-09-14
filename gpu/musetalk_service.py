"""Audio-conditioned MuseTalk 1.5 lips on cached LivePortrait motion templates.

The audio track and its Whisper features use the same sample clock (25 fps).
Templates cache neutral lips only; no volume-driven mouth movement is used.
"""
import io, os, sys, time, math, hashlib, tempfile, subprocess, threading, logging
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path
import cv2
import numpy as np
import torch
import soundfile as sf
import imageio_ffmpeg
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import Response
import avatar_service as portrait
from landscape import prepare_layout, compose_frame, reference_crop
from identity_detail import retain_reference

sys.path.insert(0, os.environ.get('MUSETALK_REPO', '/workspace/teacher-deploy/avatar/MuseTalk'))
from musetalk.models.vae import VAE
from musetalk.models.unet import UNet, PositionalEncoding
from musetalk.utils.audio_processor import AudioProcessor
from transformers import WhisperModel

logger=logging.getLogger('teacher.avatar')
FPS=25
TEMPLATE_FRAMES=100
lock=threading.Lock()
templates=OrderedDict()
vae=unet=pe=whisper=processor=None

@asynccontextmanager
async def lifespan(app):
    global vae,unet,pe,whisper,processor
    async with portrait.lifespan(app):
        root=Path(os.environ.get('MUSETALK_WEIGHTS', '/workspace/teacher-deploy/models/MuseTalk'))
        vae=VAE(str(root/'sd-vae'), use_float16=True)
        unet=UNet(str(root/'musetalkV15/musetalk.json'), str(root/'musetalkV15/unet.pth'), use_float16=True, device='cuda:0')
        pe=PositionalEncoding(384).to('cuda:0',dtype=torch.float16)
        whisper=WhisperModel.from_pretrained(str(root/'whisper')).to('cuda:0',dtype=torch.float16).eval()
        vae.vae.eval();unet.model.eval()
        processor=AudioProcessor(str(root/'whisper'))
        # Prepare saved, consented portraits before advertising a ready service.
        # Otherwise a fast first question competes with a cold template on the GPU.
        application=Path(os.environ.get('TEACHER_APP_DIR','/workspace/teacher-deploy/teacher-studio'))
        data=Path(os.environ.get('TEACHER_DATA_DIR','/workspace/teacher-deploy/data'))
        if application.is_dir() and data.is_dir():
            sys.path.insert(0,str(application))
            from server.store import Store
            store=Store(data)
            with torch.inference_mode():
                for teacher in store.list('teacher'):
                    if len(templates)>=2:break
                    if not teacher.get('consent') or not teacher.get('avatar_asset_id'):continue
                    asset=store.get('asset',teacher['avatar_asset_id'])
                    if not asset or asset.get('teacher_id')!=teacher['id'] or asset.get('kind')!='image':continue
                    path=store.root/'assets'/asset['stored_name']
                    if not path.is_file() or path.stat().st_size>15*1024*1024:continue
                    try:prepare(path.read_bytes())
                    except HTTPException:logger.warning('Skipped portrait unsuitable for startup preparation')
        yield

app=FastAPI(lifespan=lifespan)

@app.get('/health')
def health():
    return {'ready':processor is not None,'model':'MuseTalk 1.5 + LivePortrait',
            'motion':'audio-content lipsync + cached blink and head motion','fps':FPS,'prepared_avatars':len(templates),'identity_detail':'reference-skin-v1'}

def prepare(raw):
    key=hashlib.sha256(raw).hexdigest()
    if key in templates:
        templates.move_to_end(key)
        return templates[key]
    started=time.perf_counter()
    model=portrait.model
    info,kp,feature=portrait.prepare(raw)
    frames=[]
    for i in range(TEMPLATE_FRAMES):
        t=i/FPS;phase=2*math.pi*i/TEMPLATE_FRAMES
        motion={k:v.clone() for k,v in info.items()}
        motion['pitch']+=.45*math.sin(phase)+.15*math.sin(2*phase+.3)
        motion['yaw']+=.65*math.sin(phase+.5)
        blink=max(0,1-abs(t-2.35)/.12)
        eye=model.retarget_eye(kp,torch.tensor([[.30,.30,.30*(1-blink)]],device=kp.device))
        out=model.warp_decode(feature,kp,model.transform_keypoint(motion)+eye)['out']
        frames.append(np.ascontiguousarray(model.parse_output(out)[0]))
    detector=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
    faces=detector.detectMultiScale(cv2.cvtColor(frames[0],cv2.COLOR_RGB2GRAY),1.1,5,minSize=(65,65))
    if len(faces)!=1:raise HTTPException(400,'未能定位动画中的嘴部，请使用单人正面照片。')
    x,y,w,h=map(int,faces[0]);size=frames[0].shape[0]
    # A stable face box avoids detector jitter across adjacent generated frames.
    box=(max(0,x),max(0,int(y+h*.03)),min(size,x+w),min(size,int(y+h*1.05)))
    x1,y1,x2,y2=box
    source=reference_crop(raw,frames[0].shape[0])
    frames=[retain_reference(frame,source,box) for frame in frames]
    latents=[]
    for frame in frames:
        face=cv2.resize(frame[y1:y2,x1:x2],(256,256))[:,:,::-1].copy()
        # Deterministic posterior means avoid noise differences between template frames.
        masked=vae.preprocess_img(face,half_mask=True).to(vae.vae.dtype)
        reference=vae.preprocess_img(face).to(vae.vae.dtype)
        latents.append(torch.cat([vae.vae.encode(masked).latent_dist.mode(),
                                 vae.vae.encode(reference).latent_dist.mode()],dim=1)*vae.scaling_factor)
    yy,xx=np.mgrid[:256,:256]
    ellipse=((xx-128)/78)**2+((yy-190)/43)**2
    alpha=np.clip((1-ellipse)*5,0,1).astype(np.float32)
    alpha*=np.clip((yy-118)/25,0,1).astype(np.float32)
    alpha=cv2.GaussianBlur(alpha,(15,15),0)
    alpha=cv2.resize(alpha,(x2-x1,y2-y1))[...,None]
    result={'layout':prepare_layout(raw),'frames':frames,'latents':latents,'box':box,'alpha':alpha,'cursor':0}
    templates[key]=result
    while len(templates)>2:templates.popitem(last=False)
    logger.warning('avatar_template seconds=%.3f frames=%d',time.perf_counter()-started,len(frames))
    return result

@app.post('/prewarm')
def prewarm(image:UploadFile=File(...)):
    if not lock.acquire(False):raise HTTPException(429,'形象服务忙，请稍后重试。')
    try:
        raw=image.file.read(15*1024*1024+1)
        if len(raw)>15*1024*1024:raise HTTPException(413,'形象图片过大。')
        with torch.inference_mode():prepare(raw)
        return {'ready':True}
    finally:lock.release()

@app.post('/render')
def render(image:UploadFile=File(...),audio:UploadFile=File(...)):
    if not lock.acquire(False):raise HTTPException(429,'形象正在生成，请稍候。')
    try:
        started=time.perf_counter()
        raw=image.file.read(15*1024*1024+1);wav=audio.file.read(10*1024*1024+1)
        if len(raw)>15*1024*1024 or len(wav)>10*1024*1024:raise HTTPException(413,'形象或音频过大。')
        try:samples,rate=sf.read(io.BytesIO(wav),dtype='float32')
        except Exception:raise HTTPException(400,'无法读取声音。')
        if samples.ndim>1:samples=samples.mean(axis=1)
        duration=len(samples)/rate
        if not .1<=duration<=30:raise HTTPException(400,'单段动画声音需在 0.1–30 秒内。')
        with torch.inference_mode(),tempfile.TemporaryDirectory() as directory:
            template=prepare(raw)
            prepared=time.perf_counter()
            # Resample the original audio, not text timestamps or an amplitude estimate.
            import torchaudio.functional as AF
            mono=AF.resample(torch.from_numpy(samples),rate,16000).numpy()
            inputs=processor.feature_extractor(mono,return_tensors='pt',sampling_rate=16000).input_features
            chunks=processor.get_whisper_chunk([inputs], 'cuda:0',torch.float16,whisper,len(mono),fps=FPS)
            encoded=time.perf_counter()
            count=len(chunks);offset=template['cursor'];base=Path(directory)
            silent=base/'silent.mp4';voice=base/'voice.wav';output=base/'result.mp4';voice.write_bytes(wav)
            writer=imageio_ffmpeg.write_frames(str(silent),(960,540),fps=FPS,codec='libx264',
                pix_fmt_in='rgb24',pix_fmt_out='yuv420p',quality=None,macro_block_size=2,
                output_params=['-preset','veryfast','-crf','20','-tune','zerolatency','-threads','2'])
            writer.send(None)
            x1,y1,x2,y2=template['box'];alpha=template['alpha']
            try:
                for start in range(0,count,8):
                    indices=[(offset+i)%TEMPLATE_FRAMES for i in range(start,min(start+8,count))]
                    latents=torch.cat([template['latents'][i] for i in indices])
                    features=pe(chunks[start:start+len(indices)].to('cuda:0',dtype=torch.float16))
                    prediction=unet.model(latents,torch.zeros(1,device='cuda:0',dtype=torch.long),encoder_hidden_states=features).sample
                    faces=vae.decode_latents(prediction)
                    for index,face in zip(indices,faces):
                        frame=template['frames'][index].copy()
                        face=cv2.resize(face[:,:,::-1],(x2-x1,y2-y1))
                        frame[y1:y2,x1:x2]=np.clip(face*alpha+frame[y1:y2,x1:x2]*(1-alpha),0,255).astype(np.uint8)
                        writer.send(compose_frame(frame,template['layout']))
            finally:writer.close()
            template['cursor']=(offset+count)%TEMPLATE_FRAMES
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-i',str(silent),'-i',str(voice),
                '-c:v','copy','-c:a','aac','-shortest','-movflags','+faststart',str(output)],check=True,capture_output=True,timeout=20)
            elapsed=time.perf_counter()-started
            logger.warning('avatar_render audio=%.3f prepare=%.3f feature=%.3f total=%.3f frames=%d',duration,prepared-started,encoded-prepared,elapsed,count)
            return Response(output.read_bytes(),media_type='video/mp4',headers={'X-Render-Seconds':str(round(elapsed,3)),'X-Avatar-Driver':'musetalk-1.5'})
    finally:lock.release()
