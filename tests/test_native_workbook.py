"""Synthetic-only examples of platform workbook structure; no account data."""
import copy
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from aee import sp_engine
from aee.collection import collect
from aee.common import Error,load
from aee.pipeline import run

ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(importlib.util.find_spec('openpyxl'),'optional openpyxl required')
class NativeWorkbook(unittest.TestCase):
    def setUp(self):
        import openpyxl
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.config=load(ROOT/'examples/synthetic/sp-input.json')
        self.config['input_layout']='shared_xlsx_sheets'
        self.book=openpyxl.Workbook();campaign=self.book.active;campaign.title='Campaigns'
        self.headers=['Entity','Campaign ID','Campaign Name','Ad Group ID','Customer Search Term','Impressions','Clicks','Spend','Purchases','Sales']
        campaign.append(self.headers)
        campaign.append(['Campaign','synthetic_c1','Synthetic campaign','','',1000,60,60,5,250])
        campaign.append(['Ad group','synthetic_c1','Synthetic campaign','synthetic_g1','',1000,60,60,5,250])
        search=self.book.create_sheet('Search terms');search.append(self.headers)
        search.append(['Search term','synthetic_c1','Synthetic campaign','synthetic_g1','synthetic term',1000,60,60,5,250])
        for spec in self.config['reports']:
            spec['path']='native.xlsx';spec['granularity']='summary';spec['columns'].pop('date')
            spec['sheet']='Campaigns' if spec['type']=='campaign' else 'Search terms'
            spec['row_filter']={'Entity':['Campaign' if spec['type']=='campaign' else 'Search term']}
        self.save()
    def tearDown(self):self.book.close();self.tmp.cleanup()
    def save(self):
        self.book.save(self.root/'native.xlsx');p=self.root/'config.json';p.write_text(json.dumps(self.config));return p
    def test_native_ids_and_only_campaign_entity_counted(self):
        result=sp_engine.analyze(self.save())
        self.assertEqual(result['totals']['campaign']['all']['spend'],'60')
        self.assertEqual(result['totals']['campaign']['rows'],1)
        self.assertEqual(result['inputs'][0]['raw_row_count'],2)
        self.assertEqual(result['search_terms'][0]['identity']['campaign_id'],'synthetic_c1')
        self.assertEqual(result['search_terms'][0]['identity']['ad_group_id'],'synthetic_g1')
        self.assertEqual(result['search_terms'][0]['source_rows'],[2])
    def test_unconfirmed_timezone_never_makes_mature_candidates(self):
        self.config['timezone_confirmed']=False
        self.config['analysis_notes']=['Synthetic reference timezone, not verified business timezone']
        result=sp_engine.analyze(self.save())
        self.assertFalse(result['scope']['timezone_confirmed'])
        self.assertEqual(result['totals']['search_term']['mature_rows'],0)
        self.assertTrue(all(g['action']=='observe' for g in result['search_terms']))
        self.assertTrue(any('业务时区未核实' in w for w in result['warnings']))
    def test_workbook_discovery_only_returns_names(self):
        from aee.workbook import sheets
        result=sheets(self.root/'native.xlsx')
        self.assertEqual(result['sheets'],['Campaigns','Search terms'])
        self.assertNotIn('synthetic_c1',json.dumps(result))
    def test_source_metric_contradiction_is_strict_by_default(self):
        self.book['Search terms']['F2']=10
        with self.assertRaisesRegex(sp_engine.InputError,'点击大于曝光'):sp_engine.analyze(self.save())
    def test_preserve_observe_keeps_money_and_flags_source(self):
        self.config['quality_mode']='preserve_observe';self.book['Search terms']['F2']=10
        result=sp_engine.analyze(self.save())
        self.assertEqual(result['totals']['search_term']['all']['spend'],'60')
        self.assertEqual(result['search_terms'][0]['action'],'observe')
        self.assertEqual(result['data_quality'][0]['source_row'],2)
        self.assertEqual(result['data_quality'][0]['issues'],['clicks_exceed_impressions'])
        from aee.report import html_report
        html=html_report(result,'synthetic',True)
        self.assertIn('点击数大于曝光数',html);self.assertIn('全期花费',html)
    def test_quality_group_stays_observe_even_with_other_mature_rows(self):
        self.config['quality_mode']='preserve_observe';self.config['period']['end']='2025-01-02'
        sheet=self.book['Search terms'];sheet['K1']='Date';sheet['K2']='2025-01-01';sheet['F2']=10
        sheet.append(['Search term','synthetic_c1','Synthetic campaign','synthetic_g1','synthetic term',1000,60,60,5,250,'2025-01-02'])
        spec=self.config['reports'][1];spec['granularity']='daily';spec['columns']['date']='Date'
        result=sp_engine.analyze(self.save());group=result['search_terms'][0]
        self.assertEqual(group['all']['spend'],'120');self.assertEqual(group['mature']['spend'],'60')
        self.assertEqual(group['action'],'observe')
    def test_preserve_observe_still_rejects_missing_and_negative_values(self):
        self.config['quality_mode']='preserve_observe'
        for value in (None,-1):
            self.book['Search terms']['H2']=value
            with self.assertRaises(sp_engine.InputError):sp_engine.analyze(self.save())
    def test_shared_workbook_requires_explicit_mode(self):
        self.config.pop('input_layout')
        with self.assertRaisesRegex(sp_engine.InputError,'同一文件'):sp_engine.analyze(self.save())
    def test_same_sheet_cannot_impersonate_two_reports(self):
        self.config['reports'][1]['sheet']='Campaigns'
        self.config['reports'][1]['row_filter']={'Entity':['Ad group']}
        self.config['reports'][1]['columns']['search_term']='Campaign Name'
        self.config['reports'][1]['columns'].pop('campaign_name')
        with self.assertRaisesRegex(sp_engine.InputError,'两个不同'):sp_engine.analyze(self.save())
    def test_unknown_filter_and_empty_selection_stop(self):
        self.config['reports'][0]['row_filter']={'Unknown':['Campaign']}
        with self.assertRaisesRegex(sp_engine.InputError,'row_filter'):sp_engine.analyze(self.save())
        self.config['reports'][0]['row_filter']={'Entity':['Unknown']}
        with self.assertRaisesRegex(sp_engine.InputError,'没有匹配数据'):sp_engine.analyze(self.save())
    def test_numeric_id_precision_rejected(self):
        for sheet in self.book:
            for row in sheet.iter_rows(min_row=2):row[1].value=1234567890123456
        with self.assertRaisesRegex(sp_engine.InputError,'15位'):sp_engine.analyze(self.save())
    def test_scientific_notation_identifier_rejected(self):
        for sheet in self.book:
            for row in sheet.iter_rows(min_row=2):row[1].value='1.23456789e15'
        with self.assertRaisesRegex(sp_engine.InputError,'科学计数法'):sp_engine.analyze(self.save())
    def test_ad_group_identifier_scoped_to_campaign_keeps_groups_separate(self):
        self.book['Campaigns'].append(['Campaign','synthetic_c2','Second','','',100,10,2,0,0])
        self.book['Search terms'].append(['Search term','synthetic_c2','Second','synthetic_g1','other',100,10,2,0,0])
        result=sp_engine.analyze(self.save())
        self.assertEqual(len(result['search_terms']),2)
        self.assertEqual({g['identity']['campaign_id'] for g in result['search_terms']},{'synthetic_c1','synthetic_c2'})
    def test_shared_snapshots_and_raw_rows_preserved_in_pipeline(self):
        request=load(ROOT/'examples/synthetic/request.json')
        for spec,r in zip(self.config['reports'],request['reports']):
            r['path']='native.xlsx';r['sheet']=spec['sheet']
        (self.root/'request.json').write_text(json.dumps(request))
        collect(self.root/'request.json',self.root/'archive')
        manifest=load(self.root/'archive/collection.json')
        self.assertEqual(len({m['path'] for m in manifest['reports']}),1)
        for spec in self.config['reports']:spec['path']='archive/campaign.xlsx'
        p=self.root/'config.json';p.write_text(json.dumps(self.config))
        with patch('aee.pipeline.Store') as store:
            store.return_value.ingest.return_value={'status':'imported'};store.return_value.verify.return_value={'files':2,'analyses':1}
            run(p,self.root/'archive/collection.json','unused',self.root/'out')
            args=store.return_value.ingest.call_args.args
            self.assertEqual(args[3][0][1],args[3][1][1])
            self.assertEqual(len(args[4]['campaign']),2)
            self.assertEqual(args[5]['totals']['campaign']['rows'],1)
    def test_separate_single_sheet_xlsx_allows_automatic_sheet_selection(self):
        import openpyxl
        self.config.pop('input_layout')
        request=load(ROOT/'examples/synthetic/request.json')
        for spec,r in zip(self.config['reports'],request['reports']):
            sheetname=spec.pop('sheet');filename=spec['type']+'.xlsx';book=openpyxl.Workbook();sheet=book.active;sheet.title=sheetname
            for row in self.book[sheetname].values:sheet.append(row)
            book.save(self.root/filename);book.close();r['path']=filename
            spec['path']='archive/'+filename
        (self.root/'request.json').write_text(json.dumps(request));collect(self.root/'request.json',self.root/'archive')
        p=self.root/'config.json';p.write_text(json.dumps(self.config))
        with patch('aee.pipeline.Store') as store:
            store.return_value.ingest.return_value={'status':'imported'};store.return_value.verify.return_value={'files':2,'analyses':1}
            run(p,self.root/'archive/collection.json','unused',self.root/'out')
            self.assertEqual(store.return_value.ingest.call_args.args[5]['totals']['campaign']['all']['spend'],'60')
    @unittest.skipUnless(os.environ.get('AEE_TEST_DB_CONFIG'),'requires explicitly authorized synthetic PostgreSQL')
    def test_shared_workbook_postgresql_roundtrip(self):
        request=load(ROOT/'examples/synthetic/request.json')
        for spec,r in zip(self.config['reports'],request['reports']):r['path']='native.xlsx';r['sheet']=spec['sheet']
        (self.root/'request.json').write_text(json.dumps(request));collect(self.root/'request.json',self.root/'archive')
        for spec in self.config['reports']:spec['path']='archive/campaign.xlsx'
        p=self.root/'config.json';p.write_text(json.dumps(self.config))
        result=run(p,self.root/'archive/collection.json',os.environ['AEE_TEST_DB_CONFIG'],self.root/'out')
        self.assertEqual(result['verification']['rows'],3)
        self.assertEqual(result['verification']['groups'],2)
        self.assertTrue(result['verification']['raw_file_hashes_match'])

if __name__=='__main__':unittest.main()
