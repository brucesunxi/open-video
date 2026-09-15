"""Restore generated face crops into their original wide classroom composition."""
import io
import cv2
import numpy as np
from PIL import Image, ImageOps


def reference_crop(raw, size=512):
    image=ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    image.thumbnail((1400,1400))
    rgb=np.array(image)
    detector=cv2.CascadeClassifier(cv2.data.haarcascades+"haarcascade_frontalface_default.xml")
    faces=detector.detectMultiScale(cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY),1.1,5,minSize=(55,55))
    if len(faces)!=1:raise ValueError("需要清晰单人正面形象")
    x,y,w,h=faces[0];side=int(max(w,h)*2.0)
    left=int(x+w/2-side/2);top=int(y+h*.55-side/2)
    return np.array(image.crop((left,top,left+side,top+side)).resize((size,size)))


def prepare_layout(raw):
    image=ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert('RGB')
    image.thumbnail((1400,1400))
    rgb=np.array(image)
    detector=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
    faces=detector.detectMultiScale(cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY),1.1,5,minSize=(55,55))
    if len(faces)!=1:raise ValueError('横屏构图需要清晰的单人正面形象')
    x,y,w,h=faces[0]
    side=int(max(w,h)*2.0);left=int(x+w/2-side/2);top=int(y+h*.55-side/2)
    scale=min(960/rgb.shape[1],540/rgb.shape[0])
    width,height=round(rgb.shape[1]*scale),round(rgb.shape[0]*scale)
    ox,oy=(960-width)//2,(540-height)//2
    canvas=np.full((540,960,3),(233,238,225),dtype=np.uint8)
    canvas[oy:oy+height,ox:ox+width]=cv2.resize(rgb,(width,height))
    edge=max(1,round(side*scale))
    # Fade crop edges to keep the original shoulders, hands and background stable.
    axis=np.minimum(np.arange(edge),np.arange(edge)[::-1])/max(1,edge*.13)
    mask=np.clip(np.minimum(axis[:,None],axis[None,:]),0,1)[...,None].astype(np.float32)
    return canvas,(round(left*scale)+ox,round(top*scale)+oy,edge),mask


def compose_frame(frame,layout):
    canvas,(x,y,size),mask=layout
    result=canvas.copy()
    x1,y1=max(0,x),max(0,y);x2,y2=min(960,x+size),min(540,y+size)
    if x1>=x2 or y1>=y2:return result
    face=cv2.resize(frame,(size,size))[y1-y:y2-y,x1-x:x2-x]
    alpha=mask[y1-y:y2-y,x1-x:x2-x]
    result[y1:y2,x1:x2]=np.clip(face*alpha+result[y1:y2,x1:x2]*(1-alpha),0,255).astype(np.uint8)
    return np.ascontiguousarray(result)


def reference_face_box(raw, size):
    """Map the validated original face into reference_crop coordinates without redetection."""
    image=ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert('RGB')
    image.thumbnail((1400,1400))
    detector=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
    faces=detector.detectMultiScale(cv2.cvtColor(np.array(image),cv2.COLOR_RGB2GRAY),1.1,5,minSize=(55,55))
    if len(faces)!=1:raise ValueError('需要清晰单人正面形象')
    x,y,w,h=map(int,faces[0]);side=int(max(w,h)*2.0)
    left=int(x+w/2-side/2);top=int(y+h*.55-side/2)
    return tuple(round(v*size/side) for v in (x-left,y-top,w,h))
