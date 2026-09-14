import asyncio
import io
import os
import zipfile
import pytest
from fastapi.testclient import TestClient
from server.app import create_app
from server import providers


@pytest.fixture
def client(tmp_path, monkeypatch):
    for key in ('APP_TOKEN', 'LLM_API_KEY', 'TTS_BASE_URL', 'ASR_BASE_URL'):
        monkeypatch.delenv(key, raising=False)
    with TestClient(create_app(tmp_path)) as client:
        yield client


def demo(client):
    t=client.post('/api/demo').json()
    c=client.get(f"/api/teachers/{t['id']}/courses").json()[0]
    return t,c


def session(client,t,c=None):
    return client.post('/api/sessions',json={'teacher_id':t['id'],'course_id':c['id'] if c else None}).json()


def test_workflow_and_refusal(client):
    t,c=demo(client)
    s=session(client,t,c)
    start=client.post(f"/api/sessions/{s['id']}/action",json={'revision':0,'action':'start'}).json()
    answer=client.post(f"/api/sessions/{s['id']}/ask",json={'revision':start['revision'],'question':'蒸发是什么？'})
    assert answer.status_code==200, answer.text
    v=answer.json()
    assert v['sources'] and '蒸发' in v['answer'] and v['session']['slide_index']==0
    s=v['session']
    done=client.post(f"/api/sessions/{s['id']}/action",json={'revision':s['revision'],'action':'answer_done'}).json()
    assert done['state']=='PAUSED'
    resumed=client.post(f"/api/sessions/{s['id']}/action",json={'revision':done['revision'],'action':'resume'}).json()
    assert resumed['state']=='LECTURING' and resumed['slide_index']==0
    result=client.post(f"/api/sessions/{s['id']}/ask",json={'revision':resumed['revision'],'question':'量子纠缠的贝尔不等式是什么？'}).json()
    assert not result['grounded'] and result['sources']==[]


def test_teacher_isolation_and_approval(client):
    t,c=demo(client)
    other=client.post('/api/teachers',json={'name':'另一位老师'}).json()
    doc=client.post('/api/documents',json={'teacher_id':other['id'],'title':'秘密资料','text':'火星密码是蓝色山谷。'}).json()
    s=session(client,other)
    r=client.post(f"/api/sessions/{s['id']}/ask",json={'revision':0,'question':'火星密码是什么？'}).json()
    assert not r['grounded']
    client.post(f"/api/documents/{doc['id']}/approve")
    s=session(client,t)
    r=client.post(f"/api/sessions/{s['id']}/ask",json={'revision':0,'question':'火星密码是什么？'}).json()
    assert not r['grounded']
    bad=client.post('/api/sessions',json={'teacher_id':other['id'],'course_id':c['id']})
    assert bad.status_code==400
    bad=client.post('/api/courses',json={'teacher_id':t['id'],'title':'非法课程','document_ids':[doc['id']]})
    assert bad.status_code==400


def test_published_course_immutable_and_snapshot(client):
    t,c=demo(client)
    assert client.put(f"/api/courses/{c['id']}",json={'title':'改名','slides':c['slides']}).status_code==409
    doc=client.post('/api/documents',json={'teacher_id':t['id'],'title':'新增','text':'火星密码是蓝色山谷。'}).json()
    client.post(f"/api/documents/{doc['id']}/approve")
    s=session(client,t,c)
    answer=client.post(f"/api/sessions/{s['id']}/ask",json={'revision':0,'question':'火星密码是什么？'}).json()
    assert answer['sources']==[]
    clone=client.post(f"/api/courses/{c['id']}/clone").json()
    assert clone['status']=='draft' and clone['version']==2 and clone['id']!=c['id']


def test_stale_revision_cannot_move_classroom(client):
    t,c=demo(client);s=session(client,t,c)
    r=client.post(f"/api/sessions/{s['id']}/action",json={'revision':0,'action':'start'})
    assert r.status_code==200
    stale=client.post(f"/api/sessions/{s['id']}/action",json={'revision':0,'action':'next'})
    assert stale.status_code==409
    assert client.get(f"/api/sessions/{s['id']}").json()['slide_index']==0


