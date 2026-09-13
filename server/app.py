import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .store import Store, ident, now
from .knowledge import parse_document, chunk_pages, retrieve
from .media_cache import MediaCache
from . import providers
from . import auth as authentication

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')


class TeacherInput(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    subject: str = Field(default='', max_length=100)
    bio: str = Field(default='', max_length=5000)
    style: str = Field(default='', max_length=3000)
    voice_profile_id: str = Field(default='', max_length=200)
    avatar_asset_id: str = ''
    consent: bool = False


class DocumentInput(BaseModel):
    teacher_id: str
    title: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=5, max_length=150000)


class CourseInput(BaseModel):
    teacher_id: str
    title: str = Field(min_length=1, max_length=100)
    document_ids: list[str] = Field(min_length=1, max_length=20)


class Slide(BaseModel):
    id: str
    title: str = Field(min_length=1, max_length=60)
    bullets: list[str] = Field(min_length=1, max_length=5)
    narration: str = Field(min_length=1, max_length=2000)
    source_ids: list[str] = Field(min_length=1)
    gesture: Literal['explain', 'nod', 'encourage', 'think', 'listen', 'idle'] = 'explain'


class CourseEdit(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    slides: list[Slide] = Field(min_length=1, max_length=30)


class SessionInput(BaseModel):
    teacher_id: str
    course_id: str | None = None


class Action(BaseModel):
    revision: int
    action: Literal['start', 'pause', 'resume', 'next', 'previous', 'finish', 'answer_done']


class Ask(BaseModel):
    revision: int
    question: str = Field(min_length=1, max_length=2000)


class Speech(BaseModel):
    animate: bool = False
    teacher_id: str
    text: str = Field(min_length=1, max_length=2000)


class SpeechStream(BaseModel):
    teacher_id: str
    chunks: list[str] = Field(min_length=1, max_length=200)
    animate: bool = True


class CourseMediaPlan(BaseModel):
    chunks: list[list[str]] = Field(min_length=1, max_length=30)


class VoiceRegistration(BaseModel):
    asset_id: str
    transcript: str = Field(min_length=1, max_length=2000)


def create_app(data_dir=None):
    store = Store(Path(data_dir or os.getenv('DATA_DIR', str(ROOT / 'data'))))

    media_cache = MediaCache(store.root)
    media_tasks = set()

    @asynccontextmanager
    async def lifespan(app):
        for job in store.list('media_job'):
            if job['status'] in ('preparing', 'queued'):
                job.update(status='interrupted', message='服务重启，点击重新准备可复用已完成片段。')
                store.put('media_job', job)
        # A process restart must never resume old audio / in-flight generation by itself.
        for s in store.list('session'):
            if s['state'] not in ('FINISHED', 'READY', 'PAUSED'):
                s.update(state='PAUSED', revision=s['revision'] + 1, updated_at=now())
                store.put('session', s)
        yield
        for task in media_tasks:
            task.cancel()
        await asyncio.gather(*media_tasks, return_exceptions=True)

    app = FastAPI(title='知课 Teacher Studio', version='0.1.0', lifespan=lifespan)
    app.state.store = store

    def need(kind, id):
        obj = store.get(kind, id)
        if not obj:
            raise HTTPException(404, '记录不存在。')
        return obj

    def authorized(request):
        if authentication.account_enabled():
            return authentication.valid_session(request.cookies.get(authentication.COOKIE, ''))
        token = os.getenv('APP_TOKEN', '')
        if not token:
            return True
        actual = request.cookies.get('studio_token', '') or request.headers.get('Authorization', '').removeprefix('Bearer ')
        return hmac.compare_digest(actual, token)

    @app.middleware('http')
    async def access(request, call_next):
        if request.url.path.startswith('/api'):
            origin = request.headers.get('origin')
            if request.method not in ('GET', 'HEAD') and origin and urlparse(origin).netloc != request.headers.get('host'):
                # Vite development forwards the original Host header.
                return JSONResponse({'detail': '跨站请求已拒绝。'}, 403)
            if request.url.path not in ('/api/auth', '/api/login', '/api/health') and not authorized(request):
                return JSONResponse({'detail': '请先登录工作台。'}, 401)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        if request.url.path.startswith('/api'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, e):
        return JSONResponse({'detail': str(e)}, 400)

    @app.exception_handler(httpx.HTTPError)
    async def upstream_error(request, e):
        # Do not expose upstream response bodies / keys to the browser.
        return JSONResponse({'detail': '模型服务请求失败，请检查地址、密钥及服务日志。'}, 502)

    @app.get('/api/auth')
    def auth(request: Request):
        return {'authorized': authorized(request), 'required': authentication.required(),
                'mode': 'password' if authentication.account_enabled() else 'token'}

    login_attempts = {}

    @app.post('/api/login')
    async def login(request: Request):
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(400, '登录信息格式错误。')
        if authentication.account_enabled():
            key = request.client.host if request.client else 'unknown'
            now = time.monotonic()
            for ip in list(login_attempts):
                if now - login_attempts[ip][0] > 60:
                    del login_attempts[ip]
            count = login_attempts.get(key, (now, 0))
            if count[1] >= 5 or len(login_attempts) >= 1000:
                raise HTTPException(429, '尝试次数过多，请一分钟后重试。')
            login_attempts[key] = (count[0], count[1] + 1)
            username = str(payload.get('username', ''))
            password = str(payload.get('password', ''))
            valid = len(password) <= 256 and await asyncio.to_thread(
                authentication.check_password, password, os.environ['APP_PASSWORD_HASH'])
            if not valid or not hmac.compare_digest(username.encode(), os.getenv('APP_USERNAME', 'admin').encode()):
                raise HTTPException(401, '用户名或密码不正确。')
            login_attempts.pop(key, None)
            response = JSONResponse({'ok': True})
            response.set_cookie(authentication.COOKIE, authentication.make_session(), httponly=True,
                samesite='strict', secure=os.getenv('APP_COOKIE_SECURE') == '1' or request.url.scheme == 'https',
                max_age=8 * 3600)
            response.delete_cookie('studio_token')
            return response
        if not hmac.compare_digest(str(payload.get('token', '')), os.getenv('APP_TOKEN', '')):
            raise HTTPException(401, '访问令牌不正确。')
        response = JSONResponse({'ok': True})
        response.set_cookie('studio_token', payload.get('token', ''), httponly=True, samesite='strict',
                            secure=request.url.scheme == 'https', max_age=86400)
        return response

    @app.post('/api/logout')
    def logout():
        response = JSONResponse({'ok': True})
        response.delete_cookie(authentication.COOKIE)
        response.delete_cookie('studio_token')
        return response

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'version': '0.1.0'}

    @app.get('/api/config')
    def config():
        return {'mode': 'connected' if os.getenv('LLM_API_KEY') else 'local',
                'llm': {'configured': bool(os.getenv('LLM_API_KEY')), 'model': os.getenv('LLM_MODEL', 'deepseek-chat')},
                'tts': {'configured': bool(os.getenv('TTS_BASE_URL'))},
                'asr': {'configured': bool(os.getenv('ASR_BASE_URL'))},
                'avatar': {'configured': bool(os.getenv('AVATAR_BASE_URL')), 'integration': 'liveportrait' if os.getenv('AVATAR_BASE_URL') else 'pending'},
                'auth_enabled': authentication.required()}

    @app.get('/api/teachers')
    def teachers():
        return store.list('teacher')

    @app.post('/api/teachers')
    def create_teacher(body: TeacherInput):
        if body.avatar_asset_id:
            raise HTTPException(400, '请先创建老师，再上传并选择该老师的形象素材。')
        return store.put('teacher', {**body.model_dump(), 'id': ident('teacher'), 'created_at': now()})

    @app.put('/api/teachers/{teacher_id}')
    def update_teacher(teacher_id: str, body: TeacherInput):
        teacher = need('teacher', teacher_id)
        if body.avatar_asset_id:
            asset = need('asset', body.avatar_asset_id)
            if asset['teacher_id'] != teacher_id or asset['kind'] not in ('image', 'vrm'):
                raise HTTPException(400, '形象素材不属于该老师。')
        return store.put('teacher', {**teacher, **body.model_dump(), 'updated_at': now()})

    @app.get('/api/teachers/{teacher_id}/assets')
    def assets(teacher_id: str):
        need('teacher', teacher_id)
        return store.list('asset', teacher_id)

    @app.post('/api/teachers/{teacher_id}/assets')
    async def upload_asset(teacher_id: str, kind: str = Form(...), file: UploadFile = File(...)):
        need('teacher', teacher_id)
        extensions = {'image': {'.png', '.jpg', '.jpeg', '.webp'}, 'video': {'.mp4', '.mov', '.webm'},
                      'voice': {'.wav', '.mp3', '.m4a', '.ogg'}, 'vrm': {'.vrm'}}
        suffix = Path(file.filename or '').suffix.lower()
        if kind not in extensions or suffix not in extensions[kind]:
            raise HTTPException(400, '素材类型与扩展名不匹配。')
        id = ident('asset')
        path = store.root / 'assets' / (id + suffix)
        size = 0
        digest = hashlib.sha256()
        try:
            with path.open('wb') as out:
                while piece := await file.read(1024 * 1024):
                    size += len(piece)
                    if size > 250 * 1024 * 1024:
                        raise HTTPException(413, '单个素材不能超过 250MB。')
                    digest.update(piece); out.write(piece)
            if not size:
                raise HTTPException(400, '不能上传空文件。')
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return store.put('asset', {'id': id, 'teacher_id': teacher_id, 'kind': kind, 'filename': Path(file.filename).name,
                          'stored_name': path.name, 'size': size, 'sha256': digest.hexdigest(), 'created_at': now(),
                          'url': '/api/assets/' + id, 'status': 'uploaded'})

    @app.get('/api/assets/{asset_id}')
    def read_asset(asset_id: str):
        asset = need('asset', asset_id)
        return FileResponse(store.root / 'assets' / asset['stored_name'])

    @app.post('/api/teachers/{teacher_id}/voice-profile')
    async def voice_profile(teacher_id: str, body: VoiceRegistration):
        teacher = need('teacher', teacher_id)
        if not teacher['consent']:
            raise HTTPException(400, '请先保存老师的声音使用授权。')
        asset = need('asset', body.asset_id)
        if asset['teacher_id'] != teacher_id or asset['kind'] != 'voice':
            raise HTTPException(400, '请选择该老师的声音参考素材。')
        if asset['size'] > 15 * 1024 * 1024:
            raise HTTPException(413, '声音参考最多 15MB，请先截取 3–30 秒录音。')
        content = (store.root / 'assets' / asset['stored_name']).read_bytes()
        pid = await providers.register_voice(content, asset['filename'], body.transcript)
        teacher = need('teacher', teacher_id)
        if not teacher['consent']:
            raise HTTPException(409, '授权已变更，请重新确认。')
        return store.put('teacher', {**teacher, 'voice_profile_id': pid, 'updated_at': now()})

    def save_document(teacher_id, title, pages, original=None):
        need('teacher', teacher_id)
        chunks = chunk_pages(pages)
        if not chunks:
            raise HTTPException(400, '没有提取到文字。扫描 PDF 请先 OCR 后再导入。')
        if len(chunks) > 1500:
            raise HTTPException(400, '文档过大，请拆分导入。')
        return store.put('document', {'id': ident('doc'), 'teacher_id': teacher_id, 'title': title,
              'version': 1, 'approved': False, 'chunks': chunks, 'created_at': now(), 'original': original,
              'sha256': hashlib.sha256(json.dumps(pages, ensure_ascii=False).encode()).hexdigest()})

    @app.get('/api/teachers/{teacher_id}/documents')
    def documents(teacher_id: str):
        need('teacher', teacher_id)
        return store.list('document', teacher_id)

    @app.post('/api/documents')
    def add_document(body: DocumentInput):
        return save_document(body.teacher_id, body.title, [(None, body.text)])

    @app.post('/api/teachers/{teacher_id}/documents/upload')
    async def upload_document(teacher_id: str, file: UploadFile = File(...)):
        content = await file.read(15 * 1024 * 1024 + 1)
        if len(content) > 15 * 1024 * 1024:
            raise HTTPException(413, '知识文档上限 15MB。')
        try:
            pages = await asyncio.to_thread(parse_document, file.filename or '', content)
        except Exception as e:
            raise HTTPException(400, '文档解析失败，请检查文件格式、编码或是否加密。') from e
        return save_document(teacher_id, Path(file.filename).name, pages)

    @app.post('/api/documents/{doc_id}/approve')
    def approve(doc_id: str):
        doc = need('document', doc_id)
        doc['approved'] = True
        doc['approved_at'] = now()
        return store.put('document', doc)

    @app.get('/api/teachers/{teacher_id}/courses')
    def courses(teacher_id: str):
        return store.list('course', teacher_id)

    @app.post('/api/courses')
    def course_create(body: CourseInput):
        teacher = need('teacher', body.teacher_id)
        documents = [need('document', d) for d in dict.fromkeys(body.document_ids)]
        if any(d['teacher_id'] != body.teacher_id or not d['approved'] for d in documents):
            raise HTTPException(400, '只能使用该老师已审核的资料。')
        sources = [{**c, 'document_id': d['id'], 'title': d['title'], 'version': d['version']}
                   for d in documents for c in d['chunks']]
        # Deterministic source-to-course draft, deliberately not advertised as AI generation.
        slides = []
        for i, s in enumerate(sources[:12]):
            sentences = [t.strip('# \n') for t in re.split(r'(?<=[。！？])|\n', s['text']) if t.strip('# \n')]
            slides.append({'id': ident('slide'), 'title': (sentences[0][:28] if sentences else '知识点') or '知识点',
                          'bullets': [t[:140] for t in sentences[:3]] or [s['text'][:140]],
                          'narration': s['text'], 'source_ids': [s['id']], 'gesture': 'explain' if i % 2 else 'nod'})
        return store.put('course', {'id': ident('course'), 'teacher_id': body.teacher_id, 'title': body.title,
             'version': 1, 'status': 'draft', 'slides': slides, 'documents': documents,
             'sources': sources, 'teacher_snapshot': teacher, 'created_at': now(), 'generation': 'source_outline'})

    @app.get('/api/courses/{course_id}')
    def course_get(course_id: str):
        return need('course', course_id)

    @app.put('/api/courses/{course_id}')
    def course_edit(course_id: str, body: CourseEdit):
        course = need('course', course_id)
        if course['status'] != 'draft':
            raise HTTPException(409, '已发布课程不可修改，请复制为新版本。')
        allowed = {s['id'] for s in course['sources']}
        slides = [s.model_dump() for s in body.slides]
        if len({s['id'] for s in slides}) != len(slides):
            raise HTTPException(400, '课件页 ID 不能重复。')
        for slide in slides:
            if not set(slide['source_ids']) <= allowed or any(len(b) > 160 for b in slide['bullets']):
                raise HTTPException(400, '课件引用无效或单条要点超过 160 字。')
        course.update(title=body.title, slides=slides, updated_at=now())
        return store.put('course', course)

    @app.post('/api/courses/{course_id}/clone')
    def clone_course(course_id: str):
        course = need('course', course_id)
        course.update(id=ident('course'), status='draft', version=course['version'] + 1, created_at=now())
        course.pop('published_at', None)
        return store.put('course', course)

    @app.post('/api/courses/{course_id}/publish')
    def publish(course_id: str):
        course = need('course', course_id)
        if not need('teacher', course['teacher_id'])['consent']:
            raise HTTPException(400, '请先在教师资料中确认素材使用授权。')
        if course['status'] == 'published':
            return course
        course.update(status='published', published_at=now())
        return store.put('course', course)

    @app.get('/api/courses/{course_id}/export.pptx')
    async def export(course_id: str):
        course = need('course', course_id)
        output = store.root / 'exports' / (ident('export') + '.pptx')
        def run_export():
            return subprocess.run([os.getenv('NODE_BINARY', 'node'), str(ROOT / 'scripts/export-pptx.mjs'), str(output.resolve())],
                  input=json.dumps(course, ensure_ascii=False), text=True, capture_output=True, timeout=60, cwd=ROOT)
        try:
            result = await asyncio.to_thread(run_export)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise HTTPException(503, 'PPT 导出不可用，请检查 Node.js 和 npm 依赖。') from e
        if result.returncode or not output.exists():
            raise HTTPException(500, 'PPT 导出失败，请检查导出组件。')
        return FileResponse(output, filename=course['title'] + '.pptx',
                            media_type='application/vnd.openxmlformats-officedocument.presentationml.presentation')

    @app.get('/api/teachers/{teacher_id}/sessions')
    def list_sessions(teacher_id: str):
        return store.list('session', teacher_id)[:30]

    @app.post('/api/sessions')
    def session_create(body: SessionInput):
        need('teacher', body.teacher_id)
        if body.course_id:
            course = need('course', body.course_id)
            if course['teacher_id'] != body.teacher_id or course['status'] != 'published':
                raise HTTPException(400, '请选择该老师已发布的课程。')
        return store.put('session', {'id': ident('session'), 'teacher_id': body.teacher_id, 'course_id': body.course_id,
                'state': 'READY', 'revision': 0, 'slide_index': 0, 'messages': [], 'created_at': now(), 'updated_at': now()})

    @app.get('/api/sessions/{session_id}')
    def session_get(session_id: str):
        return need('session', session_id)

    def change(id, revision, mutate):
        try:
            return store.change_session(id, revision, mutate)
        except ValueError as e:
            raise HTTPException(409, str(e)) from e
        except KeyError as e:
            raise HTTPException(404, '会话不存在。') from e

    @app.post('/api/sessions/{session_id}/action')
    def session_action(session_id: str, body: Action):
        session = need('session', session_id)
        course = need('course', session['course_id']) if session['course_id'] else None
        def mutate(s):
            action = body.action
            if s['state'] == 'FINISHED':
                raise HTTPException(409, '课程已结束，请创建新会话。')
            if action in ('start', 'resume'):
                if not course or s['state'] not in ('READY', 'PAUSED'):
                    raise HTTPException(409, '当前状态不能开始讲课。')
                s['state'] = 'LECTURING'
            elif action == 'pause':
                s['state'] = 'PAUSED'
            elif action == 'finish':
                s['state'] = 'FINISHED'
            elif action == 'answer_done':
                if s['state'] != 'ANSWERING':
                    raise HTTPException(409, '当前没有正在回答的问题。')
                s['state'] = 'PAUSED'  # Explicit resume prevents accidental audio after reconnect.
            elif action in ('next', 'previous'):
                if not course or s['state'] == 'ANSWERING':
                    raise HTTPException(409, '当前不能翻页。')
                new = s['slide_index'] + (1 if action == 'next' else -1)
                if new >= len(course['slides']):
                    s['state'] = 'FINISHED'
                else:
                    s['slide_index'] = max(0, new)
        return change(session_id, body.revision, mutate)

    @app.post('/api/sessions/{session_id}/ask')
    async def session_ask(session_id: str, body: Ask):
        s = need('session', session_id)
        if s['state'] == 'FINISHED':
            raise HTTPException(409, '该会话已结束，请新建会话。')
        def reserve(value):
            value['state'] = 'ANSWERING'
            value['messages'].append({'role': 'user', 'text': body.question, 'created_at': now()})
            value['messages'] = value['messages'][-100:]
        reserved = change(session_id, body.revision, reserve)
        teacher = need('teacher', s['teacher_id'])
        docs = need('course', s['course_id'])['documents'] if s['course_id'] else store.list('document', s['teacher_id'])
        sources = await asyncio.to_thread(retrieve, body.question, docs)
        try:
            result = await providers.answer(body.question, sources, teacher, s['messages'])
        except Exception:
            def failed(value):
                value['state'] = 'PAUSED'
            change(session_id, reserved['revision'], failed)
            raise
        def commit(value):
            value['messages'].append({'role': 'assistant', 'text': result['answer'], 'sources': result['sources'],
                                       'mode': result['mode'], 'speech_text': result.get('speech_text', result['answer']), 'created_at': now()})
        updated = change(session_id, reserved['revision'], commit)
        return {'session': updated, **result}

    @app.post('/api/speech')
    async def speech(body: Speech):
        teacher = need('teacher', body.teacher_id)
        if not teacher['consent']:
            raise HTTPException(400, '尚未确认声音使用授权。')
        if not teacher['voice_profile_id']:
            raise HTTPException(400, '请先设置 GPU 服务返回的 voice_profile_id。')
        image = None
        if body.animate and os.getenv('AVATAR_BASE_URL') and teacher.get('avatar_asset_id'):
            asset = need('asset', teacher['avatar_asset_id'])
            if asset['teacher_id'] != teacher['id']:
                raise HTTPException(400, '形象不属于当前老师。')
            if asset['kind'] == 'image':
                image_path = store.root / 'assets' / asset['stored_name']
                if image_path.stat().st_size > 15 * 1024 * 1024:
                    raise HTTPException(413, '动画参考图片最多 15MB。')
                image = image_path.read_bytes()
        identity = {'version': os.getenv('MEDIA_CACHE_VERSION', '1'), 'teacher': teacher['id'],
                    'voice': teacher['voice_profile_id'], 'text': body.text,
                    'image': hashlib.sha256(image).hexdigest() if image else '',
                    'tts': os.getenv('TTS_BASE_URL'), 'avatar': os.getenv('AVATAR_BASE_URL') if image else ''}
        async def produce():
            content, mime = await providers.synthesize(body.text, teacher)
            if image:
                content, mime = await providers.animate(image, content)
            return content, mime
        started = time.perf_counter()
        content, mime, hit = await media_cache.get(identity, produce)
        return Response(content, media_type=mime, headers={
            'X-Media-Cache': 'hit' if hit else 'miss',
            'Server-Timing': f'media;dur={(time.perf_counter()-started)*1000:.1f}'})

    @app.post('/api/courses/{course_id}/prepare-media')
    async def prepare_course_media(course_id: str, body: CourseMediaPlan):
        course = need('course', course_id)
        teacher = need('teacher', course['teacher_id'])
        if not teacher.get('consent') or not teacher.get('voice_profile_id') or not teacher.get('avatar_asset_id') or not os.getenv('AVATAR_BASE_URL'):
            raise HTTPException(400, '请先配置并授权老师音色与动画形象。')
        if course['status'] != 'published' or len(body.chunks) != len(course['slides']):
            raise HTTPException(400, '请先发布课程。')
        for chunks, slide in zip(body.chunks, course['slides']):
            if not chunks or len(chunks)>200 or any(not c.strip() or len(c)>200 for c in chunks) or ''.join(chunks).strip()!=slide['narration'].strip():
                raise HTTPException(400, '准备内容必须与课程讲稿一致。')
        signature = hashlib.sha256(json.dumps([course_id, body.chunks, teacher['voice_profile_id'], teacher['avatar_asset_id'], os.getenv('MEDIA_CACHE_VERSION','1')]).encode()).hexdigest()
        existing = next((j for j in store.list('media_job') if j.get('signature')==signature and j['status'] in ('queued','preparing')), None)
        if existing: return existing
        job = {'id': ident('media'), 'teacher_id': teacher['id'], 'course_id': course_id,
               'signature': signature, 'status': 'queued', 'completed': 0,
               'total': sum(map(len,body.chunks)), 'page': 1, 'message': '等待准备', 'created_at': now()}
        store.put('media_job',job)
        async def prepare():
            try:
                job.update(status='preparing',message='正在生成老师声音与动画')
                store.put('media_job',job)
                for page, chunks in enumerate(body.chunks,1):
                    for text in chunks:
                        latest=need('teacher',teacher['id'])
                        if any(latest.get(k)!=teacher.get(k) for k in ('voice_profile_id','avatar_asset_id')):
                            raise ValueError('老师素材已更换，请重新准备。')
                        result=await speech(Speech(teacher_id=teacher['id'],text=text,animate=True))
                        if not result.media_type.startswith('video/'):
                            raise ValueError('未生成动画，请检查所选形象。')
                        job.update(completed=job['completed']+1,page=page)
                        store.put('media_job',job)
                        await asyncio.sleep(.1)
                job.update(status='ready',message='整课动画已缓存，可以开始讲课')
            except asyncio.CancelledError:
                job.update(status='interrupted',message='准备已中断，可重新准备并复用已完成片段。')
                raise
            except Exception:
                job.update(status='failed',message='准备未完成，请检查模型服务后重试；已完成片段会保留。')
            finally:
                store.put('media_job',job)
        task=asyncio.create_task(prepare());media_tasks.add(task);task.add_done_callback(media_tasks.discard)
        return job

    @app.get('/api/media-jobs/{job_id}')
    def course_media_job(job_id: str):
        return need('media_job', job_id)

    @app.post('/api/teachers/{teacher_id}/prepare-avatar')
    async def prepare_avatar(teacher_id: str):
        teacher = need('teacher', teacher_id)
        if not teacher.get('consent') or not teacher.get('avatar_asset_id'):
            raise HTTPException(400, '请先选择并授权老师形象。')
        asset = need('asset', teacher['avatar_asset_id'])
        if asset['teacher_id'] != teacher_id or asset['kind'] != 'image':
            raise HTTPException(400, '请选择该老师的照片形象。')
        base = os.getenv('AVATAR_BASE_URL', '').rstrip('/')
        if not base: return {'ready': False}
        path = store.root / 'assets' / asset['stored_name']
        if path.stat().st_size > 15 * 1024 * 1024:
            raise HTTPException(413, '动画参考图片最多 15MB。')
        async with httpx.AsyncClient(timeout=120, trust_env=False) as client:
            response = await client.post(base + '/prewarm', files={'image': ('portrait.jpg', path.read_bytes())})
            if response.status_code in (404, 429): return {'ready': False}
            response.raise_for_status()
        return {'ready': True}

    @app.post('/api/speech/stream')
    async def speech_stream(body: SpeechStream, request: Request):
        teacher = need('teacher', body.teacher_id)
        if not teacher.get('consent') or not teacher.get('voice_profile_id'):
            raise HTTPException(400, '请先授权并建立老师音色。')
        if any(not chunk.strip() or len(chunk)>200 for chunk in body.chunks) or sum(map(len,body.chunks))>2000:
            raise HTTPException(400, '语音分段为空或过长。')
        async def events():
            for index, text in enumerate(body.chunks):
                if await request.is_disconnected():return
                try:
                    result = await speech(Speech(teacher_id=body.teacher_id,text=text,animate=body.animate))
                    payload={'index':index,'mime':result.media_type,
                             'data':base64.b64encode(result.body).decode('ascii'),
                             'timing':result.headers.get('server-timing','')}
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    detail=error.detail if isinstance(error,HTTPException) else '声音或画面生成失败，请重新发送。'
                    yield 'data: '+json.dumps({'error':detail},ensure_ascii=False)+'\n\n'
                    return
                yield 'data: '+json.dumps(payload,separators=(',',':'))+'\n\n'
            yield 'data: {"done":true}\n\n'
        return StreamingResponse(events(),media_type='text/event-stream',
                                 headers={'Cache-Control':'no-store','X-Accel-Buffering':'no'})

    @app.post('/api/transcribe')
    async def transcribe(file: UploadFile = File(...)):
        content = await file.read(15 * 1024 * 1024 + 1)
        if len(content) > 15 * 1024 * 1024:
            raise HTTPException(413, '录音不能超过 15MB。')
        return {'text': await providers.transcribe(content, file.filename or 'recording.webm')}

    @app.post('/api/demo')
    def demo():
        existing = store.get('teacher', 'teacher_demo')
        if existing:
            return existing
        teacher = store.put('teacher', {'id': 'teacher_demo', 'name': '林老师 · 示例', 'subject': '小学科学',
              'bio': '用于本地流程体验的虚构教师，不对应真实人物。', 'style': '先观察生活现象，再讲原理，最后提出一个小问题。',
              'voice_profile_id': '', 'avatar_asset_id': '', 'consent': True, 'created_at': now()})
        doc = save_document(teacher['id'], '示例讲义 · 水的三态', [(None,
            '水的三态\n水在生活中有固态、液态和气态三种状态。冰是固态的水，杯子里的水是液态的水，水蒸气是气态的水。\n\n'
            '熔化与凝固\n冰吸收热量后可以熔化成水。水失去热量后可以凝固成冰。在标准大气压下，纯水的凝固点约为零摄氏度。\n\n'
            '蒸发\n液态的水从表面变成水蒸气的现象叫作蒸发。湿衣服晾干就是水分蒸发的例子。温度、空气流动和水的表面积都会影响蒸发快慢。\n\n'
            '凝结\n水蒸气遇冷变成液态小水滴的现象叫作凝结。冷饮杯外壁的小水珠来自空气中的水蒸气凝结，并不是杯里的水穿过了杯壁。\n\n'
            '观察与思考\n把冰放在杯子里观察它逐渐熔化，再观察杯壁上的水珠。比较熔化与凝结：熔化是固态变液态，凝结是气态变液态。')])
        approve(doc['id'])
        course = course_create(CourseInput(teacher_id=teacher['id'], title='一滴水的奇妙旅行', document_ids=[doc['id']]))
        publish(course['id'])
        return teacher

    if (ROOT / 'dist').exists():
        app.mount('/', StaticFiles(directory=ROOT / 'dist', html=True), name='web')
    return app


app = create_app()
