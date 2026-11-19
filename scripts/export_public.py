"""Allowlist-only source export. Never copy a working tree wholesale."""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TOP={'README.md','LICENSE','THIRD_PARTY_NOTICES.txt','.gitignore','pyproject.toml','AGENTS.md'}

def allowed(p):
    rel=p.relative_to(ROOT);parts=rel.parts
    if p.is_symlink() or '__pycache__' in parts:return False
    if len(parts)==1:return p.name in TOP
    if parts[0]=='aee':return len(parts)==2 and p.suffix in ('.py','.sql')
    if parts[0]=='skills':return p.name in ('SKILL.md','openai.yaml','run.py') or ('references'in parts and p.suffix=='.md')
    if parts[0]=='tests':return len(parts)==2 and p.name.startswith('test_') and p.suffix=='.py'
    if parts[0]=='docs':return len(parts)==2 and p.suffix in ('.md','.html')
    if parts[0]=='examples':return p.suffix in ('.json','.csv') and len(parts)<=3
    if parts[0]=='scripts':return len(parts)==2 and p.name=='export_public.py'
    return False

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    output=Path(args.output).resolve()
    if output.exists() or output.is_relative_to(ROOT):raise SystemExit('输出必须为源目录外的新目录')
    files=sorted(p for p in ROOT.rglob('*') if p.is_file() and allowed(p))
    # Patterns intentionally describe classes, never embed private account IDs.
    patterns=['/'+'Users/'+r'[^/\s]+/',r'192\.168\.\d+\.\d+',r'-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----',r'(?i)(?:app_secret|access_token|session_cookie)\s*[:=]\s*["\'][A-Za-z0-9_-]{16,}']
    for path in files:
        content=path.read_text(encoding='utf-8')
        if any(re.search(pattern,content) for pattern in patterns):raise SystemExit('隐私规则命中：'+str(path.relative_to(ROOT)))
    output.mkdir(parents=True,mode=0o755)
    entries=[]
    for path in files:
        rel=path.relative_to(ROOT);dest=output/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
        blob=dest.read_bytes();entries.append({'path':rel.as_posix(),'bytes':len(blob),'sha256':hashlib.sha256(blob).hexdigest()})
    (output/'PUBLIC_MANIFEST.json').write_text(json.dumps({'version':'0.1.0','files':entries,'scan':'allowlist and generic secret/private-path scan passed; human release review still required'},ensure_ascii=False,indent=2))
    print(json.dumps({'files':len(entries),'output':str(output),'published':False},ensure_ascii=False))

if __name__=='__main__':main()
