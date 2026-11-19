import contextlib
import io
import os
from pathlib import Path
import stat
import tempfile
import tomllib
import unittest
from unittest.mock import patch
from aee.common import Error
from aee.research_mcp import configure

@unittest.skipUnless(os.name=='posix','POSIX configuration helper')
class ResearchMcpTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.config=self.root/'config.toml'
    def test_plan_does_not_prompt_write_or_include_key(self):
        with patch('aee.research_mcp._key',side_effect=AssertionError('must not prompt')):
            plan=configure('both',self.config)
        self.assertEqual(plan['status'],'planned');self.assertFalse(self.config.exists());self.assertEqual(list(self.root.iterdir()),[])
    def test_both_providers_preserve_config_and_return_no_credentials(self):
        original=b'model = "example-model"\n[mcp_servers.other]\nurl = "https://example.com/mcp"\n';self.config.write_bytes(original)
        keys=['synthetic-only-one','synthetic-only-two'];output=io.StringIO()
        with patch('aee.research_mcp._key',side_effect=keys),contextlib.redirect_stdout(output):result=configure('both',self.config,True)
        text=self.config.read_text();data=tomllib.loads(text);self.assertTrue(text.startswith(original.decode().rstrip()))
        self.assertEqual(data['mcp_servers']['other']['url'],'https://example.com/mcp')
        self.assertEqual(data['mcp_servers']['aee_sellersprite']['http_headers']['secret-key'],keys[0])
        self.assertEqual(data['mcp_servers']['aee_sif']['url'],'https://mcp.sif.com/mcp?secret-key='+keys[1])
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode),0o600)
        backup=list(self.root.glob('*.aee-backup-*'));self.assertEqual(len(backup),1);self.assertEqual(backup[0].read_bytes(),original);self.assertEqual(stat.S_IMODE(backup[0].stat().st_mode),0o600)
        self.assertEqual(result['status'],'configured');self.assertFalse(result['network_calls'])
        self.assertTrue(all(k not in str(result)+output.getvalue() for k in keys))
    def test_duplicate_service_preserved_without_prompt(self):
        self.config.write_text('[mcp_servers.custom]\nurl="https://mcp.sif.com/mcp"\n')
        old=self.config.read_bytes()
        with patch('aee.research_mcp._key',side_effect=AssertionError('must not prompt')),self.assertRaises(Error):configure('sif',self.config,True)
        self.assertEqual(self.config.read_bytes(),old)
    def test_malformed_toml_does_not_echo_content(self):
        self.config.write_text('private-do-not-echo = [')
        with self.assertRaises(Error) as ctx:configure('sif',self.config,True)
        self.assertNotIn('private-do-not-echo',str(ctx.exception));self.assertEqual(self.config.read_text(),'private-do-not-echo = [')
    def test_symlink_rejected_without_touching_target(self):
        other=self.root/'other';other.write_text('untouched');self.config.symlink_to(other)
        with self.assertRaises(OSError):configure('sif',self.config,True)
        self.assertEqual(other.read_text(),'untouched')
    def test_git_workspace_rejected_before_key(self):
        (self.root/'.git').mkdir()
        with self.assertRaises(Error):configure('sif',self.config,True)
        self.assertFalse(self.config.exists())
    def test_cancel_second_key_writes_nothing(self):
        with patch('aee.research_mcp._key',side_effect=['synthetic-only',KeyboardInterrupt]),self.assertRaises(KeyboardInterrupt):configure('both',self.config,True)
        self.assertFalse(self.config.exists());self.assertEqual(list(self.root.iterdir()),[])
    def test_other_writer_change_is_not_overwritten(self):
        self.config.write_text('model="before"\n')
        def submit(label):self.config.write_text('model="concurrent"\n');return 'synthetic-only'
        with patch('aee.research_mcp._key',side_effect=submit),self.assertRaises(Error):configure('sif',self.config,True)
        self.assertEqual(self.config.read_text(),'model="concurrent"\n')
    def test_late_other_writer_change_is_not_overwritten(self):
        self.config.write_text('model="before"\n')
        import tempfile as tempmod
        mkstemp=tempmod.mkstemp
        def late_writer(*args,**kwargs):
            result=mkstemp(*args,**kwargs);self.config.write_text('model="late"\n');return result
        with patch('aee.research_mcp._key',return_value='synthetic-only'),patch('aee.research_mcp.tempfile.mkstemp',side_effect=late_writer),self.assertRaises(Error):configure('sif',self.config,True)
        self.assertEqual(self.config.read_text(),'model="late"\n')
        self.assertFalse(any(x.name.startswith('.aee-mcp-') for x in self.root.iterdir()))
    def test_noninteractive_input_rejected(self):
        with patch('aee.research_mcp.sys.stdin.isatty',return_value=False),self.assertRaises(Error):configure('sif',self.config,True)
        self.assertFalse(self.config.exists())
