import copy
import io
import json
import os
import re
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from aee import sp_engine
from aee.bounded import read_bounded
from aee.collection import collect
from aee.common import Error,load
from aee.pipeline import run
from aee.report import html_report
from aee.setup import install_skills

ROOT=Path(__file__).resolve().parents[1]

class LocalPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        import shutil
        for f in (ROOT/'examples/synthetic').glob('*.csv'):shutil.copyfile(f,self.root/f.name)
        self.request=load(ROOT/'examples/synthetic/request.json');self.save_request()
    def tearDown(self):self.tmp.cleanup()
    def save_request(self):
        p=self.root/'request.json';p.write_text(json.dumps(self.request));return p
    def fixture(self):
        collect(self.save_request(),self.root/'archive')
        config=load(ROOT/'examples/synthetic/sp-input.json')
        for spec in config['reports']:spec['path']='archive/'+spec['type']+'.csv'
        p=self.root/'config.json';p.write_text(json.dumps(config));return p
    def test_collect_retains_exact_bytes_and_rejects_scope(self):
        self.request['scope_confirmed']=False
        with self.assertRaises(Error):collect(self.save_request(),self.root/'rejected')
        self.assertFalse((self.root/'rejected').exists())
        self.request['scope_confirmed']=True;self.fixture()
        self.assertEqual((self.root/'campaign.csv').read_bytes(),(self.root/'archive/campaign.csv').read_bytes())
    def test_tamper_blocked_before_database(self):
        config=self.fixture();(self.root/'archive/search_term.csv').write_text('tampered')
        with patch('aee.pipeline.Store') as store:
            with self.assertRaisesRegex(Error,'版本不一致'):run(config,self.root/'archive/collection.json','unused',self.root/'output')
            store.assert_not_called()
    def test_scope_mismatch_blocked_before_database(self):
        p=self.fixture();config=load(p);config['marketplace']='CA';p.write_text(json.dumps(config))
        with patch('aee.pipeline.Store') as store:
            with self.assertRaisesRegex(Error,'范围不一致'):run(p,self.root/'archive/collection.json','unused',self.root/'output')
            store.assert_not_called()
    def test_changed_original_after_snapshot_does_not_change_import(self):
        p=self.fixture();original_analyze=sp_engine.analyze
        def changed(snapshot):
            (self.root/'archive/search_term.csv').write_text('changed after snapshot')
            return original_analyze(snapshot)
        with patch('aee.pipeline.sp_engine.analyze',side_effect=changed),patch('aee.pipeline.Store') as store:
            store.return_value.ingest.return_value={'status':'imported'}
            store.return_value.verify.return_value={'files':2,'analyses':1}
            result=run(p,self.root/'archive/collection.json','unused',self.root/'output')
            call=store.return_value.ingest.call_args.args
            self.assertIn(b'synthetic related',call[3][1][1])
            self.assertEqual(call[5]['totals']['search_term']['all']['spend'],'60')
            self.assertIn('合成样例', (self.root/'output/report.html').read_text())
    def test_file_size_guard_before_parse(self):
        p=self.root/'large.csv'
        with p.open('wb') as f:f.truncate(21*1024*1024)
        with self.assertRaisesRegex(Error,'20MiB'):read_bounded(p)
    def test_xlsx_expansion_guard(self):
        p=self.root/'large.xlsx'
        with zipfile.ZipFile(p,'w',compression=zipfile.ZIP_DEFLATED) as z:z.writestr('xl/worksheets/sheet1.xml',b'x'*(51*1024*1024))
        with self.assertRaisesRegex(Error,'50MiB'):read_bounded(p)
    def test_xlsx_wrong_declared_dimension_keeps_all_rows(self):
        try:import openpyxl
        except ImportError:self.skipTest('optional openpyxl not installed')
        p=self.root/'wrong.xlsx';book=openpyxl.Workbook();sheet=book.active;sheet.append(['Date','Spend']);sheet.append(['2025-01-01',12]);book.save(p);book.close()
        raw=io.BytesIO(p.read_bytes())
        with zipfile.ZipFile(raw) as old,zipfile.ZipFile(self.root/'fixed.xlsx','w') as new:
            for name in old.namelist():
                blob=old.read(name)
                if name=='xl/worksheets/sheet1.xml':blob=re.sub(rb'<dimension ref="[^"]+"',b'<dimension ref="A1:A1"',blob)
                new.writestr(name,blob)
        info=sp_engine.inspect_file(self.root/'fixed.xlsx',{})
        self.assertEqual(info['headers'],['Date','Spend']);self.assertEqual(info['data_rows'],1)
    def test_html_does_not_execute_search_term(self):
        p=self.fixture();result=sp_engine.analyze(p);result['search_terms'][0]['identity']['search_term']='<script>alert(1)</script>'
        html=html_report(result,'synthetic',True)
        self.assertNotIn('<script>alert(1)</script>',html);self.assertIn('&lt;script&gt;',html)
    def test_install_conflicts_do_not_overwrite(self):
        target=self.root/'skills';target.mkdir();(target/'amazon-eight-elite').mkdir();sentinel=target/'amazon-eight-elite/original';sentinel.write_text('keep')
        with self.assertRaisesRegex(Error,'目标技能已存在'):install_skills(target,True)
        self.assertEqual(sentinel.read_text(),'keep');self.assertEqual(len(list(target.iterdir())),1)
    def test_partial_install_rolls_back_only_new_destinations(self):
        import shutil
        target=self.root/'skills';target.mkdir();sentinel=target/'unrelated';sentinel.write_text('keep')
        move=shutil.move;calls=0
        def fail_later(*args,**kwargs):
            nonlocal calls
            calls+=1
            if calls==2:raise OSError('simulated disk failure')
            return move(*args,**kwargs)
        with patch('aee.setup.shutil.move',side_effect=fail_later):
            with self.assertRaises(OSError):install_skills(target,True)
        self.assertEqual(list(target.iterdir()),[sentinel]);self.assertEqual(sentinel.read_text(),'keep')

