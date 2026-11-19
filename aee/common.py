import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

class Error(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise Error(message)

def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)

def digest(value):
    return hashlib.sha256(value).hexdigest()

def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def now():
    return datetime.now(timezone.utc).isoformat()

def write_new(path, value):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:
        os.chmod(path,0o600)
        f.write(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False) if not isinstance(value,str) else value)

def new_dir(path):
    path=Path(path).resolve()
    path.mkdir(mode=0o700,parents=True,exist_ok=False)
    return path
