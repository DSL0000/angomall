import argparse,getpass
from app import db,password
p=argparse.ArgumentParser(description='通过服务器终端创建受信任的商家或管理员账号')
p.add_argument('email');p.add_argument('--role',choices=['merchant','admin'],required=True);p.add_argument('--shop',type=int);p.add_argument('--name',default='AngoMall 管理员');a=p.parse_args()
if a.role=='merchant' and a.shop is None:p.error('商家必须指定 --shop')
s=getpass.getpass('密码（至少10位）: ')
if len(s)<10:p.error('密码太短')
with db() as c:c.execute('INSERT INTO users(name,email,password,role,shop) VALUES(?,?,?,?,?)',(a.name,a.email.lower(),password(s),a.role,a.shop))
print('账号已创建')
