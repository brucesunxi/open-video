"""Single-process local launcher serving the built web app and API."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
import uvicorn

host = os.getenv('APP_HOST', '127.0.0.1')
port = int(os.getenv('APP_PORT', '8010'))
if host not in ('127.0.0.1', 'localhost', '::1') and len(os.getenv('APP_TOKEN', '')) < 24:
    raise SystemExit('外网监听必须设置至少 24 位 APP_TOKEN。请配置 .env 后再启动。')
if not (ROOT / 'dist/index.html').exists():
    raise SystemExit('请先执行 npm ci 和 npm run build。')
print(f'知课工作台：http://{host}:{port}', flush=True)
uvicorn.run('server.app:app', host=host, port=port, access_log=True)
