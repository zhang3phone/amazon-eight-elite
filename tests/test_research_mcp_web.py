import io
import tempfile
import tomllib
import unittest
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode
from unittest.mock import patch
from aee.research_mcp_web import KeyHandler,serve

class ResearchWebTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.config=Path(self.tmp.name)/'config.toml'
    def handler(self,form=None,origin='http://127.0.0.1:12345',host='127.0.0.1:12345',provider='both'):
        h=KeyHandler.__new__(KeyHandler);h.server=SimpleNamespace(server_port=12345,csrf='synthetic-csrf',provider=provider,providers=['sellersprite','sif'] if provider=='both' else [provider],config=self.config,saved=False,result=None,deadline=float('inf'))
        h.path='/save';h.headers=Message();h.headers['Host']=host;h.headers['Origin']=origin;h.headers['Content-Type']='application/x-www-form-urlencoded'
        data=urlencode(form or {'csrf':'synthetic-csrf','sellersprite':'synthetic-one','sif':'synthetic-two'}).encode();h.headers['Content-Length']=str(len(data));h.rfile=io.BytesIO(data);h.output=[];h.page=lambda body,status=200:h.output.append((status,body));return h
    def test_preview_does_not_listen_or_create(self):
        with patch('aee.research_mcp_web.LocalKeyServer',side_effect=AssertionError('must not bind')):
            result=serve('both',self.config)
        self.assertEqual(result['status'],'planned');self.assertFalse(self.config.exists())
    def test_valid_submit_saves_only_config_and_redacted_receipt(self):
        h=self.handler();h.do_POST();self.assertTrue(h.server.saved)
        data=tomllib.loads(self.config.read_text());self.assertEqual(data['mcp_servers']['aee_sif']['http_headers']['secret-key'],'synthetic-two')
        self.assertNotIn('synthetic-one',str(h.output)+str(h.server.result));self.assertNotIn('synthetic-two',str(h.output)+str(h.server.result))
        self.assertEqual(list(self.config.parent.iterdir()),[self.config])
    def test_cross_origin_rejected_before_reading_body(self):
        h=self.handler(origin='https://external.invalid');h.do_POST();self.assertEqual(h.output[0][0],403);self.assertEqual(h.rfile.tell(),0);self.assertFalse(self.config.exists())
    def test_dns_rebinding_host_rejected(self):
        h=self.handler(host='external.invalid:12345');h.do_POST();self.assertEqual(h.output[0][0],403);self.assertFalse(self.config.exists())
    def test_csrf_rejected(self):
        h=self.handler(form={'csrf':'wrong','sellersprite':'synthetic-one','sif':'synthetic-two'});h.do_POST();self.assertEqual(h.output[0][0],403);self.assertFalse(self.config.exists())
    def test_duplicate_fields_rejected_without_echo(self):
        h=self.handler(form=[('csrf','synthetic-csrf'),('sellersprite','private-value'),('sellersprite','private-value'),('sif','synthetic-two')]);h.do_POST();self.assertFalse(self.config.exists());self.assertNotIn('private-value',str(h.output))
    def test_bad_key_does_not_echo_or_write(self):
        h=self.handler(form={'csrf':'synthetic-csrf','sellersprite':'private value','sif':'synthetic-two'});h.do_POST();self.assertFalse(self.config.exists());self.assertNotIn('private value',str(h.output))
    def test_single_provider_supported(self):
        h=self.handler(form={'csrf':'synthetic-csrf','sif':'synthetic-only'},provider='sif');h.do_POST();self.assertTrue(h.server.saved);self.assertEqual(set(tomllib.loads(self.config.read_text())['mcp_servers']),{'aee_sif'})
    def test_get_uses_password_inputs_and_no_external_scripts(self):
        h=self.handler();h.path='/';h.do_GET();body=h.output[0][1];self.assertEqual(body.count('type="password"'),2);self.assertNotIn('<script',body);self.assertIn('synthetic-csrf',body);self.assertFalse(self.config.exists())
    def test_http_security_headers_and_no_secret_caching(self):
        h=KeyHandler.__new__(KeyHandler);h.wfile=io.BytesIO();headers={};h.send_response=lambda s:None;h.send_header=lambda k,v:headers.update({k:v});h.end_headers=lambda:None
        h.page('<h1>Example</h1>');self.assertEqual(headers['Cache-Control'],'no-store');self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy']);self.assertIn("form-action 'self'",headers['Content-Security-Policy'])
    def test_second_submit_is_rejected(self):
        h=self.handler();h.do_POST();old=self.config.read_bytes();h.rfile.seek(0);h.do_POST();self.assertEqual(h.output[-1][0],409);self.assertEqual(old,self.config.read_bytes())
    def test_request_size_limit_before_read(self):
        h=self.handler();h.headers.replace_header('Content-Length','100000');h.do_POST();self.assertFalse(self.config.exists());self.assertEqual(h.rfile.tell(),0)

    def test_expired_submit_cannot_write(self):
        h=self.handler();h.server.deadline=0;h.do_POST();self.assertEqual(h.output[0][0],408);self.assertFalse(self.config.exists());self.assertEqual(h.rfile.tell(),0)
    def test_expiry_while_parsing_cannot_write(self):
        h=self.handler()
        from aee.research_mcp import validate_key
        def expire(key):h.server.deadline=0;return validate_key(key)
        with patch('aee.research_mcp_web.validate_key',side_effect=expire):h.do_POST()
        self.assertEqual(h.output[0][0],408);self.assertFalse(self.config.exists())
