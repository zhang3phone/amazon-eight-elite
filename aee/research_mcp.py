"""Prepare official research MCP configuration; keys never enter CLI arguments."""
import getpass
import json
import os
import stat
import sys
import tempfile
import tomllib
import warnings
from pathlib import Path
from urllib.parse import urlencode
from .common import Error,require

ROOT=Path(__file__).resolve().parents[1]
PROVIDERS={
    'sellersprite':{'name':'卖家精灵','server':'aee_sellersprite','url':'https://mcp.sellersprite.com/v2/mcp','keys':'https://www.sellersprite.com/v3/mcp-manager?tab=secret'},
    'sif':{'name':'SIF','server':'aee_sif','url':'https://mcp.sif.com/mcp','keys':'https://www.sif.com/mcp?tab=secret'},
}

def _read(path):
    try:
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    except FileNotFoundError:
        return b'',None
    with os.fdopen(fd,'rb') as f:
        info=os.fstat(f.fileno())
        require(stat.S_ISREG(info.st_mode),'配置目标须为普通文件')
        require(info.st_uid==os.getuid(),'配置文件须属于当前用户')
        return f.read(),info

def validate_key(key):
    require(isinstance(key,str) and bool(key) and len(key)<=4096 and all(33<=ord(c)<=126 for c in key),'Key 不能为空或包含空白/控制字符；请重新在本机提交')
    return key

def _key(label):
    require(sys.stdin.isatty(),'请在本机交互终端输入 Key，不支持聊天、命令参数或管道输入')
    with warnings.catch_warnings():
        warnings.simplefilter('error',getpass.GetPassWarning)
        try:
            key=getpass.getpass(f'{label} MCP Key（隐藏输入）：')
        except (EOFError,getpass.GetPassWarning) as exc:
            raise Error('无法隐藏输入，已停止；请改用本机交互终端') from None
    return validate_key(key)

def configure(provider,config,apply=False,*,key_reader=None):
    require(provider in (*PROVIDERS,'both'),'请选择 sellersprite、sif 或 both')
    selected=list(PROVIDERS) if provider=='both' else [provider]
    path=Path(config).expanduser().absolute()
    # Resolve parents only; never follow a config-file symlink.
    path=path.parent.resolve()/path.name
    require(not path.is_relative_to(ROOT),'凭据配置必须位于项目目录之外')
    require(not any((p/'.git').exists() for p in [path.parent,*path.parents]),'凭据配置不能写入 Git 工作区')
    plan={'status':'planned','config':str(path),'providers':[{'provider':p,**PROVIDERS[p]} for p in selected],
          'key_entry':'运行 --apply 后在本机终端隐藏输入；不接收 --key 参数',
          'credential_storage':'Codex 本机 config.toml（0600），SIF 按官方示例含带密钥的 URL；勿分享配置或完整 URL',
          'network_calls':False,'live_connection':'pending_key_and_client_reload'}
    if not apply:return plan
    require(os.name=='posix' and hasattr(os,'O_NOFOLLOW'),'本辅助配置仅验证POSIX；其他系统按官方客户端教程配置')
    require(path.parent.is_dir(),'配置父目录不存在；请先启动 Codex 或选择已存在的私有目录')
    lock=path.with_name(path.name+'.aee-mcp.lock')
    try:
        lockfd=os.open(lock,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    except FileExistsError:
        raise Error('已有配置任务锁，请核实是否另有任务在运行') from None
    temp=None
    try:
        original,info=_read(path)
        try:parsed=tomllib.loads(original.decode('utf-8'))
        except (UnicodeError,tomllib.TOMLDecodeError):raise Error('现有配置无法解析；保留原文件并停止') from None
        servers=parsed.get('mcp_servers',{})
        require(isinstance(servers,dict),'现有 mcp_servers 结构不兼容')
        for p in selected:
            require(PROVIDERS[p]['server'] not in servers,'已有同名 MCP 配置，停止且不覆盖')
            # Avoid silently duplicating an already configured official service.
            host=PROVIDERS[p]['url'].split('/')[2]
            require(not any(isinstance(v,dict) and host in str(v.get('url','')).split('/')[2:3] for v in servers.values()),'已有该官方服务配置，请在客户端复用，不重复添加')
        chunks=[]
        for p in selected:
            spec=PROVIDERS[p];key=validate_key((key_reader or _key)(spec['name']))
            url=spec['url']+('?' + urlencode({'secret-key':key}) if p=='sif' else '')
            chunks.append('\n[mcp_servers.'+spec['server']+']\nurl = '+json.dumps(url)+'\nhttp_headers = { "secret-key" = '+json.dumps(key)+' }\n')
        merged=original.decode('utf-8').rstrip()+'\n'+''.join(chunks)
        try:tomllib.loads(merged)
        except tomllib.TOMLDecodeError:raise Error('合并配置无法解析，未写入') from None
        current,current_info=_read(path)
        require(current==original and (current_info is None)==(info is None),'配置已被其他程序修改，停止且不覆盖')
        if info is not None:require((info.st_ino,info.st_mtime_ns)==(current_info.st_ino,current_info.st_mtime_ns),'配置已变更，停止且不覆盖')
        if info is not None:
            # Backup may contain existing secrets: exclusive creation and mode0600.
            backup=path.with_name(path.name+'.aee-backup-'+str(__import__('time').time_ns()))
            fd=os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'wb') as f:f.write(original);f.flush();os.fsync(f.fileno())
        fd,temp=tempfile.mkstemp(prefix='.aee-mcp-',dir=path.parent)
        with os.fdopen(fd,'wb') as f:f.write(merged.encode('utf-8'));f.flush();os.fsync(f.fileno())
        # Recheck after writing the private temporary file; the lock only
        # coordinates this helper, so users must not edit Codex config concurrently.
        latest,latest_info=_read(path)
        require(latest==original and (latest_info is None)==(info is None),'配置已被其他程序修改，停止且不覆盖')
        if info is not None:require((info.st_ino,info.st_mtime_ns)==(latest_info.st_ino,latest_info.st_mtime_ns),'配置已变更，停止且不覆盖')
        os.replace(temp,path);temp=None
        return {'status':'configured','providers':selected,'config':str(path),'permissions':'0600',
                'backup_created':info is not None,'network_calls':False,'live_connection':'pending_client_reload',
                'next':'重开 Codex 对话，先发现工具目录；未经本次任务授权不调用消耗额度的业务查询。不要分享完整 MCP 配置/URL。'}
    finally:
        if temp is not None:Path(temp).unlink(missing_ok=True)
        os.close(lockfd);lock.unlink(missing_ok=True)
