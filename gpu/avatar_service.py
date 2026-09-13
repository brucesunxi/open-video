"""LivePortrait neural portrait animation; loopback service, no InsightFace models.
Audio envelope controls lip opening (not phoneme-level lipsync); gentle pose and blink controls.
"""
import io,os,sys,time,tempfile,threading,hashlib,math,subprocess
from pathlib import Path
from collections import OrderedDict
from contextlib import asynccontextmanager
import cv2
import numpy as np
import torch
import soundfile as sf
import imageio_ffmpeg
from PIL import Image,ImageOps
from fastapi import FastAPI,UploadFile,File,HTTPException
from fastapi.responses import Response
sys.path.insert(0,os.environ.get('LIVEPORTRAIT_REPO','/workspace/teacher-deploy/avatar/LivePortrait'))
from src.config.inference_config import InferenceConfig
from src.live_portrait_wrapper import LivePortraitWrapper

model=None
lock=threading.Lock()
cache=OrderedDict()
@asynccontextmanager
async def lifespan(app):
 global model
 root=Path(os.environ.get('LIVEPORTRAIT_WEIGHTS','/workspace/teacher-deploy/models/LivePortrait'))/'liveportrait'
 cfg=InferenceConfig()
 for key,name in [('F','appearance_feature_extractor'),('M','motion_extractor'),('G','spade_generator'),('W','warping_module')]:
  setattr(cfg,'checkpoint_'+key,str(root/'base_models'/(name+'.pth')))
 cfg.checkpoint_S=str(root/'retargeting_models/stitching_retargeting_module.pth')
 torch.set_num_threads(4)
 model=LivePortraitWrapper(cfg)
 yield
app=FastAPI(lifespan=lifespan)
@app.get('/health')
def health():return {'ready':model is not None,'model':'LivePortrait','motion':'audio-envelope + blink + gentle-head-pose'}

def prepare(raw):
 key=hashlib.sha256(raw).hexdigest()
 if key in cache:cache.move_to_end(key);return cache[key]
 try:
  im=ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert('RGB');im.thumbnail((1400,1400));rgb=np.array(im)
 except Exception:raise HTTPException(400,'无法读取形象图片。')
 detector=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
 faces=detector.detectMultiScale(cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY),scaleFactor=1.1,minNeighbors=5,minSize=(55,55))
 if len(faces)!=1:raise HTTPException(400,'请使用清晰的单人正面照片，当前未能唯一识别人脸。')
 x,y,w,h=faces[0];side=int(max(w,h)*2.0);cx=x+w/2;cy=y+h*.55
 left=int(cx-side/2);top=int(cy-side/2)
 crop=Image.fromarray(rgb).crop((left,top,left+side,top+side)).resize((256,256))
 source=model.prepare_source(np.array(crop));info=model.get_kp_info(source);kp=model.transform_keypoint(info);feature=model.extract_feature_3d(source)
 cache[key]=(info,kp,feature)
 while len(cache)>3:cache.popitem(last=False)
 return cache[key]

@app.post('/render')
def render(image:UploadFile=File(...),audio:UploadFile=File(...)):
 if not lock.acquire(blocking=False):raise HTTPException(429,'形象正在生成，请稍候。')
 try:
  started=time.monotonic();raw=image.file.read(15*1024*1024+1);wav=audio.file.read(10*1024*1024+1)
  if len(raw)>15*1024*1024 or len(wav)>10*1024*1024:raise HTTPException(413,'形象或音频过大。')
  try:samples,rate=sf.read(io.BytesIO(wav),dtype='float32')
  except Exception:raise HTTPException(400,'无法读取声音。')
  if samples.ndim>1:samples=samples.mean(axis=1)
  duration=len(samples)/rate
  if not .1<=duration<=30:raise HTTPException(400,'单段动画声音需在 0.1–30 秒内。')
  with torch.inference_mode():
   info,kp,feature=prepare(raw);fps=20;count=math.ceil(duration*fps)
   rms=np.array([np.sqrt(np.mean(samples[int(i*rate/fps):max(int((i+1)*rate/fps),int(i*rate/fps)+1)]**2)+1e-9) for i in range(count)])
   envelope=np.clip(rms/max(float(np.percentile(rms,90)),.015),0,1)
   envelope=np.convolve(np.pad(envelope,(1,1),mode='edge'),[.2,.6,.2],mode='valid')
   with tempfile.TemporaryDirectory() as tmp:
    tmp=Path(tmp);silent=tmp/'silent.mp4';input_audio=tmp/'voice.wav';output=tmp/'result.mp4';input_audio.write_bytes(wav)
    writer=imageio_ffmpeg.write_frames(str(silent),(512,512),fps=fps,codec='libx264',pix_fmt_in='rgb24',pix_fmt_out='yuv420p',quality=7,output_params=['-preset','ultrafast']);writer.send(None)
    try:
     for i in range(count):
      t=i/fps;motion={k:v.clone() for k,v in info.items()}
      motion['pitch']+=math.sin(t*2.0)*1.0;motion['yaw']+=math.sin(t*1.35)*1.2
      driving=model.transform_keypoint(motion)
      lip=model.retarget_lip(kp,torch.tensor([[.02,float(envelope[i])*.30]],device=kp.device))
      blink=max(0,1-abs((t%3.7)-1.3)/.10)
      eye=model.retarget_eye(kp,torch.tensor([[.30,.30,.30*(1-blink)]],device=kp.device))
      out=model.warp_decode(feature,kp,driving+lip+eye)['out']
      writer.send(np.ascontiguousarray(model.parse_output(out)[0]))
    finally:writer.close()
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-i',str(silent),'-i',str(input_audio),'-c:v','copy','-c:a','aac','-shortest','-movflags','+faststart',str(output)],check=True,capture_output=True,timeout=20)
    return Response(output.read_bytes(),media_type='video/mp4',headers={'X-Render-Seconds':str(round(time.monotonic()-started,2))})
 finally:lock.release()
