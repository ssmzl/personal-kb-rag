"""业务异常与全局异常处理。

约定：
- 业务错误抛 ``BizException``，由全局处理器转为统一 ``{code, message, data}`` 响应；
- 鉴权失败使用 HTTP 401，便于前端拦截并跳转登录页；
- 未捕获异常记录完整堆栈后返回统一 500 响应，不向前端泄漏内部细节。
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class BizException(Exception):
    """业务异常。"""

    def __init__(self, message: str, code: int = 40000, http_status: int = 200) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.http_status = http_status


def _error_response(
    code: int,
    message: str,
    http_status: int,
    data: Any = None,
) -> JSONResponse:
    """构造统一错误响应。"""
    return JSONResponse(
        status_code=http_status,
        content={"code": code, "message": message, "data": data},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器。"""

    @app.exception_handler(BizException)
    async def handle_biz_exception(request: Request, exc: BizException) -> JSONResponse:
        logger.warning(
            "业务异常：method=%s path=%s code=%s message=%s",
            request.method,
            request.url.path,
            exc.code,
            exc.message,
        )
        return _error_response(exc.code, exc.message, exc.http_status)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        logger.warning(
            "参数校验失败：method=%s path=%s errors=%s",
            request.method,
            request.url.path,
            exc.errors(),
        )
        return _error_response(42200, "请求参数校验失败", 422, jsonable_encoder(exc.errors()))

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "请求失败"
        logger.warning(
            "HTTP 异常：method=%s path=%s status=%s message=%s",
            request.method,
            request.url.path,
            exc.status_code,
            message,
        )
        return _error_response(exc.status_code, message, exc.status_code)

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "未捕获异常：method=%s path=%s error_type=%s",
            request.method,
            request.url.path,
            type(exc).__name__,
        )
        return _error_response(500, "服务器内部错误", 500)
