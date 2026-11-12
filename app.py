import os,json,sqlite3,secrets,hashlib,hmac,time
from pathlib import Path
from contextlib import contextmanager
from fastapi import FastAPI,Request,HTTPException,Depends
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field

ROOT=Path(__file__).parent
DB=os.getenv('ANGOMALL_DB',str(ROOT/'data.sqlite3'))
app=FastAPI(title='AngoMall API',version='1.0.0')
@contextmanager
def db():
 c=sqlite3.connect(DB,timeout=20); c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON')
 try:
  yield c;c.commit()
 except: c.rollback();raise
 finally:c.close()
def fail(msg,code=400):raise HTTPException(code,msg)
def password(value,salt=None):
 salt=salt or secrets.token_hex(16)
 return salt+':'+hashlib.scrypt(value.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
def init():
 with db() as c:
  c.executescript('''
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT,email TEXT UNIQUE,password TEXT,role TEXT DEFAULT 'buyer',shop INTEGER);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user INTEGER REFERENCES users(id),expires INTEGER);
CREATE TABLE IF NOT EXISTS products(id TEXT PRIMARY KEY,name TEXT,category TEXT,shop INTEGER,origin TEXT,image TEXT,price INTEGER CHECK(price>0),stock INTEGER CHECK(stock>=0),active INTEGER DEFAULT 1,note TEXT);
CREATE TABLE IF NOT EXISTS cart(user INTEGER REFERENCES users(id),product TEXT REFERENCES products(id),qty INTEGER CHECK(qty BETWEEN 1 AND 99),PRIMARY KEY(user,product));
CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,user INTEGER REFERENCES users(id),shop INTEGER,total INTEGER,status TEXT,fulfillment TEXT,address TEXT,code TEXT,created INTEGER,request_key TEXT,UNIQUE(user,request_key));
CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY,order_id TEXT REFERENCES orders(id),product TEXT REFERENCES products(id),name TEXT,qty INTEGER,price INTEGER);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,user INTEGER,action TEXT,detail TEXT,created INTEGER);
''')
  if not c.execute('SELECT 1 FROM products LIMIT 1').fetchone():
   for p in json.loads((ROOT/'seed.json').read_text()):
    stock=p.get('stock'); stock=sum(stock.values()) if isinstance(stock,dict) else 100
    c.execute('INSERT INTO products VALUES(?,?,?,?,?,?,?,?,?,?)',(p['id'],p['n'],p['cat'],p['shop'],p['origin'],p.get('image',''),max(1,round(p.get('kz') or p.get('price') or p.get('usd',10)*920)),stock,1,p.get('note','')))
def record(c,u,action,detail):c.execute('INSERT INTO audit(user,action,detail,created) VALUES(?,?,?,?)',(u['id'],action,detail,int(time.time())))
def current(request:Request):
 token=request.cookies.get('session','')
 with db() as c:
  row=c.execute('SELECT u.* FROM users u JOIN sessions s ON u.id=s.user WHERE s.token=? AND s.expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
 if not row:fail('请先登录',401)
 return dict(row)
@app.middleware('http')
async def security(request,call_next):
 if request.method in ('POST','PUT','PATCH','DELETE'):
  origin=request.headers.get('origin')
  if origin and origin.rstrip('/')!=str(request.base_url).rstrip('/'):return __import__('starlette.responses',fromlist=['JSONResponse']).JSONResponse({'detail':'请求来源不允许'},403)
 response=await call_next(request)
 response.headers['X-Content-Type-Options']='nosniff';response.headers['X-Frame-Options']='DENY';response.headers['Referrer-Policy']='same-origin'
 if request.url.path.startswith('/api'):response.headers['Cache-Control']='no-store'
 return response
class Credentials(BaseModel):
 email:str=Field(min_length=5,max_length=180)
 password:str=Field(min_length=10,max_length=128)
 name:str=Field(default='AngoMall 用户',min_length=1,max_length=80)
@app.post('/api/register')
def register(data:Credentials):
 email=data.email.lower().strip()
 if '@' not in email:fail('邮箱格式不正确')
 with db() as c:
  try:c.execute('INSERT INTO users(name,email,password) VALUES(?,?,?)',(data.name,email,password(data.password)))
  except sqlite3.IntegrityError:fail('该邮箱已注册',409)
 return {'ok':True}
ATTEMPTS={}
@app.post('/api/login')
def login(data:Credentials,request:Request):
 from fastapi.responses import JSONResponse
 key=(request.client.host,data.email.lower()); attempts=[t for t in ATTEMPTS.get(key,[]) if t>time.time()-300]
 if len(attempts)>=10:fail('尝试次数过多，请五分钟后重试',429)
 ATTEMPTS[key]=attempts+[time.time()]
 with db() as c:
  u=c.execute('SELECT * FROM users WHERE email=?',(data.email.lower().strip(),)).fetchone()
  if not u or not hmac.compare_digest(password(data.password,u['password'].split(':')[0]),u['password']):fail('邮箱或密码不正确',401)
  token=secrets.token_urlsafe(32);c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),u['id'],int(time.time())+86400))
 ATTEMPTS.pop(key,None)
 r=JSONResponse({'ok':True});r.set_cookie('session',token,httponly=True,samesite='lax',secure=os.getenv('COOKIE_SECURE')=='1',max_age=86400);return r
