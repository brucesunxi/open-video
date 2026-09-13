"""Compare the existing service and candidate engine. Private audio never leaves server."""
import io, json, sys, time
from pathlib import Path
import httpx, soundfile as sf, torch
root=Path('/workspace/teacher-deploy')
sys.path.insert(0,str(root/'vendor/faster-qwen'))
from faster_qwen3_tts import FasterQwen3TTS
profile=next((root/'data/voices').glob('*/profile.json'))
metadata=json.loads(profile.read_text())
texts=['你好，同学。', '水有三种状态，分别是固态、液态和气态。']
for text in texts:
    started=time.perf_counter()
    response=httpx.post('http://127.0.0.1:8020/synthesize',json={'text':text,'voice_profile_id':profile.parent.name},timeout=120,trust_env=False)
    response.raise_for_status()
    audio,rate=sf.read(io.BytesIO(response.content))
    print('baseline',len(text),'generation',round(time.perf_counter()-started,3),'audio',round(len(audio)/rate,3),flush=True)
torch.set_num_threads(4)
model=FasterQwen3TTS.from_pretrained(str(root/'models/Qwen3-TTS-12Hz-1.7B-Base'),device='cuda:0',dtype=torch.bfloat16)
prompt=model.model.create_voice_clone_prompt(ref_audio=str(profile.parent/'reference.wav'),ref_text=metadata['transcript'],x_vector_only_mode=False)
for text in [texts[0],*texts]:
    started=time.perf_counter()
    audio,rate=model.generate_voice_clone(text=text,language='Chinese',voice_clone_prompt=prompt,ref_text=metadata['transcript'],max_new_tokens=512,append_silence=False)
    print('candidate',len(text),'generation',round(time.perf_counter()-started,3),'audio',round(len(audio[0])/rate,3),flush=True)
