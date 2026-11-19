"""Immutable handoff from Codex native Computer Use or a manual export.

This module deliberately has no Cookie reader, CDP socket or guessed vendor API.
The installed skill performs supported UI actions; this boundary verifies files.
"""
import shutil
from datetime import datetime, timezone
from pathlib import Path
from .common import Error, canonical, digest, load, new_dir, now, require, write_new
from .sp_engine import inspect_file
from .bounded import read_bounded

def collect(request_path, output):
    request_path=Path(request_path).resolve()
    request=load(request_path)
    require(request.get('source') in ('ziniao_ui','manual_export','synthetic'),'source 需 ziniao_ui/manual_export/synthetic')
    require(request.get('scope_confirmed') is True,'先确认本次采集店铺与站点范围')
    for field in ('account_alias','marketplace','period','captured_at','reports'):
        require(request.get(field),f'采集清单缺少 {field}')
    captured=datetime.fromisoformat(request['captured_at'].replace('Z','+00:00'))
    require(captured.tzinfo is not None and captured<=datetime.now(timezone.utc),'captured_at 需非未来的带时区时刻')
    require(set(request['period'])=={'start','end'},'period 需 start/end')
    from datetime import date
    require(date.fromisoformat(request['period']['start'])<=date.fromisoformat(request['period']['end']),'采集期间错误')
    require(isinstance(request['reports'],list) and 1<=len(request['reports'])<=2,'一次接收一或两种广告报表')
    prepared=[];seen=set()
    for item in request['reports']:
        kind=item.get('type')
        require(kind in ('campaign','search_term') and kind not in seen,'报告类型无效或重复')
        seen.add(kind)
        path=(request_path.parent/str(item.get('path',''))).resolve()
        require(path.is_file() and not path.name.endswith(('.crdownload','.part','.download')),'报表未下载完成')
        require(item.get('download_completed') is True,'需确认平台下载完成')
        require(item.get('report_scope_verified') is True,'需在报表设置中核实店铺、站点、期间')
        if request['source']=='ziniao_ui':
            require(item.get('ui_evidence'), '紫鸟导出需填写最小界面证据说明，不含 Cookie 或签名链接')
        spec={k:item[k] for k in ('sheet','header_row','encoding','delimiter') if k in item}
        blob=read_bounded(path);require(blob,'报表为空')
        # Inspect the captured bytes, not a second read of a changing download.
        import tempfile
        with tempfile.TemporaryDirectory(prefix='aee-inspect-') as scratch:
            snapshot=Path(scratch)/('input'+path.suffix.lower());snapshot.write_bytes(blob)
            try:structure=inspect_file(snapshot,spec)
            except ValueError as exc:raise Error(str(exc)) from exc
        prepared.append((item,path,blob,structure))
    output=new_dir(output)
    manifest={k:request[k] for k in ('source','account_alias','marketplace','period','captured_at')}
    manifest.update({'format_version':1,'verified_at':now(),'scope_confirmed':True,'reports':[],
                     'status':'files_verified_not_business_validated','synthetic':request['source']=='synthetic'})
    stored={}
    for item,path,blob,structure in prepared:
        key=(digest(blob),path.suffix.lower())
        if key not in stored:
            filename=item['type']+path.suffix.lower();dest=output/filename
            with dest.open('xb') as f:f.write(blob)
            dest.chmod(0o600);stored[key]=filename
        filename=stored[key];dest=output/filename
        require(digest(dest.read_bytes())==digest(blob),'文件保存后校验失败')
        manifest['reports'].append({'type':item['type'],'path':filename,'sha256':digest(blob),'bytes':len(blob),
           'original_name':path.name,'headers':structure['headers'],'data_rows':structure['data_rows'],
           'sheet':structure['sheet'],'ui_evidence':item.get('ui_evidence'),'generated_at':item.get('generated_at')})
    write_new(output/'collection.json',manifest)
    return {'status':manifest['status'],'reports':len(prepared),'unique_files':len(stored),'directory':str(output)}

def validate_handoff(config,config_path,manifest_path):
    manifest_path=Path(manifest_path).resolve();manifest=load(manifest_path)
    for key in ('account_alias','marketplace','period'):
        require(manifest.get(key)==config.get(key),'采集与分析范围不一致：'+key)
    require(manifest.get('scope_confirmed') is True,'采集范围未确认')
    require(manifest.get('source') in ('ziniao_ui','manual_export','synthetic'),'采集来源未知')
    require(len(manifest.get('reports',[]))==2,'完整广告链路需活动与搜索词两种文件')
    hashes={}
    for report in manifest['reports']:
        path=(manifest_path.parent/report['path']).resolve()
        require(path.is_relative_to(manifest_path.parent),'采集文件必须位于归档目录内')
        require(digest(path.read_bytes())==report['sha256'],'归档报表已改变')
        require(report['type'] not in hashes,'采集类型重复');hashes[report['type']]=report['sha256']
    for spec in config['reports']:
        path=(Path(config_path).resolve().parent/spec['path']).resolve()
        require(digest(path.read_bytes())==hashes.get(spec['type']),'分析文件与下载归档版本不一致')
    return manifest
