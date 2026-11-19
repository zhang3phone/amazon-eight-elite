"""Public packaging must exclude ad hoc business artifacts."""
import importlib.util
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location('public_export',Path(__file__).resolve().parents[1]/'scripts/export_public.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class PublicExportTests(unittest.TestCase):
    def test_ad_hoc_business_files_excluded(self):
        for name in ['docs/live.html','examples/raw.csv','examples/synthetic/live.json']:
            self.assertFalse(module.allowed(module.ROOT/name))

    def test_known_native_template_included(self):
        self.assertTrue(module.allowed(module.ROOT/'examples/native-bulk.template.json'))
