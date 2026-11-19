"""Local PostgreSQL only; SQL literals use UTF-8 hex, never raw user text.

psql -X ignores user startup files, -w never prompts, errors are not echoed.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path
from .common import Error, canonical, load, require
from . import __version__

def text(value):
    return "convert_from(decode('"+str(value).encode().hex()+"','hex'),'UTF8')"

def jsonb(value):
    return text(canonical(value))+'::jsonb'

def name(value):
    require(isinstance(value,str) and re.fullmatch(r'[a-z][a-z0-9_]{0,62}',value),'数据库/用户名称仅接受小写字母、数字、下划线，最长63字符')
    return value

class Store:
    def __init__(self,config_path):
        self.cfg=load(config_path)
        require(set(self.cfg)<= {'host','port','user','database','password_env'},'数据库配置含未知字段')
        self.database=name(self.cfg.get('database'));self.user=name(self.cfg.get('user'))
        host=self.cfg.get('host');self.host=host
        require(host in ('127.0.0.1','::1') or (isinstance(host,str) and Path(host).is_absolute() and Path(host).is_dir()),'仅允许明确的本机 IP 或本机 Unix socket 目录')
        self.port=self.cfg.get('port',5432)
        require(type(self.port) is int and 1<=self.port<=65535,'port 无效')
        require(shutil.which('psql'),'缺少 psql，请先运行 doctor')
        # Do not inherit libpq service files/options/hostaddr/SSL callbacks.
        self.env={k:v for k,v in os.environ.items() if not k.startswith('PG')}
        self.env.update({'PGCONNECT_TIMEOUT':'5','PGCLIENTENCODING':'UTF8','PGAPPNAME':'amazon-eight-elite'})
        password_key=self.cfg.get('password_env')
        if password_key:
            require(re.fullmatch(r'AEE_[A-Z0-9_]+',password_key),'password_env 需 AEE_ 前缀变量')
            require(password_key in os.environ,'所指定的数据库密码环境变量未设置')
            self.env['PGPASSWORD']=os.environ[password_key]
        self.env['PGPASSFILE']=os.devnull

    def sql(self,sql,database=None):
        argv=['psql','-X','-w','-qAt','-v','ON_ERROR_STOP=1','-h',self.host,'-p',str(self.port),'-U',self.user,'-d',database or self.database]
        try:r=subprocess.run(argv,input=sql,text=True,capture_output=True,env=self.env,timeout=120)
        except (OSError,subprocess.TimeoutExpired) as exc:raise Error('本机数据库调用失败或超时；未输出连接详情') from exc
        if r.returncode:
            # Database messages can contain private rows/SQL, so do not echo them.
            code=re.search(r'SQLSTATE[: =]+([A-Z0-9]{5})',r.stderr)
            raise Error('PostgreSQL 操作失败；检查目标、权限、schema 版本与服务状态'+(' SQLSTATE='+code[1] if code else ''))
        return r.stdout.strip()

    def check_identity(self):
        value=self.sql('SELECT current_database();')
        require(value==self.database,'实际数据库与配置不一致')
        return value

    def create(self,confirmed,apply=False):
        require(confirmed==self.database,'--confirm-db 必须与目标库准确相同')
        found=self.sql('SELECT datname FROM pg_database WHERE datname='+text(self.database)+';','postgres')
        if not apply:return {'status':'planned','database':self.database,'exists':bool(found)}
        require(not found,'目标库已经存在，禁止自动接管；改用核实后的 db-init')
        self.sql('CREATE DATABASE "'+self.database+'";','postgres');self.check_identity()
        return {'status':'created','database':self.database}

    def init(self,confirmed,apply=False):
        require(confirmed==self.database,'--confirm-db 必须与目标库准确相同');self.check_identity()
        if not apply:return {'status':'planned','schema':'aee','version':1,'database':self.database}
        marker=self.sql("SELECT coalesce(obj_description(oid,'pg_namespace'),'') FROM pg_namespace WHERE nspname='aee';")
        exists=self.sql("SELECT count(*) FROM pg_namespace WHERE nspname='aee';")=='1'
        if exists:
            require(marker=='amazon-eight-elite:v1','已有 aee schema 不属于本项目 v1，停止变更')
            require(self.sql('SELECT version FROM aee.schema_version;')=='1','schema 版本不支持')
            return {'status':'already_initialized','version':1}
        sql=(Path(__file__).parent/'schema.sql').read_text()
        self.sql('BEGIN;'+sql+'COMMIT;')
        require(self.sql('SELECT version FROM aee.schema_version;')=='1','schema 创建后回读不符')
        return {'status':'initialized','version':1}

    def ready(self):
        self.check_identity()
        require(self.sql("SELECT coalesce(obj_description(oid,'pg_namespace'),'') FROM pg_namespace WHERE nspname='aee';")=='amazon-eight-elite:v1','目标 schema 未确认为本项目')
        require(self.sql('SELECT version FROM aee.schema_version;')=='1','请先对已确认的独立库执行 db-init')

    def ingest(self,batch,collection,config,files,records,result,html):
        self.ready()
        # Everything is in one transaction. An existing content-derived batch
        # returns idempotently only when the same pipeline/config hash matches.
        existing=self.sql('SELECT input_hash FROM aee.batches WHERE batch_id='+text(batch)+';')
        if existing:
            require(existing==batch,'批次标识冲突')
            return {'status':'already_imported','batch_id':batch}
        statements=['BEGIN;',"SELECT pg_advisory_xact_lock(hashtext('aee-ingest'));",
           'INSERT INTO aee.batches(batch_id,input_hash,scope,collection,config,engine_version) VALUES ('+
           ','.join([text(batch),text(batch),jsonb(result['scope']),jsonb(collection),jsonb(config),text(__version__)])+');']
        for kind,blob,meta in files:
            statements.append('INSERT INTO aee.raw_files(batch_id,report_type,sha256,original_name,content,metadata) VALUES ('+
              ','.join([text(batch),text(kind),text(meta['sha256']),text(meta['original_name']),"decode('"+blob.hex()+"','hex')",jsonb(meta)])+');')
        for kind,rows in records.items():
            for ordinal,row in rows:
                statements.append('INSERT INTO aee.raw_rows(batch_id,report_type,source_row,payload) VALUES ('+
                  ','.join([text(batch),text(kind),str(ordinal),jsonb(row)])+');')
        for kind in ('campaigns','search_terms'):
            for index,group in enumerate(result[kind]):
                statements.append('INSERT INTO aee.ad_groups(batch_id,grain,ordinal,payload) VALUES ('+
                  ','.join([text(batch),text(kind),str(index),jsonb(group)])+');')
        statements.append('INSERT INTO aee.analysis_runs(batch_id,result,html) VALUES ('+','.join([text(batch),jsonb(result),text(html)])+');')
        statements.append('COMMIT;')
        try:self.sql('\n'.join(statements))
        except Error:
            # Retry/read after another identical import won the advisory lock.
            if self.sql('SELECT count(*) FROM aee.analysis_runs WHERE batch_id='+text(batch)+';')!='1':raise
            return {'status':'already_imported','batch_id':batch}
        return {'status':'imported','batch_id':batch}

    def verify(self,batch):
        self.ready()
        query="""SELECT json_build_object('files',(SELECT count(*) FROM aee.raw_files WHERE batch_id={b}),'rows',(SELECT count(*) FROM aee.raw_rows WHERE batch_id={b}),'groups',(SELECT count(*) FROM aee.ad_groups WHERE batch_id={b}),'analyses',(SELECT count(*) FROM aee.analysis_runs WHERE batch_id={b}),'bytes',(SELECT coalesce(sum(octet_length(content)),0) FROM aee.raw_files WHERE batch_id={b}),'raw_file_hashes_match',(SELECT coalesce(bool_and(encode(sha256(content),'hex')=sha256),false) FROM aee.raw_files WHERE batch_id={b}));""".format(b=text(batch))
        import json
        result=json.loads(self.sql(query));require(result['files']==2 and result['analyses']==1 and result['raw_file_hashes_match'],'批次验收失败')
        expected=self.sql("SELECT json_build_object('rows',(SELECT sum(coalesce((i->>'raw_row_count')::int,(i->>'row_count')::int)) FROM jsonb_array_elements(result->'inputs') i),'groups',jsonb_array_length(result->'campaigns')+jsonb_array_length(result->'search_terms')) FROM aee.analysis_runs WHERE batch_id="+text(batch)+';')
        expected=json.loads(expected)
        require(result['rows']==expected['rows'] and result['groups']==expected['groups'],'原始行或指标分组计数不一致')
        return result

    def report(self,batch):
        self.ready();value=self.sql('SELECT encode(convert_to(html,\'UTF8\'),\'hex\') FROM aee.analysis_runs WHERE batch_id='+text(batch)+';')
        require(value,'批次不存在');return bytes.fromhex(value).decode()
