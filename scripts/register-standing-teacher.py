"""Register the selected standing portrait and prepare its published courses locally on the server."""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

app = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(app))
load_dotenv(app / '.env')
from server.auth import COOKIE, make_session


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--teacher', default='teacher_e3b3015cdcfd4b72')
    parser.add_argument('--activate', action='store_true', help='Select only after all courses are ready')
    args = parser.parse_args()
    raw = args.image.read_bytes()
    name = '站姿讲课·和马老师一起学数学-' + hashlib.sha256(raw).hexdigest()[:12] + '.png'
    with httpx.Client(base_url='http://127.0.0.1:8010', timeout=240, trust_env=False) as client:
        def request(method, path, **kwargs):
            client.cookies.set(COOKIE, make_session())
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()

        teacher = next(t for t in request('GET', '/api/teachers') if t['id'] == args.teacher)
        if not teacher.get('consent') or not teacher.get('voice_profile_id'):
            raise SystemExit('请先确认老师授权和音色。')
        assets_url = '/api/teachers/' + args.teacher + '/assets'
        asset = next((a for a in request('GET', assets_url) if a['filename'] == name), None)
        if asset is None:
            asset = request('POST', assets_url, data={'kind': 'image'}, files={'file': (name, raw, 'image/png')})
        courses = [c for c in request('GET', '/api/teachers/' + args.teacher + '/courses') if c['teacher_id'] == args.teacher and c['status'] == 'published']
        if not courses:
            raise SystemExit('形象已注册，未发现已发布课程，未切换默认形象。')
        # Use exactly the same segmentation as the classroom player.
        node = """import fs from 'node:fs';import {speechChunks} from './deploy/speech-chunks.mjs';
process.stdout.write(JSON.stringify(JSON.parse(fs.readFileSync(0,'utf8')).map(t=>speechChunks(t,true))));"""
        for course in courses:
            course = request('GET', '/api/courses/' + course['id'])
            chunks = json.loads(subprocess.check_output(['node', '--input-type=module', '-e', node], cwd=app,
                input=json.dumps([s['narration'] for s in course['slides']]).encode()))
            plan = {'avatar_asset_id': asset['id'], 'chunks': chunks}
            path = '/api/courses/' + course['id']
            job = request('POST', path + '/prepare-media', json=plan)
            deadline = time.monotonic() + 6 * 3600
            previous = None
            while job['status'] in ('queued', 'preparing'):
                progress = (job['status'], job['completed'])
                if progress != previous:
                    print(course['title'], job['completed'], '/', job['total'], flush=True)
                    previous = progress
                if time.monotonic() > deadline:
                    raise SystemExit('等待超时；任务仍可能继续，未切换默认形象。')
                time.sleep(5)
                job = request('GET', '/api/media-jobs/' + job['id'])
            if job['status'] != 'ready':
                raise SystemExit('课程准备未完成，未切换默认形象：' + job.get('message', job['status']))
        if args.activate:
            latest = next(t for t in request('GET', '/api/teachers') if t['id'] == args.teacher)
            if any(latest.get(k) != teacher.get(k) for k in ('voice_profile_id', 'avatar_asset_id', 'consent')):
                raise SystemExit('准备期间老师配置改变，保留当前选择，请在后台手动切换。')
            request('PUT', '/api/teachers/' + args.teacher, json={**latest, 'avatar_asset_id': asset['id']})
        print('站姿课程已准备完成，后台可选择：', name)


if __name__ == '__main__':
    main()
