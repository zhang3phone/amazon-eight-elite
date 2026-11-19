from pathlib import Path
import json,sys
p=Path(__file__).resolve()
root=next((x for x in p.parents if (x/'aee'/'cli.py').is_file()),None)
if root is None:
    f=p.parent/'runtime.json'
    if not f.is_file():raise SystemExit('请先在工具项目执行 install-skills，或从完整发行目录调用')
    root=Path(json.loads(f.read_text())['project_root'])
if not (root/'aee'/'cli.py').is_file():raise SystemExit('本地工具目录已移动，请重新安装技能映射')
sys.path.insert(0,str(root))
from aee.cli import main
raise SystemExit(main())
