"""Bound bytes before parsing and ZIP expansion before opening XLSX."""
import io
import zipfile
from pathlib import Path
from .common import require

MAX_BYTES=20*1024*1024
MAX_ROWS=100000

def read_bounded(path):
    path=Path(path)
    require(path.stat().st_size<=MAX_BYTES,'首版单文件最大20MiB')
    with path.open('rb') as f:blob=f.read(MAX_BYTES+1)
    require(len(blob)<=MAX_BYTES,'文件读取期间超过20MiB限制')
    if path.suffix.lower()=='.xlsx':
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            entries=archive.infolist()
            require(len(entries)<=512,'XLSX 内部文件数超过限制')
            require(sum(i.file_size for i in entries)<=100*1024*1024,'XLSX 解压总量超过100MiB限制')
            require(all(i.file_size<=50*1024*1024 for i in entries),'XLSX 单项解压超过50MiB限制')
    return blob
