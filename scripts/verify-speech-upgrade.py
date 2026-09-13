"""Server-only quality/timing check. No reference audio or credentials exported."""
import io, sys, time, tempfile
from pathlib import Path
import httpx, soundfile as sf, cv2, numpy as np
root=Path('/workspace/teacher-deploy')
sys.path.insert(0,str(root/'teacher-studio'))
from server.store import Store
store=Store(root/'data')
teacher=next(t for t in store.list('teacher') if t.get('voice_profile_id') and t.get('avatar_asset_id'))
asset=store.get('asset',teacher['avatar_asset_id'])
image=(store.root/'assets'/asset['stored_name']).read_bytes()
with httpx.Client(timeout=180,trust_env=False) as client:
    for port in (8021,8041):
        response=client.get(f'http://127.0.0.1:{port}/health');response.raise_for_status();print(response.json(),flush=True)
    started=time.perf_counter()
    response=client.post('http://127.0.0.1:8041/prewarm',files={'image':('portrait.jpg',image)})
    if response.status_code!=200:raise RuntimeError(response.text[:1000])
    print('prewarm_seconds',round(time.perf_counter()-started,3),flush=True)
    for text in ['你好，同学。今天我们一起学习水的三态。', '爸爸买了八个苹果，妈妈把苹果放在桌上。']:
        started=time.perf_counter()
        speech=client.post('http://127.0.0.1:8021/synthesize',json={'text':text,'voice_profile_id':teacher['voice_profile_id']})
        if speech.status_code!=200:raise RuntimeError(speech.text[:1000])
        duration=sf.info(io.BytesIO(speech.content)).duration
        tts_seconds=time.perf_counter()-started
        transcription=client.post('http://127.0.0.1:8030/transcribe',files={'file':('test.wav',speech.content,'audio/wav')})
        print('tts_seconds',round(tts_seconds,3),'audio_seconds',round(duration,3),'source',text,'asr',transcription.json(),flush=True)
        started=time.perf_counter()
        video=client.post('http://127.0.0.1:8041/render',files={'image':('portrait.jpg',image),'audio':('speech.wav',speech.content,'audio/wav')})
        if video.status_code!=200:raise RuntimeError(video.text[:1000])
        print('render_seconds',round(time.perf_counter()-started,3),'bytes',len(video.content),flush=True)
        with tempfile.NamedTemporaryFile(suffix='.mp4') as output:
            output.write(video.content);output.flush();cap=cv2.VideoCapture(output.name)
            fps=cap.get(cv2.CAP_PROP_FPS);count=cap.get(cv2.CAP_PROP_FRAME_COUNT)
            assert abs(count/fps-duration)<.08,(count/fps,duration)
            ok,first=cap.read();cap.set(cv2.CAP_PROP_POS_FRAMES,int(count/2));ok,last=cap.read();cap.release()
            assert ok and first.shape==last.shape==(512,512,3)
            print('fps',fps,'frames',count,'duration_delta',round(count/fps-duration,4),
                  'mean_frame_change',round(float(np.abs(first.astype(float)-last).mean()),3),flush=True)