@unittest.skipUnless(os.environ.get('AEE_TEST_DB_CONFIG'),'requires explicitly authorized isolated local PostgreSQL')
class PostgreSQLIntegration(unittest.TestCase):
    def test_real_transaction_idempotency_and_export(self):
        from aee.store import Store
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);request=load(ROOT/'examples/synthetic/request.json')
            for spec in request['reports']:spec['path']=str(ROOT/'examples/synthetic'/spec['path'])
            (root/'request.json').write_text(json.dumps(request));collect(root/'request.json',root/'archive')
            config=load(ROOT/'examples/synthetic/sp-input.json')
            for spec in config['reports']:spec['path']=str(root/'archive'/(spec['type']+'.csv'))
            # Different goal keeps this test independent of an existing demo run.
            config['business_goal']='INTEGRATION TEST';(root/'config.json').write_text(json.dumps(config))
            db=os.environ['AEE_TEST_DB_CONFIG']
            a=run(root/'config.json',root/'archive/collection.json',db,root/'one')
            b=run(root/'config.json',root/'archive/collection.json',db,root/'two')
            self.assertEqual(a['batch_id'],b['batch_id']);self.assertEqual(b['storage'],'already_imported')
            self.assertEqual(b['verification']['files'],2);self.assertEqual(b['verification']['rows'],3)
            self.assertTrue(b['verification']['raw_file_hashes_match'])
            self.assertEqual(Store(db).report(a['batch_id']),(root/'one/report.html').read_text())
    def test_failed_import_rolls_back_all_new_records(self):
        from aee.store import Store,text
        from aee.common import digest
        store=Store(os.environ['AEE_TEST_DB_CONFIG']);batch=digest(b'SYNTHETIC ROLLBACK TEST')
        result={'scope':{'account_alias':'SYNTHETIC_ONLY'},'campaigns':[],'search_terms':[]}
        with self.assertRaises(Error):
            store.ingest(batch,{'source':'synthetic'},{},[],{'campaign':[(2,{'test':1}),(2,{'test':2})]},result,'synthetic')
        self.assertEqual(store.sql('SELECT count(*) FROM aee.batches WHERE batch_id='+text(batch)+';'),'0')
        self.assertEqual(store.sql('SELECT count(*) FROM aee.raw_rows WHERE batch_id='+text(batch)+';'),'0')

if __name__=='__main__':unittest.main()
