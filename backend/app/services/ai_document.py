"""把标题、内容要求和检索片段拼成文档生成提示词。"""

GENERATE_DOC_SYSTEM = """你是企业知识库文档撰写助手。根据用户给出的标题、内容要求以及【检索结果】撰写 Markdown 文档。
规则：
1. 输出结构必须包含四级标题：文档概述、核心章节、具体要点、引用来源。
2. 有检索结果时，关键事实必须标注 [S1][S2] 对应片段；文末「引用来源」列出编号、文件名与页码。
3. 无检索结果时（知识库冷启动），可基于通用职业规范撰写初稿，但必须在文首声明「当前知识库暂无参考片段，以下为 AI 初稿，需人工核对」，且不得伪造本企业制度条款、内部数据或未给出的数字。
4. 使用简体中文。不要输出与文档无关的寒暄。"""


def build_generate_prompt(title: str, requirements: str, contexts: list[dict]) -> str:
    """contexts 项含 filename / page / heading / content，编号对应 [S1]。"""
    lines = [
        f"文档标题：{title}",
        f"内容要求：{requirements}",
        "",
        "【检索结果】",
    ]
    if not contexts:
        lines.append("（无）知识库暂无可用参考片段，按冷启动规则撰写初稿。")
        return "\n".join(lines)
    for i, ctx in enumerate(contexts, start=1):
        lines.append(
            f"[S{i}] 来源:{ctx['filename']} 页:{ctx.get('page') or '-'} 标题:{ctx.get('heading') or '-'}"
        )
        lines.append(ctx["content"])
        lines.append("")
    return "\n".join(lines)
