import argparse
import json
import sys
from pathlib import Path
from .common import Error,write_new

def main(argv=None):
    p=argparse.ArgumentParser(description='亚马逊八项全能精英：本地工具；不执行店铺后台变更')
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('doctor')
    q=sub.add_parser('research-mcp');q.add_argument('--provider',choices=['sellersprite','sif','both'],default='both');q.add_argument('--config',default=str(Path.home()/'.codex/config.toml'));q.add_argument('--apply',action='store_true')
    q=sub.add_parser('postgres-install');q.add_argument('--apply',action='store_true')
    for command in ('local-init','local-stop'):
        q=sub.add_parser(command);q.add_argument('--root',required=True);q.add_argument('--apply',action='store_true')
        if command=='local-init':q.add_argument('--database',required=True);q.add_argument('--confirm-db',required=True)
    q=sub.add_parser('install-skills');q.add_argument('--target',required=True);q.add_argument('--apply',action='store_true')
    for command in ('db-create','db-init'):
        q=sub.add_parser(command);q.add_argument('--db',required=True);q.add_argument('--confirm-db',required=True);q.add_argument('--apply',action='store_true')
    q=sub.add_parser('collect');q.add_argument('--request',required=True);q.add_argument('--output',required=True)
    q=sub.add_parser('inspect');q.add_argument('file');q.add_argument('--sheet');q.add_argument('--header-row',type=int,default=1)
    q=sub.add_parser('inspect-workbook');q.add_argument('file')
    q=sub.add_parser('run');q.add_argument('--config',required=True);q.add_argument('--collection',required=True);q.add_argument('--db',required=True);q.add_argument('--output',required=True)
    q=sub.add_parser('db-verify');q.add_argument('--db',required=True);q.add_argument('--batch',required=True)
    q=sub.add_parser('export-html');q.add_argument('--db',required=True);q.add_argument('--batch',required=True);q.add_argument('--output',required=True)
    a=p.parse_args(argv)
    try:
        from . import setup
        from .store import Store
        if a.command=='research-mcp':
            from .research_mcp import configure
            r=configure(a.provider,a.config,a.apply)
        elif a.command=='doctor':r=setup.doctor()
        elif a.command=='postgres-install':r=setup.install_postgres(a.apply)
        elif a.command=='local-init':r=setup.local_init(a.root,a.database,a.confirm_db,a.apply)
        elif a.command=='local-stop':r=setup.local_stop(a.root,a.apply)
        elif a.command=='install-skills':r=setup.install_skills(a.target,a.apply)
        elif a.command=='db-create':r=Store(a.db).create(a.confirm_db,a.apply)
        elif a.command=='db-init':r=Store(a.db).init(a.confirm_db,a.apply)
        elif a.command=='collect':
            from .collection import collect
            r=collect(a.request,a.output)
        elif a.command=='inspect':
            from .sp_engine import inspect_file
            r=inspect_file(Path(a.file),{'sheet':a.sheet,'header_row':a.header_row})
        elif a.command=='inspect-workbook':
            from .workbook import sheets
            r=sheets(a.file)
        elif a.command=='run':
            from .pipeline import run
            r=run(a.config,a.collection,a.db,a.output)
        elif a.command=='db-verify':r=Store(a.db).verify(a.batch)
        elif a.command=='export-html':write_new(a.output,Store(a.db).report(a.batch));r={'status':'exported','output':a.output}
        print(json.dumps(r,ensure_ascii=False,indent=2));return 0
    except KeyboardInterrupt:
        print(json.dumps({'status':'cancelled','shop_changes':False},ensure_ascii=False),file=sys.stderr);return 130
    except (Error,ValueError,OSError,KeyError,TypeError) as exc:
        # Errors from parsing may contain source values; do not print raw rows.
        from .sp_engine import InputError
        message=str(exc) if isinstance(exc,(Error,InputError)) else f'{type(exc).__name__}: 配置、文件或输入校验未通过；请检查字段与格式'
        print(json.dumps({'status':'failed','error':message,'shop_changes':False},ensure_ascii=False),file=sys.stderr);return 2
