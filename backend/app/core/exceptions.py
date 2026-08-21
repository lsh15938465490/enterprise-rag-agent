"""
接口统一返回格式：{ code, message, data, request_id }。

业务失败不要直接抛 Python 异常给用户，而是抛 AppError，这里会转成上面的 JSON。
"""

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """可预期的业务错误，例如未登录、没权限、资源不存在。"""
    def __init__(self, code: int, message: str, http_status: int = 400, data: Any = None) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status
        self.data = data
        super().__init__(message)


def envelope(
    *,
    code: int = 0,
    message: str = "ok",
    data: Any = None,
    request_id: str = "-",
) -> dict[str, Any]:
    """所有接口共用的 JSON 外壳。code=0 表示成功。"""
    return {"code": code, "message": message, "data": data, "request_id": request_id}


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


def error_response(request: Request, code: int, message: str, http_status: int, data: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=http_status,
        content=envelope(code=code, message=message, data=data, request_id=get_request_id(request)),
    )
