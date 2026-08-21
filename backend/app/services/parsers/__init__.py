"""按后缀把 PDF / Word / 纯文本读成一段段文字。读不出字会报 EMPTY_TEXT。"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ParsedBlock:
    content: str
    page_number: int | None
    heading: str | None


def parse_file(path: Path, content_type: str, filename: str) -> list[ParsedBlock]:
    """根据后缀选择解析器。"""
    suffix = path.suffix.lower()
    if suffix == ".pdf" or "pdf" in content_type:
        return _parse_pdf(path)
    if suffix == ".docx" or "word" in content_type:
        return _parse_docx(path)
    return _parse_text(path)


def _parse_pdf(path: Path) -> list[ParsedBlock]:
    """一页一段。扫描件没有文字层会 EMPTY_TEXT。"""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    blocks: list[ParsedBlock] = []
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            blocks.append(ParsedBlock(content=text, page_number=i, heading=None))
    if not blocks:
        raise ValueError("EMPTY_TEXT")
    return blocks


def _parse_docx(path: Path) -> list[ParsedBlock]:
    """按段落读取。标题样式会记到 heading。表格内容当前不读。"""
    import docx

    document = docx.Document(str(path))
    heading: str | None = None
    blocks: list[ParsedBlock] = []
    buf: list[str] = []
    for para in document.paragraphs:
        style = (para.style.name or "") if para.style else ""
        text = (para.text or "").strip()
        if not text:
            continue
        if style.startswith("Heading"):
            if buf:
                blocks.append(ParsedBlock(content="\n".join(buf), page_number=None, heading=heading))
                buf = []
            heading = text[:512]
            continue
        buf.append(text)
    if buf:
        blocks.append(ParsedBlock(content="\n".join(buf), page_number=None, heading=heading))
    if not blocks:
        raise ValueError("EMPTY_TEXT")
    return blocks


def _parse_text(path: Path) -> list[ParsedBlock]:
    """txt/md：先试 utf-8，再试 gbk（国内常见编码）。"""
    raw = path.read_bytes()
    text = None
    for enc in ("utf-8", "gbk"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("EMPTY_TEXT")
    text = text.strip()
    if not text:
        raise ValueError("EMPTY_TEXT")
    return [ParsedBlock(content=text, page_number=None, heading=None)]
