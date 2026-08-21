"""上传文件存到磁盘：安全文件名、读写路径、向量归一化。"""

import hashlib
import math
import re
from pathlib import Path

from app.core.config import settings

_SAFE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff._-]+")


def secure_filename(name: str) -> str:
    """去掉路径穿越和奇怪字符，只留下安全的文件名。"""
    name = Path(name).name
    cleaned = _SAFE.sub("_", name).strip("._")
    return cleaned or "file"


def save_bytes(tenant_id: str, kb_id: str, doc_id: str, filename: str, data: bytes) -> tuple[str, str]:
    """按 租户/知识库/文档id 分目录保存，返回相对路径和 sha256，便于以后校验文件是否被改。"""
    safe = secure_filename(filename)
    rel = f"{tenant_id}/{kb_id}/{doc_id}/{safe}"
    dest = Path(settings.UPLOAD_DIR) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    checksum = hashlib.sha256(data).hexdigest()
    return rel.replace("\\", "/"), checksum


def abs_path(storage_key: str) -> Path:
    """相对路径转成磁盘绝对路径。"""
    return Path(settings.UPLOAD_DIR) / storage_key


def delete_file(storage_key: str) -> None:
    """删除已上传文件；文件不存在就当成功。"""
    path = abs_path(storage_key)
    if path.exists():
        path.unlink()


def sha256_bytes(data: bytes) -> str:
    """算文件指纹。"""
    return hashlib.sha256(data).hexdigest()


def l2_normalize(vec: list[float]) -> list[float]:
    """把向量长度归一成 1，方便后面用余弦相似度比较「方向像不像」。"""
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]
