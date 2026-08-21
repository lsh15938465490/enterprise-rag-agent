"""RRF 融合：两边都出现的文档 id 应该排更前。"""

from app.services.rrf import rrf
from uuid import uuid4


def test_rrf_empty():
    assert rrf([], []) == []


def test_rrf_single_list():
    x = uuid4()
    fused = rrf([(x, 1.0)], [])
    assert fused[0][0] == x
    assert fused[0][1] == 1 / 61
