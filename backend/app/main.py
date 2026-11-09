"""FastAPI 应用工厂与入口。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, update

from .config import AppSettings
from .database import (
    Base,
    apply_schema_migrations,
    create_db_engine,
    create_session_factory,
)
from .errors import register_exception_handlers
from .models import DesignRuleCoverageRun, StoryBreakdown, utc_now
from .routers import (
    alias_stamp,
    breakdowns,
    design_feedbacks,
    design_rule_coverage,
    design_rules,
    image_generation,
    post_configs,
    posts,
    prompt_snapshots,
    sensitive_words,
    settings,
    stories,
    uploads,
)
from .services.design_rules import migrate_legacy_rules
from .services.files import organize_page_images

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
        apply_schema_migrations(engine)
        # 旧版 feedback.is_rule 迁移成结构化规则草案；重复执行安全
        with session_factory() as session:
            migrate_legacy_rules(session)
        # 服务重启时，上一进程未结束的覆盖检测没有 worker，标记为中断
        with session_factory() as session:
            session.execute(
                update(DesignRuleCoverageRun)
                .where(DesignRuleCoverageRun.status.in_(("queued", "running")))
                .values(
                    status="interrupted",
                    error_message="服务重启，检测任务已中断，请重新发起",
                    finished_at=utc_now(),
                )
            )
            session.commit()
        # 一次性把旧版平铺的成品图归入章节目录；重复执行安全
        with session_factory() as session:
            for breakdown in session.scalars(select(StoryBreakdown)).all():
                organize_page_images(
                    app_settings.upload_dir,
                    breakdown.story_id,
                    breakdown.pages or [],
                    breakdown.chapters or [],
                )
        yield
        engine.dispose()

    app = FastAPI(
        title="条漫工作台 API",
        description=(
            "条漫生成管理：启动提示词、故事、发文。\n\n"
            "## 生图回传\n"
            "生图 AI 可以把成品图直接回传，不需要手动上传。"
            "支持正文页、章节封面、章节引导卡：\n\n"
            "- 正文页批量：`POST /api/stories/{story_id}/breakdown/"
            "pages/images/ingest`（一次最多 20 张，逐项返回结果）\n"
            "- 正文页单张：`POST /api/stories/{story_id}/breakdown/"
            "pages/{page_number}/image/ingest`\n"
            "- 章节封面：`POST /api/stories/{story_id}/breakdown/"
            "chapters/{chapter_number}/cover/image/ingest`\n"
            "- 章节引导卡：`POST /api/stories/{story_id}/breakdown/"
            "chapters/{chapter_number}/guide/image/ingest`\n\n"
            "请求体二选一：`image_url`（后端主动下载，适合云端生图）"
            "或 `image_base64`（本地 agent 直接 POST）。"
            "正文页的 `page_number` 是全局页码，不是章内页码；"
            "支持的格式为 JPG / PNG / WebP，单张不超过 15MB，"
            "同一页重复回传会覆盖旧图。"
        ),
        version="0.1.0",
        lifespan=lifespan,
        openapi_tags=[
            {
                "name": "生图回传",
                "description": (
                    "生图 AI 回传成品图：图片 URL 或 base64，"
                    "写入正文页 / 章节封面 / 章节引导卡。"
                ),
            },
            {
                "name": "图片别名",
                "description": (
                    "原地给正文页 / 章节封面 / 引导卡底部加【别名】，"
                    "首次处理前自动备份原图，支持恢复。"
                ),
            },
        ],
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
    app.include_router(sensitive_words.router)
    app.include_router(uploads.router)
    app.include_router(stories.router)
    app.include_router(design_feedbacks.router)
    app.include_router(design_rules.router)
    app.include_router(design_rule_coverage.router)
    app.include_router(prompt_snapshots.router)
    app.include_router(breakdowns.router)
    app.include_router(breakdowns.ingest_router)
    app.include_router(image_generation.router)
    app.include_router(alias_stamp.router)
    app.include_router(post_configs.router)
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
