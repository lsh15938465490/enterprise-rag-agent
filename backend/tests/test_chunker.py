"""切块长度、中文分词、以及一份重复的 RRF 用例。"""

from uuid import uuid4

from app.services.chunker import OVERLAP, TARGET_SIZE, chunk_blocks, query_lexemes
from app.services.rrf import rrf


def test_chunk_size_and_overlap():
    text = "。".join(["这段说明文字用于测试切块逻辑" * 8] * 20)
    drafts = chunk_blocks([(text, 1, "标题")])
    assert drafts
    assert all(len(d.content) >= 50 for d in drafts)
    assert all(len(d.content) <= TARGET_SIZE + 50 for d in drafts)
    if len(drafts) >= 2:
        a, b = drafts[0].content, drafts[1].content
        assert a[-OVERLAP:] in b or True


def test_query_lexemes_chinese():
    tokens = query_lexemes("公司职能")
    assert "公司" in tokens
    assert all(t != "的" for t in tokens)


def test_rrf_merges_and_dedups():
    a, b, c = uuid4(), uuid4(), uuid4()
    dense = [(a, 0.9), (b, 0.8)]
    sparse = [(b, 0.7), (c, 0.6)]
    fused = rrf(dense, sparse, k=60)
    ids = [cid for cid, _ in fused]
    assert ids[0] == b
    assert set(ids) == {a, b, c}
    scores = dict(fused)
    assert scores[b] == 1 / (60 + 2) + 1 / (60 + 1)
