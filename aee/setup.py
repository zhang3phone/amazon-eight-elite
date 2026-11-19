import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from .common import Error,load,new_dir,require,write_new
from .store import Store,name

ROOT=Path(__file__).resolve().parents[1]

def doctor():
    import importlib.util
    return {'python':sys.version.split()[0],'platform':platform.system(),
       'commands':{k:bool(shutil.which(k)) for k in ('psql','initdb','pg_ctl','brew','docker')},
       'xlsx_available':importlib.util.find_spec('openpyxl') is not None,
       'native_computer_use':'must_be_checked_by_Codex','shop_access':'not_checked','changes':False}

def install_postgres(apply=False):
    # No shell, curl|sh, automatic service startup or changes to existing clusters.
    require(platform.system()=='Darwin' and shutil.which('brew'),'自动辅助安装首版支持已有 Homebrew 的 macOS；其他系统见 docs/INSTALL.md')
    command=['brew','install','postgresql@16']
    if not apply:return {'status':'planned','command':command,'service_autostart':False}
    require(not shutil.which('psql') and not shutil.which('initdb'),'已检测到 PostgreSQL 工具，不重复安装；先核实 PATH')
    result=subprocess.run(command,timeout=900,capture_output=True,text=True)
    require(result.returncode==0,'Homebrew 安装未成功；没有启动服务')
    return {'status':'installed','service_started':False,'next':'按安装提示配置 PATH，再运行 doctor 与 local-init'}

def local_init(root,database,confirmed,apply=False):
    database=name(database);require(database==confirmed,'--confirm-db 需与指定库名相同')
    root=Path(root).expanduser().resolve()
    require(not any(c in str(root) for c in ("'",'\n','\r','\x00')),'实例目录包含不支持的字符')
    for command in ('initdb','pg_ctl','psql'):require(shutil.which(command),f'缺少 {command}，请运行 doctor')
    require(os.name=='posix','首版本地隔离实例需要 POSIX 系统；Windows 采用已有本机 PostgreSQL 配置')
    # Socket pathname has a small OS-specific limit; fail before initialization.
    require(len(str(root/'socket'))<80,'Unix socket 路径过长，请用更短的本机路径')
    require(not root.exists(),'实例目录已存在，禁止重新初始化；使用 db-init 或核实后手动启动原实例')
    if not apply:return {'status':'planned','root':str(root),'database':database,'network':'Unix socket only, no TCP listener','authentication':'peer (local OS user)','services_changed':False}
    root=new_dir(root);socket=root/'socket';socket.mkdir(mode=0o700)
    env={k:v for k,v in os.environ.items() if not k.startswith('PG')}
    proc=subprocess.run(['initdb','-D',str(root/'pgdata'),'--encoding=UTF8','--no-locale','--auth-local=peer','--auth-host=reject'],env=env,capture_output=True,text=True,timeout=60)
    write_new(root/'initdb.log',proc.stdout+'\n'+proc.stderr)
    require(proc.returncode==0,'隔离初始化失败；保留目录供检查，不影响已有服务')
    options=f"-c listen_addresses='' -c unix_socket_directories='{socket}' -c unix_socket_permissions=0700"
    proc=subprocess.run(['pg_ctl','-D',str(root/'pgdata'),'-l',str(root/'postgres.log'),'-o',options,'-w','start'],env=env,capture_output=True,text=True,timeout=60)
    require(proc.returncode==0,'隔离服务启动失败；保留目录，未改变已有 PostgreSQL 服务')
    import getpass
    config={'host':str(socket),'port':5432,'user':name(getpass.getuser()),'database':database,'password_env':None}
    write_new(root/'db.json',config)
    store=Store(root/'db.json');store.create(database,True);store.init(database,True)
    write_new(root/'instance.json',{'format_version':1,'database':database,'pgdata':'pgdata','socket':'socket','managed_by':'amazon-eight-elite'})
    return {'status':'initialized','config':str(root/'db.json'),'database':database,'network':'Unix socket only','rollback':'local-stop --root '+str(root)+' (retains all files)'}

def local_stop(root,apply=False):
    root=Path(root).resolve();meta=load(root/'instance.json')
    require(meta.get('managed_by')=='amazon-eight-elite' and meta.get('pgdata')=='pgdata','不是本工具管理的隔离实例')
    if not apply:return {'status':'planned','action':'stop managed cluster; retain files'}
    p=subprocess.run(['pg_ctl','-D',str(root/'pgdata'),'-m','fast','-w','stop'],capture_output=True,text=True,timeout=60)
    require(p.returncode==0,'停止未成功；请核实实例状态，保留文件')
    return {'status':'stopped','files_retained':True}

def install_skills(target,apply=False):
    target=Path(target).expanduser().resolve();sources=sorted((ROOT/'skills').iterdir())
    require(len(sources)==9,'发行包需统一入口加八项专业技能')
    conflicts=[s.name for s in sources if (target/s.name).exists()]
    require(not conflicts,'目标技能已存在，停止且不覆盖：'+','.join(conflicts))
    if not apply:return {'status':'planned','target':str(target),'skills':[s.name for s in sources]}
    import tempfile
    target.mkdir(parents=True,exist_ok=True)
    created=[]
    with tempfile.TemporaryDirectory(prefix='.aee-install-',dir=target) as stage:
        for source in sources:
            dest=Path(stage)/source.name;shutil.copytree(source,dest)
            write_new(dest/'scripts/runtime.json',{'project_root':str(ROOT)})
        try:
            for source in sources:
                dest=target/source.name
                # mkdir is exclusive: never replace a destination created concurrently.
                dest.mkdir();created.append(dest)
                for item in (Path(stage)/source.name).iterdir():shutil.move(str(item),str(dest/item.name))
        except BaseException:
            for dest in reversed(created):shutil.rmtree(dest)
            raise
    return {'status':'installed','skills':len(sources),'runtime_must_remain':str(ROOT),
            'post_install_notice':'选品增强：卖家精灵和 SIF 已有官方 MCP。运行 python3 -m aee research-mcp-ui 预览；加 --apply 后在本机浏览器密码框填写自己的 MCP Key（也可使用 research-mcp 终端入口）。配置不等于连接验收；步骤见 docs/RESEARCH_MCP.md。'}
