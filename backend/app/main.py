"""
后端总入口。

浏览器访问的接口、统一报错格式、跨域（CORS）都在这里挂上。
启动时会检查生产环境配置是否安全，并尝试写入开发用 demo 账号。
"""

import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import AppError, error_response
from app.core.logging import setup_logging
from app.db.seed import seed_dev_data
from app.db.session import SessionLocal

setup_logging()
logger = logging.getLogger(__name__)


async def lifespan(app: FastAPI):
    """程序启动和关闭时跑一次：先做安全检查，再尝试灌开发数据。"""
    settings.assert_safe_for_env()
    try:
        async with SessionLocal() as session:
            await seed_dev_data(session)
    except Exception:
        logger.warning(
            "开发种子数据未写入：数据库尚未就绪，请先启动 postgres 并执行 alembic upgrade head",
            exc_info=True,
        )
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """给每次请求发一个编号，方便日志里把同一次操作串起来。"""
    rid = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = rid
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """业务错误（未登录、没权限等）。"""
    return error_response(request, exc.code, exc.message, exc.http_status, exc.data)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """请求参数类型/长度不对。"""
    return error_response(request, 40022, "参数校验失败", 422, exc.errors())


@app.exception_handler(StarletteHTTPException)
async def http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """框架自带的 404/401 等，映射到我们的业务码。"""
    code = 40004 if exc.status_code == 404 else 50001
    if exc.status_code == 401:
        code = 40001
    if exc.status_code == 403:
        code = 40003
    return error_response(request, code, str(exc.detail), exc.status_code)


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    """没预料到的异常：记日志，对外只说内部错误，避免泄露堆栈。"""
    logger.exception("unhandled")
    return error_response(request, 50001, "内部错误", 500)


app.include_router(api_router, prefix="/api/v1")
