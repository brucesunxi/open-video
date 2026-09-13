"""Configure the shared login account on the server; never logs the password."""
import argparse
import getpass
import os
from pathlib import Path
import secrets
import sys
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from server.auth import password_hash
p=argparse.ArgumentParser();p.add_argument('--username',default='admin');p.add_argument('--generate',action='store_true');a=p.parse_args()
if not a.username or len(a.username)>80:raise SystemExit('用户名长度需为 1–80 字符')
password=secrets.token_urlsafe(15) if a.generate else getpass.getpass('新密码（至少 12 位）: ')
if len(password)<12 or len(password)>256:raise SystemExit('密码长度需为 12–256 位')
if not a.generate and password!=getpass.getpass('再次输入: '):raise SystemExit('两次密码不一致')
path=root/'.env';s=path.read_text() if path.exists() else ''
changes={'APP_USERNAME':a.username,'APP_PASSWORD_HASH':password_hash(password),'APP_TOKEN':secrets.token_urlsafe(32),'APP_COOKIE_SECURE':'1'}
lines=[x for x in s.splitlines() if x.split('=',1)[0] not in changes];lines.extend(k+'='+v for k,v in changes.items());path.write_text('\n'.join(lines)+'\n');path.chmod(0o600)
if a.generate:
 f=root.parent/'login-initial.txt';fd=os.open(f,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
 with os.fdopen(fd,'w') as out:out.write('用户名: '+a.username+'\n密码: '+password+'\n')
 print('初始登录信息保存在服务器:',f)
print('账号已设置；重启业务服务后生效。')
