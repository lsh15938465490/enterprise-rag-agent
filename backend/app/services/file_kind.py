"""按文件头（魔数）识别真实类型，须与后缀一致。"""

from io import BytesIO
from zipfile import BadZipFile, ZipFile

from app.core.exceptions import AppError

ALLOWED_EXT = {".pdf", ".docx", ".txt", ".md"}

# 后缀允许对应的内容类型
_EXT_KIND = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "text",
    ".md": "text",
}


def suffix(filename: str) -> str:
    if "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()


def _is_docx(data: bytes) -> bool:
    """DOCX 是 ZIP，且包内有 Word 文档部件。xlsx/pptx 也是 PK 开头，不能只认 ZIP。"""
    if len(data) < 4 or data[:2] != b"PK":
        return False
    try:
        with ZipFile(BytesIO(data)) as zf:
            names = set(zf.namelist())
    except (BadZipFile, OSError, ValueError):
        return False
    return "word/document.xml" in names


def sniff_kind(data: bytes) -> str:
    """根据文件头判断内容类型：pdf / docx / zip / exe / ole / text。"""
    if not data:
        return "empty"
    if data.startswith(b"%PDF"):
        return "pdf"
    if data.startswith(b"PK"):
        return "docx" if _is_docx(data) else "zip"
    if data.startswith(b"MZ"):
        return "exe"
    if data.startswith(b"\xd0\xcf\x11\xe0"):
        return "ole"
    return "text"


def assert_kind_matches_name(filename: str, data: bytes) -> str:
    """后缀必须在白名单，且魔数与后缀一致。返回规范化后缀。"""
    ext = suffix(filename)
    expected = _EXT_KIND.get(ext)
    if expected is None:
        raise AppError(40022, "不支持的文件类型", 422)
    kind = sniff_kind(data)
    if kind != expected:
        raise AppError(40022, "文件内容与后缀不一致", 422)
    return ext