def test_ask_cancel_drops_late_answer(client, monkeypatch):
    t,c=demo(client);s=session(client,t,c)
    async def slow(*args):
        # Simulate another request changing revision while inference is pending.
        store=client.app.state.store
        current=store.get('session',s['id'])
        store.change_session(s['id'],current['revision'],lambda v:v.update(state='PAUSED'))
        return {'answer':'迟到的答案','sources':[],'grounded':False,'mode':'test'}
    monkeypatch.setattr(providers,'answer',slow)
    r=client.post(f"/api/sessions/{s['id']}/ask",json={'revision':0,'question':'蒸发是什么？'})
    assert r.status_code==409
    state=client.get(f"/api/sessions/{s['id']}").json()
    assert state['state']=='PAUSED' and not any(m['role']=='assistant' for m in state['messages'])


def test_auth_and_cross_origin(client,monkeypatch):
    monkeypatch.setenv('APP_TOKEN','test-access-token-with-24-chars')
    assert client.get('/api/teachers').status_code==401
    assert client.post('/api/login',json={'token':'wrong'}).status_code==401
    assert client.post('/api/login',json={'token':'test-access-token-with-24-chars'}).status_code==200
    assert client.get('/api/teachers').status_code==200
    assert client.post('/api/demo',headers={'Origin':'https://evil.example'}).status_code==403


def test_upload_validation_and_source_extraction(client):
    t,c=demo(client)
    r=client.post(f"/api/teachers/{t['id']}/documents/upload",files={'file':('lesson.txt','新的讲义。知识来自资料。'.encode(),'text/plain')})
    assert r.status_code==200 and not r.json()['approved']
    assert r.json()['chunks'][0]['text']=='新的讲义。知识来自资料。'
    r=client.post(f"/api/teachers/{t['id']}/assets",data={'kind':'image'},files={'file':('bad.html',b'<script/>','text/html')})
    assert r.status_code==400
    other=client.post('/api/teachers',json={'name':'另一老师'}).json()
    asset=client.post(f"/api/teachers/{t['id']}/assets",data={'kind':'image'},files={'file':('a.png',b'fake-image','image/png')}).json()
    assert client.put(f"/api/teachers/{other['id']}",json={'name':'另一老师','avatar_asset_id':asset['id']}).status_code==400
    assert client.post('/api/teachers',json={'name':'新老师','avatar_asset_id':asset['id']}).status_code==400