@app.post('/api/logout')
def logout(request:Request):
 from fastapi.responses import JSONResponse
 with db() as c:c.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(request.cookies.get('session','').encode()).hexdigest(),))
 r=JSONResponse({'ok':True});r.delete_cookie('session');return r
@app.get('/api/me')
def me(u=Depends(current)):return {k:u[k] for k in ('id','name','email','role','shop')}
@app.get('/api/shops')
def shops():return json.loads((ROOT/'shops.json').read_text())
@app.get('/api/products')
def products(q:str='',category:str='',origin:str='',shop:int=0):
 with db() as c:return [dict(r) for r in c.execute('SELECT * FROM products WHERE active=1 AND name LIKE ? AND (?="" OR category=?) AND (?="" OR origin=?) AND (?=0 OR shop=?)',('%'+q[:100]+'%',category,category,origin,origin,shop,shop))]
class CartItem(BaseModel):
 product:str
 qty:int=Field(ge=0,le=99)
@app.get('/api/cart')
def cart(u=Depends(current)):
 with db() as c:return [dict(r) for r in c.execute('SELECT p.*,c.qty FROM cart c JOIN products p ON c.product=p.id WHERE c.user=?',(u['id'],))]
@app.put('/api/cart')
def set_cart(data:CartItem,u=Depends(current)):
 with db() as c:
  p=c.execute('SELECT * FROM products WHERE id=? AND active=1',(data.product,)).fetchone()
  if not p:fail('商品不存在',404)
  if data.qty>p['stock']:fail('库存不足',409)
  if data.qty:c.execute('INSERT INTO cart VALUES(?,?,?) ON CONFLICT(user,product) DO UPDATE SET qty=excluded.qty',(u['id'],data.product,data.qty))
  else:c.execute('DELETE FROM cart WHERE user=? AND product=?',(u['id'],data.product))
 return {'ok':True}
class Checkout(BaseModel):
 fulfillment:str='pickup'
 address:str=Field(min_length=3,max_length=300)
 request_key:str=Field(min_length=10,max_length=100)
