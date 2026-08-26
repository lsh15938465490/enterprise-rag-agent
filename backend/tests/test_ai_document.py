from app.api.v1.ai_docs import _safe_md_name
from app.services.ai_document import GENERATE_DOC_SYSTEM, build_generate_prompt


def test_prompt_includes_title_requirements_and_sources():
    text = build_generate_prompt(
        "请假SOP",
        "写一份请假流程",
        [{"filename": "制度.pdf", "page": 2, "heading": "请假", "content": "需提前一天申请。"}],
    )
    assert "文档标题：请假SOP" in text
    assert "内容要求：写一份请假流程" in text
    assert "[S1] 来源:制度.pdf 页:2" in text
    assert "需提前一天申请。" in text
    assert "文档概述" in GENERATE_DOC_SYSTEM
    assert "引用来源" in GENERATE_DOC_SYSTEM


def test_empty_kb_prompt_is_cold_start():
    text = build_generate_prompt("周报", "本周进展", [])
    assert "（无）" in text
    assert "冷启动" in text


def test_safe_md_name():
    assert _safe_md_name("请假流程").endswith(".md")
    assert _safe_md_name("说明.md") == "说明.md"
