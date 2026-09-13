"""Publish the reviewed grade-five demo through the app API on the demo host.

Preserves selected teacher media and existing courses. Re-running reuses the
same published lesson. Credentials come only from the server environment.
"""
import json
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

app = Path(__file__).resolve().parents[1]
load_dotenv(app / '.env')
sys.path.insert(0, str(app))
from server.auth import COOKIE, make_session

lesson = json.loads((app / 'lessons/grade5-fraction-addition.json').read_text())
with httpx.Client(base_url='http://127.0.0.1:8010', trust_env=False,
                  cookies={COOKIE: make_session()}, timeout=60) as client:
    def request(method, path, **kwargs):
        response = client.request(method, '/api' + path, **kwargs)
        response.raise_for_status()
        return response.json()

    teachers = request('GET', '/teachers')
    matches = [t for t in teachers if t['name'].startswith('数学老师')]
    if len(matches) != 1:
        raise SystemExit('Expected one math teacher; no changes made.')
    teacher = matches[0]
    tid = teacher['id']
    profile = {key: teacher[key] for key in
               ('name', 'subject', 'bio', 'style', 'voice_profile_id', 'avatar_asset_id', 'consent')}
    profile.update(subject=lesson['subject'], style=lesson['style'])
    request('PUT', f'/teachers/{tid}', json=profile)
    courses = request('GET', f'/teachers/{tid}/courses')
    existing = next((c for c in courses if c['title'] == lesson['title'] and c['status'] == 'published'), None)
    if existing:
        print(json.dumps({'course_id': existing['id'], 'status': 'already published'}, ensure_ascii=False))
        raise SystemExit(0)
    # Each slide becomes a separate document so its citations remain precise.
    documents = request('GET', f'/teachers/{tid}/documents')
    ids = []
    for index, slide in enumerate(lesson['slides'], 1):
        title = f"{lesson['document_title']} · {index:02d} {slide['title']}"
        text = slide['title'] + '\n' + '\n'.join(slide['bullets']) + '\n' + slide['narration']
        doc = next((d for d in documents if d['title'] == title), None)
        if doc is None:
            doc = request('POST', '/documents', json={'teacher_id': tid, 'title': title, 'text': text})
        request('POST', f"/documents/{doc['id']}/approve")
        ids.append(doc['id'])
    course = request('POST', '/courses', json={'teacher_id': tid, 'title': lesson['title'], 'document_ids': ids})
    slides = []
    for index, slide in enumerate(lesson['slides']):
        source_ids = [s['id'] for s in course['sources'] if s['document_id'] == ids[index]]
        assert source_ids
        slides.append(dict(slide, id=f'math_fraction_{index+1}', source_ids=source_ids))
    request('PUT', f"/courses/{course['id']}", json={'title': lesson['title'], 'slides': slides})
    published = request('POST', f"/courses/{course['id']}/publish")
    current = next(t for t in request('GET', '/teachers') if t['id'] == tid)
    assert current['avatar_asset_id'] == teacher['avatar_asset_id']
    assert current['voice_profile_id'] == teacher['voice_profile_id']
    assert published['slides'] == slides
    print(json.dumps({'teacher': tid, 'course_id': course['id'], 'title': published['title'],
                      'pages': len(slides), 'status': published['status'], 'media_preserved': True}, ensure_ascii=False))