@app.post('/api/orders')
def checkout(data:Checkout,u=Depends(current)):
 if data.fulfillment not in ('pickup','delivery'):fail('配送方式无效')
 with db() as c:
  c.execute('BEGIN IMMEDIATE')
  old=c.execute('SELECT id FROM orders WHERE user=? AND request_key=?',(u['id'],data.request_key)).fetchall()
  if old:return {'ids':[r['id'] for r in old]}
  rows=c.execute('SELECT p.*,cart.qty FROM cart JOIN products p ON cart.product=p.id WHERE cart.user=?',(u['id'],)).fetchall()
  if not rows:fail('购物车为空')
  # One merchant per checkout keeps fulfillment and idempotency unambiguous.
  if len({p['shop'] for p in rows})>1:fail('请按店铺分别结算，每次只保留同一店铺的商品')
  for p in rows:
   if not p['active'] or p['stock']<p['qty']:fail('商品库存或状态已变化，请刷新购物车',409)
  oid='AM-'+secrets.token_hex(6).upper();status='quoted' if any(p['origin']!='local' for p in rows) else 'pending'
  c.execute('INSERT INTO orders VALUES(?,?,?,?,?,?,?,?,?,?)',(oid,u['id'],rows[0]['shop'],sum(p['price']*p['qty'] for p in rows),status,data.fulfillment,data.address,str(secrets.randbelow(900000)+100000),int(time.time()),data.request_key))
  for p in rows:
   c.execute('UPDATE products SET stock=stock-? WHERE id=?',(p['qty'],p['id']))
   c.execute('INSERT INTO items(order_id,product,name,qty,price) VALUES(?,?,?,?,?)',(oid,p['id'],p['name'],p['qty'],p['price']))
  c.execute('DELETE FROM cart WHERE user=?',(u['id'],));record(c,u,'order.create',oid)
 return {'ids':[oid]}
@app.get('/api/orders')
def orders(u=Depends(current)):
 with db() as c:
  query='SELECT * FROM orders';args=[]
  if u['role']=='buyer':query+=' WHERE user=?';args=[u['id']]
  elif u['role']=='merchant':query+=' WHERE shop=?';args=[u['shop']]
  rows=[dict(r) for r in c.execute(query+' ORDER BY created DESC',args)]
  for r in rows:
   r['items']=[dict(i) for i in c.execute('SELECT * FROM items WHERE order_id=?',(r['id'],))]
   if u['role']!='buyer' and r['user']!=u['id']:r.pop('code',None)
  return rows
class Transition(BaseModel):
 action:str
 code:str=''
@app.post('/api/orders/{oid}/transition')
def transition(oid:str,data:Transition,u=Depends(current)):
 with db() as c:
  c.execute('BEGIN IMMEDIATE');o=c.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
  if not o:fail('订单不存在',404)
  staff=u['role']=='admin' or (u['role']=='merchant' and u['shop']==o['shop'])
  owner=u['id']==o['user'];a=data.action;s=o['status'];target=None
  if a=='cancel' and (owner or staff) and s in ('pending','quoted','confirmed'):target='cancelled'
  elif a=='confirm' and staff and s in ('pending','quoted'):target='confirmed'
  elif a=='complete' and staff and s=='confirmed':
   if not hmac.compare_digest(o['code'],data.code):fail('核验码错误')
   target='completed'
  elif a=='return' and owner and s=='completed':target='return_requested'
  elif a=='refund' and staff and s=='return_requested':target='refunded'
  if not target:fail('无权限或订单状态不允许此操作',403)
  if target in ('cancelled','refunded'):
   for i in c.execute('SELECT * FROM items WHERE order_id=?',(oid,)).fetchall():c.execute('UPDATE products SET stock=stock+? WHERE id=?',(i['qty'],i['product']))
  c.execute('UPDATE orders SET status=? WHERE id=?',(target,oid));record(c,u,'order.'+a,oid)
 return {'ok':True,'status':target}
class ProductEdit(BaseModel):
 price:int=Field(gt=0,le=1000000000)
 stock:int=Field(ge=0,le=1000000)
 active:bool=True
@app.patch('/api/products/{pid}')
def edit(pid:str,data:ProductEdit,u=Depends(current)):
 with db() as c:
  p=c.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone()
  if not p:fail('商品不存在',404)
  if u['role']!='admin' and not(u['role']=='merchant' and u['shop']==p['shop']):fail('无权限',403)
  c.execute('UPDATE products SET price=?,stock=?,active=? WHERE id=?',(data.price,data.stock,int(data.active),pid));record(c,u,'product.update',pid)
 return {'ok':True}
@app.get('/api/admin/audit')
def audit(u=Depends(current)):
 if u['role']!='admin':fail('无权限',403)
 with db() as c:return [dict(r) for r in c.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 100')]
@app.get('/api/health')
def health():
 with db() as c:c.execute('SELECT 1')
 return {'status':'ok'}
init()
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
@app.get('/')
def index():return FileResponse(ROOT/'static/index.html')
