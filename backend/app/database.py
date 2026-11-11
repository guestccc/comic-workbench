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
        # 知乎推广信息：原文 ID / 搜索别名；原名标题直接使用故事名
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
        if columns and "sensitive_edit" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE stories ADD COLUMN sensitive_edit JSON"
            )
        # 小红书发布设置（故事级）：合集名、内容声明与来源媒体名
        if columns and "xhs_collection" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE stories ADD COLUMN xhs_collection VARCHAR(64) "
                "NOT NULL DEFAULT ''"
            )
        # 声明由布尔开关升级为平台选项文案；旧库按原开关语义回填
        if columns and "xhs_declaration" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE stories ADD COLUMN xhs_declaration VARCHAR(32) "
                "NOT NULL DEFAULT '笔记含AI合成内容'"
            )
            if "xhs_ai_declaration" in columns:
                # 用户关掉过声明的故事迁移为「不声明」，其余保持默认文案
                connection.exec_driver_sql(
                    "UPDATE stories SET xhs_declaration = '' "
                    "WHERE xhs_ai_declaration = 0"
                )
        if columns and "xhs_repost_source" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE stories ADD COLUMN xhs_repost_source VARCHAR(64) "
                "NOT NULL DEFAULT ''"
            )
        # 旧开关已由 xhs_declaration 取代，避免留下第二个可编辑源
        if columns and "xhs_ai_declaration" in columns:
            connection.exec_driver_sql(
                "ALTER TABLE stories DROP COLUMN xhs_ai_declaration"
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

        # 设计建议升级为通用规则：渲染提示词时自动追加【设计规则】
        feedback_columns = {
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(design_feedbacks)"
            )
        }
        if feedback_columns and "is_rule" not in feedback_columns:
            connection.exec_driver_sql(
                "ALTER TABLE design_feedbacks ADD COLUMN is_rule "
                "BOOLEAN NOT NULL DEFAULT 0"
            )
        if feedback_columns and "rule_text" not in feedback_columns:
            connection.exec_driver_sql(
                "ALTER TABLE design_feedbacks ADD COLUMN rule_text "
                "TEXT NOT NULL DEFAULT ''"
            )
        if feedback_columns and "rule_target" not in feedback_columns:
            connection.exec_driver_sql(
                "ALTER TABLE design_feedbacks ADD COLUMN rule_target "
                "VARCHAR(20) NOT NULL DEFAULT 'cover'"
            )
        if feedback_columns and "rule_promoted_at" not in feedback_columns:
            connection.exec_driver_sql(
                "ALTER TABLE design_feedbacks ADD COLUMN rule_promoted_at DATETIME"
            )

        rule_columns = {
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(design_rules)"
            )
        }
        if rule_columns and "template_applied_at" not in rule_columns:
            connection.exec_driver_sql(
                "ALTER TABLE design_rules ADD COLUMN template_applied_at DATETIME"
            )

        # 章节发文配置增加发布标签（全局预设标签只是候选项）
        chapter_post_columns = {
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(story_chapter_post_configs)"
            )
        }
        if chapter_post_columns and "tags" not in chapter_post_columns:
            connection.exec_driver_sql(
                "ALTER TABLE story_chapter_post_configs "
                "ADD COLUMN tags JSON NOT NULL DEFAULT '[]'"
            )

        # 提示词快照增加规则硬检查结果
        snapshot_columns = {
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(prompt_render_snapshots)"
            )
        }
        if snapshot_columns and "rule_checks" not in snapshot_columns:
            connection.exec_driver_sql(
                "ALTER TABLE prompt_render_snapshots ADD COLUMN rule_checks JSON"
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
