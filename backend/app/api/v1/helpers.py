"""成功响应的快捷写法：ok() 包一层信封；page_data() 给分页列表用。"""

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.exceptions import envelope, get_request_id


def ok(request: Request, data: Any = None, status_code: int = 200) -> JSONResponse:
    """成功时的统一返回。data 里才是真正业务内容。"""
    return JSONResponse(
        status_code=status_code,
        content=envelope(data=data, request_id=get_request_id(request)),
    )


def page_data(items: list[Any], total: int, page: int, page_size: int) -> dict[str, Any]:
    """列表接口的分页结构：这一页的 items + 总共多少条。"""
    return {"items": items, "total": total, "page": page, "page_size": page_size}
