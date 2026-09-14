"""Retain reference skin identity outside expressive eye and mouth regions."""
import cv2
import numpy as np


def retain_reference(frame, source, box):
    source = cv2.resize(source, (frame.shape[1], frame.shape[0]))
    # Backward flow: each generated pixel samples the corresponding reference pixel.
    flow = cv2.calcOpticalFlowFarneback(cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY),
        cv2.cvtColor(source, cv2.COLOR_RGB2GRAY), None, .5, 4, 25, 4, 7, 1.5, 0)
    yy, xx = np.mgrid[:frame.shape[0], :frame.shape[1]].astype(np.float32)
    aligned = cv2.remap(source, xx+flow[...,0], yy+flow[...,1], cv2.INTER_LINEAR,
                        borderMode=cv2.BORDER_REFLECT_101)
    x1,y1,x2,y2=box;w=x2-x1;h=y2-y1
    face = np.clip((1-((xx-(x1+w*.5))/(w*.58))**2-((yy-(y1+h*.47))/(h*.65))**2)*5,0,1)
    # Preserve generated blinking and speech; protect the rest from neural smoothing.
    def ellipse(cx,cy,rx,ry):
        return np.clip((1-((xx-cx)/rx)**2-((yy-cy)/ry)**2)*4,0,1)
    eyes=np.maximum(ellipse(x1+w*.30,y1+h*.39,w*.22,h*.13),
                    ellipse(x1+w*.70,y1+h*.39,w*.22,h*.13))
    mouth=ellipse(x1+w*.50,y1+h*.76,w*.34,h*.21)
    alpha=cv2.GaussianBlur((face*(1-eyes)*(1-mouth)).astype(np.float32),(9,9),0)[...,None]*.90
    return np.ascontiguousarray(np.clip(aligned*alpha+frame*(1-alpha),0,255).astype(np.uint8))
