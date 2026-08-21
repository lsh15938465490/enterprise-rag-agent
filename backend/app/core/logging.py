"""把日志打成一行 JSON，方便以后收集。每条尽量带 request_id。"""

import logging
import sys
from typing import Any


class RequestIdFilter(logging.Filter):
    """给每条日志补 request_id 字段，没有就写 '-'。"""
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True


def setup_logging() -> None:
    """启动时调用一次，后面 print 风格的日志都会变成 JSON 行。"""
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    formatter = logging.Formatter(
        '{"level":"%(levelname)s","logger":"%(name)s","request_id":"%(request_id)s","message":"%(message)s"}'
    )
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
