import hashlib,unittest
from pathlib import Path
from fastapi.testclient import TestClient
from app import app

class OriginalPage(unittest.TestCase):
 def test_home_is_exact_uploaded_document(self):
  root=Path(__file__).resolve().parents[1]
  expected='4bd6d520497305827bf6704e98aee74d887fd91618a7ca7eca1deb52fe0db4de'
  data=(root/'static/index.html').read_bytes()
  self.assertEqual(hashlib.sha256(data).hexdigest(),expected)
  self.assertEqual(data,(root/'static/original.html').read_bytes())
  response=TestClient(app).get('/')
  self.assertEqual(response.status_code,200)
  self.assertEqual(response.content,data)
  self.assertTrue(response.headers['content-type'].startswith('text/html'))
