import asyncio
import json
import httpx
import pytest
from server import providers


def mock_client(monkeypatch, handler):
    original=httpx.AsyncClient
    monkeypatch.setattr(providers.httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))


def test_tts_contract(monkeypatch):
    monkeypatch.setenv('TTS_BASE_URL','http://gpu.local:8020')
    monkeypatch.setenv('TTS_API_KEY','secret')
    def handler(request):
        assert str(request.url)=='http://gpu.local:8020/synthesize'
        assert request.headers['Authorization']=='Bearer secret'
        assert json.loads(request.content)['voice_profile_id']=='voice-v1'
        return httpx.Response(200,content=b'RIFF-example',headers={'Content-Type':'audio/wav'})
    mock_client(monkeypatch,handler)
    audio,mime=asyncio.run(providers.synthesize('你好',{'voice_profile_id':'voice-v1'}))
    assert mime=='audio/wav' and audio.startswith(b'RIFF')


def test_tts_rejects_json_instead_of_audio(monkeypatch):
    monkeypatch.setenv('TTS_BASE_URL','http://gpu.local')
    mock_client(monkeypatch,lambda request:httpx.Response(200,json={'url':'not-supported'}))
    with pytest.raises(ValueError):asyncio.run(providers.synthesize('你好',{}))


def test_asr_contract(monkeypatch):
    monkeypatch.setenv('ASR_BASE_URL','http://gpu.local:8030')
    def handler(request):
        assert request.url.path=='/transcribe'
        assert b'name="file"' in request.content
        return httpx.Response(200,json={'text':'什么是蒸发？'})
    mock_client(monkeypatch,handler)
    assert asyncio.run(providers.transcribe(b'audio','recording.webm'))=='什么是蒸发？'


def test_llm_fabricated_citation_falls_back(monkeypatch):
    monkeypatch.setenv('LLM_API_KEY','secret')
    source={'id':'source1','text':'蒸发发生在液体表面。'}
    fake={'answer':'外部知识','citations':[{'id':'source1','quote':'这是不存在的原文'}]}
    mock_client(monkeypatch,lambda request:httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(fake)}}]}))
    r=asyncio.run(providers.answer('蒸发是什么',[source],{}))
    assert r['mode']=='extractive' and '外部知识' not in r['answer']


def test_llm_valid_citations(monkeypatch):
    monkeypatch.setenv('LLM_API_KEY','secret')
    source={'id':'source1','text':'蒸发发生在液体表面。'}
    result={'answer':'蒸发发生在液体表面。','citations':[{'id':'source1','quote':'蒸发发生在液体表面。'}]}
    mock_client(monkeypatch,lambda request:httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(result)}}]}))
    r=asyncio.run(providers.answer('蒸发是什么',[source],{}))
    assert r['mode']=='llm' and r['sources']==[source]


def test_model_headers_omit_empty_key(monkeypatch):
    from server.providers import model_headers
    monkeypatch.delenv('ASR_API_KEY',raising=False)
    assert model_headers('ASR_API_KEY')=={}
    monkeypatch.setenv('ASR_API_KEY','secret')
    assert model_headers('ASR_API_KEY')=={'Authorization':'Bearer secret'}


def test_general_chat_display_note_not_spoken_and_history(monkeypatch):
    monkeypatch.setenv('LLM_API_KEY','secret')
    def handler(request):
        payload=json.loads(request.content)
        assert any(m['content']=='我喜欢科学。' for m in payload['messages'])
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'answer':'你好！你想聊什么科学问题？','citations':[]})}}]})
    mock_client(monkeypatch,handler)
    r=asyncio.run(providers.answer('你好',[],{},[{'role':'user','text':'我喜欢科学。'}]))
    assert r['answer'].endswith(providers.GENERAL_NOTE)
    assert r['speech_text']=='你好！你想聊什么科学问题？'
    assert providers.GENERAL_NOTE not in r['speech_text']
    assert r['grounded'] is False and r['sources']==[]


def test_unrelated_evidence_allows_general_chat(monkeypatch):
    monkeypatch.setenv('LLM_API_KEY','secret')
    mock_client(monkeypatch,lambda request:httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'answer':'你好呀！','citations':[]})}}]}))
    r=asyncio.run(providers.answer('你好',[{'id':'water','text':'水可以蒸发。'}],{}))
    assert r['mode']=='general' and not r['sources']
    assert r['answer'].endswith(providers.GENERAL_NOTE)


def test_tts_waits_for_busy_service(monkeypatch):
    monkeypatch.setenv('TTS_BASE_URL','http://gpu.local')
    calls=[]
    def handler(request):
        calls.append(request)
        if len(calls)==1:return httpx.Response(429)
        return httpx.Response(200,content=b'RIFF-ok',headers={'Content-Type':'audio/wav'})
    mock_client(monkeypatch,handler)
    audio,_=asyncio.run(providers.synthesize('你好',{'voice_profile_id':'test'}))
    assert audio==b'RIFF-ok' and len(calls)==2


def test_chat_retries_invalid_response(monkeypatch):
    monkeypatch.setenv('LLM_API_KEY','secret')
    calls=[]
    def handler(request):
        calls.append(request)
        content='{"answer":' if len(calls)==1 else json.dumps({'answer':'孙同学，你好！','citations':[]})
        return httpx.Response(200,json={'choices':[{'message':{'content':content}}]})
    mock_client(monkeypatch,handler)
    result=asyncio.run(providers.answer('我是孙同学',[],{}))
    assert result['speech_text']=='孙同学，你好！' and len(calls)==2


def test_chat_accepts_fenced_json_and_bounds_empty_retries(monkeypatch):
    monkeypatch.setenv('LLM_API_KEY','secret')
    mock_client(monkeypatch,lambda r:httpx.Response(200,json={'choices':[{'message':{'content':'```json\n{"answer":"你好！","citations":[]}\n```'}}]}))
    assert asyncio.run(providers.answer('你好',[],{}))['speech_text']=='你好！'
