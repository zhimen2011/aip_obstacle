"""文件哈希工具。用于 SQLite 里的 source_files.file_hash 去重。"""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_of_file(path: str | Path, chunk_size: int = 65536) -> str:
    """按块读文件算 sha256，避免一次读大文件。"""
    p = Path(path)
    h = hashlib.sha256()
    with p.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def sha256_of_text(text: str) -> str:
    """对字符串内容算 sha256（parse_text 路径用）。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
