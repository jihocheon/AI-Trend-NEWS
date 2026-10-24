import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from chat_support import ScriptedGenerator,knowledge
from radar.chat import ChatService
from radar.chat_web import create_app


class WebTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();path=Path(self.tmp.name)/'knowledge.db'
        store=knowledge(path);store.close();self.generator=ScriptedGenerator()
        self.service=ChatService(path,generator_factory=lambda store:self.generator,min_interval=0)
        self.client=TestClient(create_app(self.service),base_url='http://localhost')
    def tearDown(self):self.client.close();self.tmp.cleanup()
    def test_interface_assets_and_security_headers(self):
        response=self.client.get('/')
        self.assertEqual(response.status_code,200);self.assertIn('lang="ko"',response.text)
        self.assertIn("frame-ancestors 'none'",response.headers['content-security-policy'])
        js=self.client.get('/static/chat.js');self.assertEqual(js.status_code,200)
        self.assertNotIn('innerHTML',js.text);self.assertNotIn('GEMINI_API_KEY',js.text)
        self.assertEqual(self.client.get('/static/chat.css').status_code,200)
    def test_chat_followup_clear_and_health(self):
        first=self.client.post('/api/chat',json={'message':'RAG와 MCP 비교'})
        self.assertEqual(first.status_code,200);sid=first.json()['conversation_id']
        second=self.client.post('/api/chat',json={'message':'그럼 둘을 어떻게 연결해?','conversation_id':sid})
        self.assertEqual(second.status_code,200);self.assertEqual(len(self.generator.calls),2)
        self.assertEqual(self.client.delete('/api/conversations/'+sid).status_code,200)
        self.assertNotIn(sid,self.service.sessions)
        with patch.dict('os.environ',{},clear=True):
            self.assertFalse(self.client.get('/api/health').json()['generation_configured'])
    def test_origin_host_and_input_validation(self):
        self.assertEqual(self.client.post('/api/chat',json={'message':'RAG'},headers={'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(self.client.get('/',headers={'Host':'evil.example'}).status_code,400)
        response=self.client.post('/api/chat',json={'message':'x'*1001,'api_key':'not-allowed'})
        self.assertEqual(response.status_code,422);self.assertNotIn('not-allowed',response.text)
        self.assertEqual(self.generator.calls,[])
    def test_invalid_model_output_is_safe_error(self):
        self.generator.generate=lambda body:{'private':'provider error secret'}
        response=self.client.post('/api/chat',json={'message':'RAG 설명'})
        self.assertEqual(response.status_code,502);self.assertNotIn('provider error',response.text)
