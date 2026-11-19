from pathlib import Path
from . import sp_engine
from .collection import validate_handoff
from .common import canonical,digest,load,new_dir,require,write_new
from .report import html_report
from .store import Store
from .bounded import read_bounded
from . import __version__

def run(config_path,manifest_path,database_path,output):
    import tempfile
    with tempfile.TemporaryDirectory(prefix='aee-snapshot-') as temporary:
        return _run_snapshot(config_path,manifest_path,database_path,output,Path(temporary))

def _run_snapshot(config_path,manifest_path,database_path,output,snapshot):
    config_path=Path(config_path).resolve();config=load(config_path)
    manifest=load(manifest_path)
    for key in ('account_alias','marketplace','period'):
        require(manifest.get(key)==config.get(key),'采集与分析范围不一致：'+key)
    require(manifest.get('scope_confirmed') is True,'采集范围未确认')
    require(manifest.get('source') in ('ziniao_ui','manual_export','synthetic'),'采集来源未知')
    entries=manifest.get('reports',[])
    require(len(entries)==2 and {m['type'] for m in entries}=={'campaign','search_term'},'需两份不同类型采集记录')
    import copy
    snapshot_config=copy.deepcopy(config)
    blobs={};snapshot_files={}
    if config.get('input_layout')=='shared_xlsx_sheets':
        require(len({(config_path.parent/r['path']).resolve() for r in config['reports']})==1,
                '共享工作簿配置必须明确指向同一原件路径')
    for spec in snapshot_config['reports']:
        path=(config_path.parent/spec['path']).resolve();blob=read_bounded(path)
        meta=next(m for m in entries if m['type']==spec['type'])
        require(meta.get('generated_at')==spec.get('generated_at'),'采集与分析声明的报表生成时刻不同')
        require(digest(blob)==meta['sha256'] and len(blob)==meta['bytes'],'分析输入与采集归档版本不一致')
        key=(digest(blob),path.suffix.lower())
        if key not in snapshot_files:
            dest=snapshot/('source-'+str(len(snapshot_files))+path.suffix.lower());dest.write_bytes(blob);snapshot_files[key]=dest
        dest=snapshot_files[key]
        blobs[spec['type']]=blob;spec['path']=dest.name
    snapshot_path=snapshot/'config.json';write_new(snapshot_path,snapshot_config)
    result=sp_engine.analyze(snapshot_path)
    for source in result['inputs']:
        meta=next(m for m in entries if m['type']==source['type'])
        if 'sheet' in meta:require(meta['sheet']==source['sheet'],'采集与分析实际选用的工作表不一致')
        source['path']='raw_file:'+source['type']+':'+source['sha256']
    normalized=copy.deepcopy(config)
    for report in normalized['reports']:report.pop('path',None)
    files=[];records={}
    for spec in snapshot_config['reports']:
        path=snapshot/spec['path'];blob=blobs[spec['type']]
        require(len(blob)<=20*1024*1024,'首版单文件最大20MiB；大报表请先制定分批导入方案')
        headers,rows,sheet=sp_engine.read_table(path,spec)
        require(len(rows)<=100000,'首版单表最多10万行，防止内存与事务超限')
        # Preserve header names and scalar values. Dates/numbers originating
        # from XLSX get a tagged representation instead of being guessed.
        def scalar(v):
            if v is None or isinstance(v,(str,int,float,bool)):return v
            return {'original_type':type(v).__name__,'value':str(v)}
        records[spec['type']]=[(n,{k:scalar(v) for k,v in row.items()}) for n,row in rows]
        meta=next(r for r in manifest['reports'] if r['type']==spec['type'])
        files.append((spec['type'],blob,meta))
    # Logical idempotency: source/config/version, not output path or capture time.
    batch=digest(canonical({'engine':__version__,'config':normalized,'files':{k:m['sha256'] for k,_,m in files},'source':manifest['source']}).encode())
    html=html_report(result,batch,manifest['source']=='synthetic')
    store=Store(database_path);store.ready()
    require(not Path(output).exists(),'输出目录已存在，禁止覆盖')
    receipt=store.ingest(batch,manifest,normalized,files,records,result,html)
    checks=store.verify(batch)
    # DB is authoritative. Reused batch uses the already stored report/results.
    if receipt['status']=='already_imported':
        import json
        from .store import text
        result=json.loads(store.sql('SELECT result::text FROM aee.analysis_runs WHERE batch_id='+text(batch)+';'))
        html=store.report(batch)
    import os
    output=Path(output).resolve()
    old_mask=os.umask(0o077)
    try:sp_engine.write_outputs(result,output)
    finally:os.umask(old_mask)
    write_new(output/'report.html',html)
    write_new(output/'receipt.json',{'batch_id':batch,'storage':receipt['status'],'verification':checks,'shop_changes':False})
    return {'batch_id':batch,'storage':receipt['status'],'verification':checks,'output':str(output)}
