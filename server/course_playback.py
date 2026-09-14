"""Fast-start lesson videos assembled from existing clips without video re-encoding."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def playback_signature(course, teacher, image_hash):
    identity = [1, course['id'], [s['narration'] for s in course['slides']],
                teacher['voice_profile_id'], teacher['avatar_asset_id'], image_hash,
                os.getenv('MEDIA_CACHE_VERSION', 'reference-skin-v1'),
                os.getenv('TTS_BASE_URL'), os.getenv('AVATAR_BASE_URL')]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


def read_page(root, signature, index):
    folder = Path(root) / 'course-playback' / signature
    try:
        info = json.loads((folder / f'{index}.json').read_text())
        video = folder / f'{index}.mp4'
        if video.stat().st_size != info['size'] or not info['size']:
            return None
        return info
    except (OSError, ValueError, KeyError):
        return None


def join_page(root, signature, index, clips):
    folder = Path(root) / 'course-playback' / signature
    folder.mkdir(parents=True, exist_ok=True)
    existing = read_page(root, signature, index)
    if existing:
        return existing
    executable = os.getenv('FFMPEG_BIN') or shutil.which('ffmpeg')
    if not executable:
        raise ValueError('请配置 FFMPEG_BIN，才能合并课程视频。')
    segments = []
    elapsed = offset = 0
    with tempfile.TemporaryDirectory(dir=folder) as temp:
        work = Path(temp)
        for i, (text, data) in enumerate(clips):
            path = work / f'{i}.mp4'
            path.write_bytes(data)
            probe = subprocess.run([executable, '-hide_banner', '-i', str(path)], capture_output=True, text=True, timeout=30)
            match = re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)', probe.stderr)
            if not match:
                raise ValueError('无法读取课程视频时长。')
            h, m, s = map(float, match.groups())
            duration = h*3600 + m*60 + s
            segments.append({'start': elapsed, 'duration': duration, 'offset': offset, 'length': len(text)})
            elapsed += duration
            offset += len(text)
        (work / 'list.txt').write_text(''.join(f"file '{i}.mp4'\n" for i in range(len(clips))))
        subprocess.run([executable, '-v', 'error', '-f', 'concat', '-safe', '1', '-i', str(work/'list.txt'),
                        '-c', 'copy', '-movflags', '+faststart', str(work/'page.mp4')],
                       check=True, capture_output=True, timeout=120)
        destination = folder / f'{index}.mp4'
        os.replace(work/'page.mp4', destination)
        info = {'size': destination.stat().st_size, 'duration': elapsed, 'segments': segments}
        (work/'page.json').write_text(json.dumps(info))
        os.replace(work/'page.json', folder/f'{index}.json')
        return info
