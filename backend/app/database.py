"""数据库连接与会话管理（同步 SQLAlchemy + SQLite）。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from fastapi import Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


def _apply_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    """每个新连接都启用外键约束并设置并发安全相关参数。"""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        # WAL 提升读写并发；对非 SQLite 文件（如内存库）设置失败也不影响使用
        cursor.execute("PRAGMA journal_mode=WAL")
    finally:
        cursor.close()


def create_db_engine(db_path: Path) -> Engine:
    """创建指向指定 SQLite 文件的引擎（自动创建父目录）。"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _apply_sqlite_pragmas)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def apply_schema_migrations(engine: Engine) -> None:
    """为旧版数据库补充新增字段。

    SQLite 的 create_all 不会给已存在的表加列，因此这里做幂等检查。
    新库由 create_all 直接按最新模型建表，本函数不会做任何修改。
    """
    with engine.begin() as connection:
        columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(stories)")
        }
        if columns and "art_style_id" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE stories ADD COLUMN art_style_id VARCHAR(64)"
            )
        # 知乎推广信息：原文标题 / 原文 ID / 搜索别名
        if columns and "zhihu_title" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE stories ADD COLUMN zhihu_title VARCHAR(300) "
                "NOT NULL DEFAULT ''"
            )
        if columns and "zhihu_article_id" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE stories ADD COLUMN zhihu_article_id VARCHAR(64) "
                "NOT NULL DEFAULT ''"
            )
        if columns and "zhihu_alias" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE stories ADD COLUMN zhihu_alias VARCHAR(8) "
                "NOT NULL DEFAULT ''"
            )
        if columns and "zhihu_aliases" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE stories ADD COLUMN zhihu_aliases JSON"
            )

        # AI 改动解读的持久化缓存（原文 / 优化文未变时不再调用模型）
        breakdown_columns = {
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(story_breakdowns)"
            )
        }
        if breakdown_columns and "analysis_cache" not in breakdown_columns:
            connection.exec_driver_sql(
                "ALTER TABLE story_breakdowns ADD COLUMN analysis_cache JSON"
            )
        if (
            breakdown_columns
            and "analysis_input_hash" not in breakdown_columns
        ):
            connection.exec_driver_sql(
                "ALTER TABLE story_breakdowns ADD COLUMN analysis_input_hash VARCHAR(64)"
            )
        # 两步拆解的分镜对照表：第一步写 mapping，第二步据此生成 pages
        if breakdown_columns and "mapping" not in breakdown_columns:
            connection.exec_driver_sql(
                "ALTER TABLE story_breakdowns ADD COLUMN mapping JSON"
            )
        # 章节发布分组：封面 + 正文 + 引导卡
        if breakdown_columns and "chapters" not in breakdown_columns:
            connection.exec_driver_sql(
                "ALTER TABLE story_breakdowns ADD COLUMN chapters JSON"
            )


def get_db(request: Request) -> Iterator[Session]:
    """FastAPI 依赖：每个请求独立 Session，结束时关闭。

    不自动 commit，事务边界由各路由显式控制。
    """
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
