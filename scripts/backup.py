"""Run with the studio stopped to keep database and filesystem assets consistent."""
import os
import sys
import sqlite3
import tarfile
import tempfile
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

root=Path(__file__).resolve().parents[1]
load_dotenv(root/'.env')
data=Path(os.getenv('DATA_DIR',str(root/'data'))).resolve()
destination=Path(sys.argv[1] if len(sys.argv)>1 else root/'backups').resolve()
destination.mkdir(parents=True,exist_ok=True)
if not (data/'studio.sqlite3').exists():
    raise SystemExit('未找到数据库。请在项目根目录运行，并检查 DATA_DIR。')
output=destination/('teacher-studio-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.tar.gz')
with tempfile.TemporaryDirectory() as tmp:
    snapshot=Path(tmp)/'studio.sqlite3'
    with sqlite3.connect(data/'studio.sqlite3') as src,sqlite3.connect(snapshot) as dst:
        src.backup(dst)
    with tarfile.open(output,'w:gz') as archive:
        archive.add(snapshot,arcname='studio.sqlite3')
        if (data/'assets').exists():archive.add(data/'assets',arcname='assets')
print('备份完成：',output)
