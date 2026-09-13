"""Persistent media cache. Atomic files; single producer per process."""
import asyncio
import hashlib
import json
import os
from pathlib import Path


class MediaCache:
    def __init__(self, root):
        self.root = Path(root) / 'speech-cache'
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = asyncio.Lock()

    async def get(self, identity, produce):
        key = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        path = self.root / (key + '.json')
        def read():
            if not path.exists():
                return None
            try:
                info = json.loads(path.read_text())
                data = (self.root / (key + '.bin')).read_bytes()
                if data and hashlib.sha256(data).hexdigest() == info['sha256']:
                    return data, info['mime']
            except (OSError, ValueError, KeyError):
                pass
        cached = read()
        if cached:
            return *cached, True
        async with self.lock:
            cached = read()
            if cached:
                return *cached, True
            data, mime = await produce()
            if not data or not mime.startswith(('audio/', 'video/')):
                raise ValueError('生成的媒体为空或格式无效。')
            binary = self.root / (key + '.bin')
            temp = binary.with_suffix('.tmp')
            temp.write_bytes(data)
            os.replace(temp, binary)
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps({'mime': mime, 'sha256': hashlib.sha256(data).hexdigest()}))
            os.replace(temp, path)
            return data, mime, False
