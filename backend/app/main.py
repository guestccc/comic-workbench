"""FastAPI 应用工厂与入口。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import AppSettings
from .database import Base, create_db_engine, create_session_factory
from .errors import register_exception_handlers
from .routers import posts, settings, stories, uploads

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


def create_app(app_settings: AppSettings | None = None) -> FastAPI:
    """创建应用实例。

    通过注入 AppSettings 让测试使用临时数据库与上传目录，实现完全隔离。
    """
    app_settings = app_settings or AppSettings()

    engine = create_db_engine(app_settings.db_path)
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        app_settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        app_settings.upload_dir.mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(bind=engine)
        yield
        engine.dispose()

    app = FastAPI(
        title="条漫工作台 API",
        description="条漫生成管理：启动提示词、故事、发文",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.app_settings = app_settings
    app.state.engine = engine
    app.state.session_factory = session_factory

    register_exception_handlers(app)

    @app.middleware("http")
    async def add_security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/api/health", tags=["系统"])
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    # API 路由必须先于静态目录挂载注册
    app.include_router(settings.router)
    app.include_router(uploads.router)
    app.include_router(stories.router)
    app.include_router(posts.router)

    # 只对外挂载上传目录；check_dir=False 允许目录在 lifespan 中延迟创建
    app.mount(
        "/uploads",
        StaticFiles(directory=app_settings.upload_dir, check_dir=False),
        name="uploads",
    )

    # 生产模式：托管前端构建产物（HashRouter 无需 SPA fallback）
    if app_settings.frontend_dist.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=app_settings.frontend_dist, html=True),
            name="frontend",
        )

    return app


app = create_app()
