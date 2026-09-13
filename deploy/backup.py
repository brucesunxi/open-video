"""Create a consistent local recovery archive on the GPU host (contains secrets)."""
import os
import sqlite3
import tarfile
from pathlib import Path
root=Path(os.environ.get('TEACHER_DEPLOY_ROOT','/workspace/teacher-deploy'))
backup=root/'backups';backup.mkdir(mode=0o700,exist_ok=True)
db=root/'data/studio.sqlite3';snapshot=backup/'studio-snapshot.sqlite3'
with sqlite3.connect(db) as source,sqlite3.connect(snapshot) as dest:
    source.backup(dest)
    if dest.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise SystemExit('SQLite backup failed')
path=backup/'deployment-latest.tar.gz'
with tarfile.open(path,'w:gz') as tar:
    for p in (root/'data').rglob('*'):
        if p.is_file() and p.name not in ('studio.sqlite3','studio.sqlite3-wal','studio.sqlite3-shm'):
            tar.add(p,arcname=str(p.relative_to(root)))
    tar.add(snapshot,arcname='data/studio.sqlite3')
    for name in ('model-manifest.json','asr-installed.json','tts-installed.json','asr-extra-lock.txt','tts-extra-lock.txt','teacher-studio/.env','teacher-studio/deploy/services.py'):
        tar.add(root/name,arcname=name)
path.chmod(0o600)
print('Backup verified:',path,'bytes:',path.stat().st_size)
