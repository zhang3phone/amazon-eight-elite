"""Synthetic fixtures only. Does not validate any real account or threshold."""
import copy
import csv
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

SCRIPT=Path(__file__).resolve().parents[1]/"aee/sp_engine.py"
spec=importlib.util.spec_from_file_location("analyze_sp",SCRIPT)
ads=importlib.util.module_from_spec(spec)
spec.loader.exec_module(ads)


class AnalyzeSP(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="synthetic-amazon-sp-")
        self.root=Path(self.temp.name)
        self.headers=["Date","Campaign ID","Campaign Name","Ad Group ID","Customer Search Term","Impressions","Clicks","Spend","Purchases","Sales"]
        self.campaign=[['2026-11-01','c1','Sample','','',1000,100,50,10,200],
                       ['2026-11-17','c1','Sample','','',100,10,5,0,0]]
        self.search=[['2026-11-01','c1','Sample','g1','yoga mat',500,20,20,4,100],
                     ['2026-11-01','c1','Sample','g1','unrelated',100,20,30,0,0],
                     ['2026-11-17','c1','Sample','g1','fresh',100,10,5,0,0]]
        columns={"date":"Date","campaign_id":"Campaign ID","campaign_name":"Campaign Name",
                 "impressions":"Impressions","clicks":"Clicks","spend":"Spend","orders":"Purchases","sales":"Sales"}
        self.config={"account_alias":"SYNTHETIC_ONLY","marketplace":"US","currency":"USD","timezone":"America/Los_Angeles",
                     "advertiser_type":"seller","ad_product":"SP","period":{"start":"2026-11-01","end":"2026-11-17"},
                     "attribution_window_days":7,"reporting_lag_hours":24,"number_format":"decimal_dot",
                     "rules":{"target_acos":0.25,"minimum_clicks":10,"minimum_orders":3,"zero_order_spend_limit":25},"reports":[]}
        for kind in ("campaign","search_term"):
            mapping=copy.deepcopy(columns)
            if kind=="search_term": mapping.update({"ad_group_id":"Ad Group ID","search_term":"Customer Search Term"})
            self.config["reports"].append({"type":kind,"path":kind+".csv","generated_at":"2026-11-18T12:00:00+00:00",
                 "scope_confirmed":True,"granularity":"daily","columns":mapping})

    def tearDown(self):
        self.temp.cleanup()

    def save(self):
        for name,rows in (("campaign",self.campaign),("search_term",self.search)):
            with (self.root/(name+".csv")).open("w",encoding="utf-8-sig",newline="") as f:
                writer=csv.writer(f); writer.writerow(self.headers); writer.writerows(rows)
        path=self.root/"config.json"
        path.write_text(json.dumps(self.config),encoding="utf-8")
        return path

    def run_analysis(self):
        return ads.analyze(self.save())

    def groups(self,result):
        return {g["identity"]["search_term"]:g for g in result["search_terms"]}

    def test_mature_candidates_and_recent_observation(self):
        result=self.run_analysis(); g=self.groups(result)
        self.assertEqual(g['unrelated']['action'],'review_negative')
        self.assertEqual(g['yoga mat']['action'],'review_expansion')
        self.assertEqual(g['fresh']['action'],'observe')
        self.assertEqual(result['totals']['campaign']['all']['spend'],'55')
        self.assertEqual(result['totals']['search_term']['mature']['spend'],'50')
        self.assertTrue(any('覆盖不同' in w for w in result['warnings']))
        self.assertEqual(g['unrelated']['mature_source_rows'],[3])

    def test_ratio_uses_aggregate_amounts(self):
        self.search=[['2026-11-01','c1','Sample','g1','shared',100,10,10,1,10],
                     ['2026-11-02','c1','Sample','g1','shared',100,10,90,9,900]]
        group=self.groups(self.run_analysis())['shared']
        self.assertEqual(Decimal(group['all']['acos']),Decimal(100)/Decimal(910))
        self.assertNotEqual(Decimal(group['all']['acos']),Decimal('0.55'))

    def test_missing_rules_remain_observations(self):
        self.config['rules']={}
        self.assertTrue(all(g['action']=='observe' for g in self.run_analysis()['search_terms']))

    def test_partial_rules_do_not_invent_thresholds(self):
        self.config['rules']={'minimum_clicks':10}
        self.assertTrue(all(g['action']=='observe' for g in self.run_analysis()['search_terms']))

    def test_zero_sales_is_null_acos_not_zero(self):
        self.assertIsNone(self.groups(self.run_analysis())['unrelated']['all']['acos'])

    def test_blank_sales_is_blocking(self):
        self.search[0][-1]=''
        with self.assertRaisesRegex(ads.InputError,'缺失数值'): self.run_analysis()

    def test_invalid_and_negative_amounts_block(self):
        for value in ('NaN','Infinity','-10','1,23.4'):
            with self.subTest(value=value):
                self.search[0][7]=value
                with self.assertRaises(ads.InputError): self.run_analysis()

    def test_count_cannot_be_fractional(self):
        self.search[0][6]=1.5
        with self.assertRaisesRegex(ads.InputError,'整数'): self.run_analysis()

    def test_duplicate_grain_blocks(self):
        self.search.append(copy.deepcopy(self.search[0]))
        with self.assertRaisesRegex(ads.InputError,'粒度重复'): self.run_analysis()

    def test_campaign_name_change_does_not_evade_duplicate_check(self):
        repeated=copy.deepcopy(self.campaign[0]); repeated[2]='Renamed'
        self.campaign.append(repeated)
        with self.assertRaisesRegex(ads.InputError,'粒度重复'): self.run_analysis()

    def test_same_campaign_name_different_ids_stays_separate(self):
        c=copy.deepcopy(self.campaign[0]); c[1]='c2'; self.campaign.append(c)
        q=copy.deepcopy(self.search[0]); q[1]='c2'; self.search.append(q)
        result=self.run_analysis()
        self.assertEqual(len(result['campaigns']),2)

    def test_unknown_campaign_blocks(self):
        self.search[0][1]='not-in-campaign-file'
        with self.assertRaisesRegex(ads.InputError,'campaign_id'): self.run_analysis()

    def test_currency_scope_column_blocks_mixing(self):
        self.headers.append('Currency')
        for row in self.campaign+self.search: row.append('USD')
        self.search[0][-1]='EUR'
        for report in self.config['reports']: report['columns']['currency']='Currency'
        with self.assertRaisesRegex(ads.InputError,'currency'): self.run_analysis()

    def test_unconfirmed_scope_blocks(self):
        self.config['reports'][0]['scope_confirmed']=False
        with self.assertRaisesRegex(ads.InputError,'范围'): self.run_analysis()

    def test_window_header_mismatch_blocks(self):
        self.headers[-1]='14 Day Total Sales'
        for report in self.config['reports']: report['columns']['sales']='14 Day Total Sales'
        with self.assertRaisesRegex(ads.InputError,'窗口'): self.run_analysis()

    def test_promoted_sales_subset_blocks(self):
        self.headers[-1]='Sales (promoted)'
        for report in self.config['reports']: report['columns']['sales']='Sales (promoted)'
        with self.assertRaisesRegex(ads.InputError,'子集'): self.run_analysis()

    def test_date_outside_scope_blocks(self):
        self.search[0][0]='2026-10-01'
        with self.assertRaisesRegex(ads.InputError,'超出'): self.run_analysis()

    def test_generation_time_requires_timezone(self):
        self.config['reports'][0]['generated_at']='2026-11-18T12:00:00'
        with self.assertRaises(ads.InputError): self.run_analysis()

    def test_maturity_boundary_uses_local_day_end_plus_window_and_lag(self):
        self.search=[['2026-11-01','c1','Sample','g1','boundary',100,20,30,0,0]]
        # D=Nov 1; end of day +7 days +24h lag => Nov 10 00:00 PST = 08:00 UTC.
        for generated,mature in [('2026-11-10T07:59:59+00:00',False),('2026-11-10T08:00:00+00:00',True)]:
            with self.subTest(generated=generated):
                self.config['period']['end']='2026-11-01'; self.campaign=self.campaign[:1]
                for report in self.config['reports']: report['generated_at']=generated
                self.assertEqual(bool(self.groups(self.run_analysis())['boundary']['mature_source_rows']),mature)

    def test_summary_mixed_maturity_not_split(self):
        self.headers=self.headers[1:]
        self.campaign=[self.campaign[0][1:]]; self.search=[self.search[0][1:]]
        for report in self.config['reports']:
            report['granularity']='summary'; del report['columns']['date']
        self.assertTrue(all(g['action']=='observe' for g in self.run_analysis()['search_terms']))

    def test_decimal_comma_and_grouping(self):
        self.config['number_format']='decimal_comma'; self.search[0][7]='1.234,56'
        self.assertEqual(self.groups(self.run_analysis())['yoga mat']['all']['spend'],'1234.56')

    def test_chinese_headers_with_explicit_mapping(self):
        translated={'Date':'日期','Campaign ID':'活动编号','Campaign Name':'活动名称','Ad Group ID':'广告组编号',
                    'Customer Search Term':'搜索词','Impressions':'曝光','Clicks':'点击','Spend':'花费','Purchases':'订单','Sales':'销售额'}
        self.headers=[translated[h] for h in self.headers]
        for report in self.config['reports']:
            report['columns']={k:translated[v] for k,v in report['columns'].items()}
        self.assertEqual(len(self.run_analysis()['search_terms']),3)

    def test_unknown_mapping_blocks(self):
        self.config['reports'][0]['columns']['spend']='Unknown'
        with self.assertRaisesRegex(ads.InputError,'表头'): self.run_analysis()

    def test_identical_input_file_rejected(self):
        self.campaign=copy.deepcopy(self.search)
        with self.assertRaises(ads.InputError): self.run_analysis()

    def test_csv_injection_is_sanitized_and_json_preserves_original(self):
        self.search[0][4]='=HYPERLINK("https://invalid.example")'
        result=self.run_analysis(); out=self.root/'result'
        ads.write_outputs(result,out)
        with (out/'candidates.csv').open(encoding='utf-8-sig',newline='') as stream:
            rows=list(csv.DictReader(stream))
        row=next(r for r in rows if 'HYPERLINK' in r['search_term'])
        self.assertTrue(row['search_term'].startswith("'="))
        loaded=json.loads((out/'metrics.json').read_text())
        self.assertTrue(any(g['identity']['search_term'].startswith('=') for g in loaded['search_terms']))

    def test_existing_output_not_overwritten(self):
        result=self.run_analysis(); out=self.root/'result'; out.mkdir(); marker=out/'keep'; marker.write_text('original')
        with self.assertRaises(ads.InputError): ads.write_outputs(result,out)
        self.assertEqual(marker.read_text(),'original')

    def test_cli_invalid_input_has_nonzero_exit_and_no_output(self):
        self.search[0][-1]=''; config=self.save(); out=self.root/'not-created'
        done=subprocess.run([sys.executable,str(SCRIPT),'--config',str(config),'--output',str(out)],capture_output=True,text=True)
        self.assertEqual(done.returncode,2)
        self.assertFalse(out.exists())

    def test_cli_success_and_inspection(self):
        config=self.save(); out=self.root/'result'
        done=subprocess.run([sys.executable,str(SCRIPT),'--config',str(config),'--output',str(out)],capture_output=True,text=True)
        self.assertEqual(done.returncode,0,done.stderr)
        self.assertEqual({p.name for p in out.iterdir()},{'metrics.json','candidates.csv','diagnosis.md'})
        inspected=subprocess.run([sys.executable,str(SCRIPT),'--inspect',str(self.root/'search_term.csv')],capture_output=True,text=True)
        self.assertEqual(json.loads(inspected.stdout)['data_rows'],3)

    def test_tsv_with_bom(self):
        path=self.root/'sample.tsv'
        path.write_text('\ufeffDate\tClicks\n2026-11-01\t5\n',encoding='utf-8')
        self.assertEqual(ads.inspect_file(path,{})['headers'],['Date','Clicks'])

    @unittest.skipUnless(importlib.util.find_spec('openpyxl'),'optional openpyxl not installed')
    def test_xlsx_numeric_and_formula_and_sheet_selection(self):
        import openpyxl
        path=self.root/'sample.xlsx'; book=openpyxl.Workbook(); sheet=book.active
        sheet.append(['Date','Spend']); sheet.append([date(2026,11,1),12.5]); book.save(path); book.close()
        info=ads.inspect_file(path,{})
        self.assertEqual(info['data_rows'],1)
        book=openpyxl.load_workbook(path); book.active['B2']='=10+2.5'; book.save(path); book.close()
        with self.assertRaisesRegex(ads.InputError,'公式'): ads.inspect_file(path,{})
        book=openpyxl.Workbook(); book.active.append(['A']); book.create_sheet('Other').append(['B']); book.save(path); book.close()
        with self.assertRaisesRegex(ads.InputError,'sheet'): ads.inspect_file(path,{})
        self.assertEqual(ads.inspect_file(path,{'sheet':'Other'})['sheet'],'Other')

    @unittest.skipUnless(importlib.util.find_spec('openpyxl'),'optional openpyxl not installed')
    def test_xlsx_full_analysis(self):
        import openpyxl
        config=self.save()
        for name,rows in (('campaign',self.campaign),('search_term',self.search)):
            book=openpyxl.Workbook(); sheet=book.active; sheet.append(self.headers)
            for row in rows: sheet.append(row)
            book.save(self.root/(name+'.xlsx')); book.close()
        for report in self.config['reports']: report['path']=report['type']+'.xlsx'
        config.write_text(json.dumps(self.config))
        self.assertEqual(self.groups(ads.analyze(config))['unrelated']['action'],'review_negative')

    def test_invalid_report_entry_blocks(self):
        self.config['reports']=[None,{}]
        with self.assertRaises(ads.InputError): self.run_analysis()

    def test_zero_orders_with_positive_sales_blocks(self):
        self.search[1][-1]=100
        with self.assertRaisesRegex(ads.InputError,'订单为零'):
            self.run_analysis()

    def test_future_report_generation_time_blocks(self):
        for report in self.config['reports']:
            report['generated_at']='2099-11-18T12:00:00+00:00'
        with self.assertRaisesRegex(ads.InputError,'未来'):
            self.run_analysis()

    def test_generation_clock_tolerance(self):
        allowed_now=datetime.fromisoformat('2026-11-18T11:55:00+00:00')
        ads.validate_config(self.config,now=allowed_now)
        with self.assertRaisesRegex(ads.InputError,'未来'):
            ads.validate_config(self.config,now=datetime.fromisoformat('2026-11-18T11:54:59+00:00'))

    def test_unknown_per_report_window_is_not_ignored(self):
        self.config['reports'][1]['attribution_window_days']=14
        with self.assertRaisesRegex(ads.InputError,'未知字段'):
            self.run_analysis()

    def test_candidate_has_clicks_ids_dates_and_source(self):
        result=self.run_analysis(); out=self.root/'review'
        ads.write_outputs(result,out)
        with (out/'candidates.csv').open(encoding='utf-8-sig',newline='') as stream:
            rows=list(csv.DictReader(stream))
        row=next(r for r in rows if r['search_term']=='unrelated')
        self.assertEqual(row['mature_clicks'],'20')
        self.assertEqual(row['campaign_id'],'c1')
        self.assertEqual(json.loads(row['mature_dates']),['2026-11-01'])
        self.assertEqual(row['period_end'],'2026-11-17')
        self.assertIn('target_id',row)
        self.assertEqual(json.loads(row['source_rows']),[3])

    def test_missing_dates_are_disclosed_not_zero_filled(self):
        result=self.run_analysis()
        self.assertTrue(any('不能自动认定为零' in w for w in result['warnings']))
        self.assertEqual(result['inputs'][0]['dates_with_records'],['2026-11-01','2026-11-17'])


if __name__=='__main__':
    unittest.main(verbosity=2)
