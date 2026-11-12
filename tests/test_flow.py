import os,tempfile,sys,unittest
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
folder=tempfile.TemporaryDirectory();os.environ['ANGOMALL_DB']=folder.name+'/test.sqlite3'
from fastapi.testclient import TestClient
from app import app,db,password
class Flow(unittest.TestCase):
 def test_closed_loop(self):
  buyer=TestClient(app);other=TestClient(app);staff=TestClient(app)
  self.assertEqual(buyer.get('/api/health').json()['status'],'ok')
  self.assertTrue(buyer.get('/api/shops').json())
  self.assertTrue(all(p['shop']==1 for p in buyer.get('/api/products?shop=1').json()))
  for client,email in [(buyer,'buyer@test.com'),(other,'other@test.com')]:
   self.assertEqual(client.post('/api/register',json={'email':email,'password':'StrongPass123!','role':'admin'}).status_code,200)
   self.assertEqual(client.post('/api/login',json={'email':email,'password':'StrongPass123!'}).status_code,200)
  self.assertEqual(buyer.get('/api/me').json()['role'],'buyer')
  self.assertEqual(other.get('/api/admin/audit').status_code,403)
  with db() as c:c.execute('INSERT INTO users(name,email,password,role,shop) VALUES(?,?,?,?,?)',('merchant','staff@test.com',password('StrongPass123!'),'merchant',1))
  staff.post('/api/login',json={'email':'staff@test.com','password':'StrongPass123!'})
  p=next(p for p in buyer.get('/api/products').json() if p['shop']==1 and p['origin']=='local' and p['stock']>0)
  self.assertEqual(other.patch('/api/products/'+p['id'],json={'price':1,'stock':999}).status_code,403)
  self.assertEqual(buyer.put('/api/cart',json={'product':p['id'],'qty':100}).status_code,422)
  buyer.put('/api/cart',json={'product':p['id'],'qty':1})
  body={'address':'Belas pickup +244 900000000','request_key':'test-request-001'}
  order=buyer.post('/api/orders',json=body);self.assertEqual(order.status_code,200,order.text);oid=order.json()['ids'][0]
  self.assertEqual(buyer.post('/api/orders',json=body).json(),order.json())
  self.assertEqual(other.get('/api/orders').json(),[])
  url='/api/orders/'+oid+'/transition'
  self.assertEqual(other.post(url,json={'action':'cancel'}).status_code,403)
  self.assertEqual(buyer.post(url,json={'action':'confirm'}).status_code,403)
  self.assertEqual(staff.post(url,json={'action':'confirm'}).status_code,200)
  self.assertNotIn('code',staff.get('/api/orders').json()[0])
  self.assertEqual(staff.post(url,json={'action':'complete','code':'bad'}).status_code,400)
  code=buyer.get('/api/orders').json()[0]['code']
  self.assertEqual(staff.post(url,json={'action':'complete','code':code}).status_code,200)
  self.assertEqual(buyer.post(url,json={'action':'return'}).status_code,200)
  self.assertEqual(staff.post(url,json={'action':'refund'}).status_code,200)
  self.assertEqual(staff.post(url,json={'action':'refund'}).status_code,403)
  after=next(x for x in buyer.get('/api/products').json() if x['id']==p['id'])
  self.assertEqual(after['stock'],p['stock'])
  self.assertEqual(buyer.post('/api/logout',headers={'origin':'https://evil.test'}).status_code,403)
  buyer.post('/api/logout');self.assertEqual(buyer.get('/api/me').status_code,401)

class StockRace(unittest.TestCase):
 def test_last_unit_is_not_oversold(self):
  from concurrent.futures import ThreadPoolExecutor
  clients=[TestClient(app),TestClient(app)]
  with db() as c:
   p=c.execute('SELECT id FROM products WHERE shop=1 LIMIT 1').fetchone()['id']
   c.execute('UPDATE products SET stock=1 WHERE id=?',(p,))
  for n,client in enumerate(clients):
   body={'email':f'race{n}@test.com','password':'StrongPass123!'}
   client.post('/api/register',json=body);client.post('/api/login',json=body)
   self.assertEqual(client.put('/api/cart',json={'product':p,'qty':1}).status_code,200)
  def submit(client):return client.post('/api/orders',json={'address':'Belas store pickup','request_key':'concurrent-request-01'}).status_code
  with ThreadPoolExecutor(2) as pool:results=list(pool.map(submit,clients))
  self.assertEqual(sorted(results),[200,409])
  with db() as c:self.assertEqual(c.execute('SELECT stock FROM products WHERE id=?',(p,)).fetchone()[0],0)

if __name__=='__main__':unittest.main()
