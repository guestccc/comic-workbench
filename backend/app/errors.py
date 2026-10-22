"""统一错误结构与全局异常处理。

所有接口错误统一返回：{"detail": "中文消息", "code": "MACHINE_CODE"}
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("comic_workbench")


class AppError(Exception):
    """业务异常：携带 HTTP 状态码、中文提示与机器可读错误码。"""

    def __init__(self, status_code: int, message: str, code: str = "APP_ERROR") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.code = code


def error_response(status_code: int, message: str, code: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": message, "code": code},
    )


def _format_validation_error(exc: RequestValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "请求参数校验失败"
    first = errors[0]
    location = ".".join(
        str(part) for part in first.get("loc", ()) if part not in ("body", "query", "path")
    )
    message = str(first.get("msg", "参数不合法"))
    # Pydantic 自定义 ValueError 会带 "Value error, " 前缀
    if message.startswith("Value error, "):
        message = message[len("Value error, ") :]
    return f"请求参数校验失败：{location or '参数'} {message}".strip()


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器，保证任何异常都以中文 JSON 返回。"""

    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.status_code, exc.message, exc.code)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(422, _format_validation_error(exc), "VALIDATION_ERROR")

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "请求处理失败"
        if exc.status_code == 404:
            message = message or "资源不存在"
        return error_response(exc.status_code, message, "HTTP_ERROR")

    @app.exception_handler(IntegrityError)
    async def handle_integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning("数据库约束冲突: %s", exc.orig)
        return error_response(409, "数据冲突，请检查关联数据后重试", "INTEGRITY_ERROR")

    @app.exception_handler(OperationalError)
    async def handle_operational_error(_: Request, exc: OperationalError) -> JSONResponse:
        logger.error("数据库操作失败: %s", exc.orig)
        return error_response(503, "数据库繁忙，请稍后重试", "DATABASE_BUSY")

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # 记录完整堆栈便于排查，但不向前端泄露内部细节
        logger.exception("未处理异常: %s %s", request.method, request.url.path)
        return error_response(500, "服务器内部错误，请稍后重试", "INTERNAL_ERROR")