def test_pptx_contains_editable_text_and_notes(client):
    t,c=demo(client)
    r=client.get(f"/api/courses/{c['id']}/export.pptx")
    assert r.status_code==200,r.text[:500] if r.status_code!=200 else ''
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        slide=z.read('ppt/slides/slide1.xml').decode()
        notes=z.read('ppt/notesSlides/notesSlide1.xml').decode()
        assert '水的三态' in slide and '固态' in slide and '资料依据' in notes
        assert len([n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')])==len(c['slides'])


def test_restart_pauses_and_persists(tmp_path,monkeypatch):
    monkeypatch.delenv('APP_TOKEN',raising=False)
    with TestClient(create_app(tmp_path)) as a:
        t,c=demo(a);s=session(a,t,c)
        a.post(f"/api/sessions/{s['id']}/action",json={'revision':0,'action':'start'})
        a.post(f"/api/sessions/{s['id']}/action",json={'revision':1,'action':'next'})
    with TestClient(create_app(tmp_path)) as b:
        restored=b.get(f"/api/sessions/{s['id']}").json()
        assert restored['state']=='PAUSED' and restored['slide_index']==1
        assert b.get('/api/teachers').json()[0]['id']==t['id']


def test_voice_registration_ownership_and_consent(client, monkeypatch):
    t,_=demo(client)
    other=client.post('/api/teachers',json={'name':'另一位老师','consent':True}).json()
    asset=client.post(f"/api/teachers/{t['id']}/assets",data={'kind':'voice'},
        files={'file':('reference.wav',b'test-audio','audio/wav')}).json()
    calls=[]
    async def register(content, filename, transcript):
        calls.append((content,filename,transcript))
        return 'test-profile'
    monkeypatch.setattr(providers,'register_voice',register)
    body={'asset_id':asset['id'],'transcript':'今天我们学习水的三态。'}
    assert client.post(f"/api/teachers/{other['id']}/voice-profile",json=body).status_code==400
    client.put(f"/api/teachers/{t['id']}",json={**t,'consent':False})
    assert client.post(f"/api/teachers/{t['id']}/voice-profile",json=body).status_code==400
    assert calls==[]
    client.put(f"/api/teachers/{t['id']}",json=t)
    response=client.post(f"/api/teachers/{t['id']}/voice-profile",json=body)
    assert response.status_code==200
    assert response.json()['voice_profile_id']=='test-profile'
    assert calls==[(b'test-audio','reference.wav',body['transcript'])]


def test_password_login_session_and_logout(client, monkeypatch):
    from server.auth import password_hash, COOKIE
    monkeypatch.setenv('APP_TOKEN','old-token-is-never-a-login-now')
    monkeypatch.setenv('APP_USERNAME','demo')
    monkeypatch.setenv('APP_PASSWORD_HASH',password_hash('a-long-demo-password'))
    assert client.get('/api/auth').json()['mode']=='password'
    assert client.get('/api/teachers',headers={'Authorization':'Bearer old-token-is-never-a-login-now'}).status_code==401
    assert client.post('/api/login',json={'token':'old-token-is-never-a-login-now'}).status_code==401
    assert client.post('/api/login',json={'username':'demo','password':'wrong'}).status_code==401
    r=client.post('/api/login',json={'username':'demo','password':'a-long-demo-password'})
    assert r.status_code==200
    assert 'HttpOnly' in r.headers['set-cookie']
    assert client.get('/api/teachers').status_code==200
    assert client.post('/api/logout').status_code==200
    assert client.get('/api/teachers').status_code==401
    client.cookies.set(COOKIE,'9999999999.fake.fake')
    assert client.get('/api/teachers').status_code==401


def test_password_throttle(client,monkeypatch):
    from server.auth import password_hash
    monkeypatch.setenv('APP_PASSWORD_HASH',password_hash('a-long-demo-password'))
    for _ in range(5):
        assert client.post('/api/login',json={'username':'wrong','password':'wrong'}).status_code==401
    assert client.post('/api/login',json={'username':'wrong','password':'wrong'}).status_code==429


def test_session_expiry_and_password_rotation(monkeypatch):
    from server import auth
    monkeypatch.setenv('APP_TOKEN','test-secret')
    monkeypatch.setenv('APP_PASSWORD_HASH','hash-1')
    token=auth.make_session()
    assert auth.valid_session(token)
    monkeypatch.setenv('APP_PASSWORD_HASH','hash-2')
    assert not auth.valid_session(token)
    monkeypatch.setenv('APP_PASSWORD_HASH','hash-1')
    now=auth.time.time()
    monkeypatch.setattr(auth.time,'time',lambda:now+8*3600+1)
    assert not auth.valid_session(token)


def test_animated_speech_and_audio_preview(client, monkeypatch):
    t,_=demo(client)
    image=client.post(f"/api/teachers/{t['id']}/assets",data={'kind':'image'},files={'file':('portrait.jpg',b'image','image/jpeg')}).json()
    client.put(f"/api/teachers/{t['id']}",json={**t,'voice_profile_id':'voice','avatar_asset_id':image['id']})
    monkeypatch.setenv('AVATAR_BASE_URL','http://localhost:8040')
    calls=[]
    async def synth(text, teacher):return b'wave','audio/wav'
    async def animate(image,audio):
        calls.append((image,audio));return b'movie','video/mp4'
    monkeypatch.setattr(providers,'synthesize',synth)
    monkeypatch.setattr(providers,'animate',animate)
    body={'teacher_id':t['id'],'text':'你好'}
    preview=client.post('/api/speech',json=body)
    assert preview.headers['content-type']=='audio/wav' and not calls
    video=client.post('/api/speech',json={**body,'animate':True})
    assert video.headers['content-type']=='video/mp4' and video.content==b'movie'
    assert calls==[(b'image',b'wave')]
    assert 'media;dur=' in video.headers['server-timing']
    cached=client.post('/api/speech',json={**body,'animate':True})
    assert cached.headers['x-media-cache']=='hit' and cached.content==b'movie'
    assert len(calls)==1
    client.put(f"/api/teachers/{t['id']}",json={**t,'consent':False})
    assert client.post('/api/speech',json={**body,'animate':True}).status_code==400


def test_avatar_prewarm_checks_consent_and_asset_kind(client):
    t,_=demo(client)
    route=f"/api/teachers/{t['id']}/prepare-avatar"
    assert client.post(route).status_code==400
    image=client.post(f"/api/teachers/{t['id']}/assets",data={'kind':'image'},
                      files={'file':('portrait.jpg',b'image','image/jpeg')}).json()
    client.put(f"/api/teachers/{t['id']}",json={**t,'avatar_asset_id':image['id'],'consent':False})
    assert client.post(route).status_code==400


def test_speech_stream_order_and_midstream_error(client,monkeypatch):
    import json,base64
    t,_=demo(client)
    client.put(f"/api/teachers/{t['id']}",json={**t,'voice_profile_id':'voice'})
    calls=[]
    async def synth(text, teacher):
        calls.append(text)
        if text=='失败':raise ValueError('internal model error')
        return text.encode(),'audio/wav'
    monkeypatch.setattr(providers,'synthesize',synth)
    body={'teacher_id':t['id'],'chunks':['第一句','第二句'],'animate':False}
    r=client.post('/api/speech/stream',json=body)
    events=[json.loads(line[6:]) for line in r.text.splitlines() if line.startswith('data: ')]
    assert [base64.b64decode(e['data']).decode() for e in events[:-1]]==body['chunks']
    assert [e['index'] for e in events[:-1]]==[0,1]
    assert events[-1]=={'done':True}
    assert r.headers['x-accel-buffering']=='no'
    calls.clear()
    r=client.post('/api/speech/stream',json={**body,'chunks':['第一句','失败','不应生成']})
    events=[json.loads(line[6:]) for line in r.text.splitlines() if line.startswith('data: ')]
    assert calls==['失败'] and 'error' in events[-1]  # First sentence is served from cache.
    assert 'internal model error' not in r.text
    assert client.post('/api/speech/stream',json={**body,'chunks':[' ']}).status_code==400
    client.put(f"/api/teachers/{t['id']}",json={**t,'voice_profile_id':'voice','consent':False})
    assert client.post('/api/speech/stream',json=body).status_code==400


def test_stream_accepts_full_length_slide_segments():
    from server.app import SpeechStream
    body=SpeechStream(teacher_id='teacher',chunks=['教'*10]*200)
    assert sum(map(len,body.chunks))==2000


def test_prepare_course_media_matches_course_and_reuses_cache(client, monkeypatch):
    import time
    t,c=demo(client)
    image=client.post(f"/api/teachers/{t['id']}/assets",data={'kind':'image'},files={'file':('portrait.jpg',b'image','image/jpeg')}).json()
    client.put(f"/api/teachers/{t['id']}",json={**t,'voice_profile_id':'voice','avatar_asset_id':image['id']})
    monkeypatch.setenv('AVATAR_BASE_URL','http://localhost:8040')
    calls=[]
    async def synth(text,teacher):calls.append(text);return b'wave','audio/wav'
    async def animate(image,audio):return b'movie','video/mp4'
    monkeypatch.setattr(providers,'synthesize',synth)
    monkeypatch.setattr(providers,'animate',animate)
    # Rendering is mocked above; exercise durable playback publishing with those bytes.
    import importlib, json
    app_module = importlib.import_module('server.app')
    def join(root, signature, index, clips):
        folder = root/'course-playback'/signature
        folder.mkdir(parents=True, exist_ok=True)
        data = b''.join(data for _, data in clips)
        (folder/f'{index}.mp4').write_bytes(data)
        info = {'size':len(data),'duration':2,'segments':[{'start':0,'duration':2,'offset':0,'length':len(clips[0][0])}]}
        (folder/f'{index}.json').write_text(json.dumps(info))
        return info
    monkeypatch.setattr(app_module, 'join_page', join)
    endpoint=f"/api/courses/{c['id']}/prepare-media"
    assert client.post(endpoint,json={'chunks':[['unrelated']]}).status_code==400
    plan={'chunks':[[s['narration']] for s in c['slides']]}
    job=client.post(endpoint,json=plan).json()
    for _ in range(100):
        status=client.get('/api/media-jobs/'+job['id']).json()
        if status['status'] not in ('queued','preparing'):break
        time.sleep(.02)
    assert status['status']=='ready',status
    assert status['completed']==len(c['slides'])
    count=len(calls)
    r=client.post('/api/speech',json={'teacher_id':t['id'],'text':c['slides'][0]['narration'],'animate':True})
    assert r.headers['x-media-cache']=='hit' and len(calls)==count
    playback = client.get(f"/api/courses/{c['id']}/playback").json()
    assert playback['ready'] and len(playback['pages']) == len(c['slides'])
    url = playback['pages'][0]['url']
    partial = client.get(url, headers={'Range':'bytes=0-1'})
    assert partial.status_code == 206 and partial.content == b'mo'
    assert 'private' in partial.headers['cache-control']
    assert len(calls) == count, 'direct playback must never invoke synthesis'
    client.put(f"/api/teachers/{t['id']}",json={**t,'voice_profile_id':'different','avatar_asset_id':image['id']})
    assert not client.get(f"/api/courses/{c['id']}/playback").json()['ready']
    assert client.get(url).status_code == 404, 'old identity cannot be played after switching voice'
