"""Discover worksheet names without printing business rows or changing files."""
import io
from pathlib import Path
from .bounded import read_bounded
from .common import Error,require

def sheets(path):
    path=Path(path);require(path.suffix.lower()=='.xlsx','inspect-workbook 仅支持原生 XLSX')
    blob=read_bounded(path)
    try:import openpyxl
    except ImportError as exc:raise Error('XLSX 需要可选 openpyxl 依赖') from exc
    book=openpyxl.load_workbook(io.BytesIO(blob),read_only=True,data_only=False,keep_links=False)
    try:
        require(len(book.worksheets)<=32,'XLSX 超过32个工作表限制')
        return {'sheets':[s.title for s in book.worksheets],
                'notice':'仅枚举工作表名；用 inspect --sheet 明确核对实际表头和行数，不相信未验证的声明范围。'}
    finally:book.close()
