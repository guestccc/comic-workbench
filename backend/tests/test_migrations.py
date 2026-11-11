"""数据库结构迁移测试：旧库启动时自动补充新增字段。"""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from app.database import apply_schema_migrations, create_db_engine
from app.main import create_app


def _create_old_stories_table(db_path) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE stories (
                id INTEGER NOT NULL,
                name VARCHAR(200) NOT NULL,
                content TEXT NOT NULL,
                cover_filename VARCHAR(64),
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                PRIMARY KEY (id)
            )
            """
        )
        connection.commit()
    finally:
        connection.close()


def _columns(engine) -> set[str]:
    with engine.connect() as connection:
        return {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(stories)")
        }


def test_migration_adds_art_style_id(tmp_path):
    db_path = tmp_path / "old.db"
    _create_old_stories_table(db_path)

    engine = create_db_engine(db_path)
    try:
        apply_schema_migrations(engine)
        assert "art_style_id" in _columns(engine)
        assert "sensitive_edit" in _columns(engine)
        assert "xhs_collection" in _columns(engine)
        assert "xhs_declaration" in _columns(engine)
        assert "xhs_repost_source" in _columns(engine)
        # 旧布尔开关已退役，迁移后不再保留
        assert "xhs_ai_declaration" not in _columns(engine)

        # 幂等：重复执行不报错
        apply_schema_migrations(engine)
        assert "art_style_id" in _columns(engine)
        assert "sensitive_edit" in _columns(engine)
        assert "xhs_collection" in _columns(engine)
        assert "xhs_declaration" in _columns(engine)
        assert "xhs_repost_source" in _columns(engine)
    finally:
        engine.dispose()


def test_migration_backfills_xiaohongshu_defaults(tmp_path):
    """旧故事补列后默认声明 AI 合成内容、不加入合集。"""
    db_path = tmp_path / "old.db"
    _create_old_stories_table(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "INSERT INTO stories (id, name, content, created_at, updated_at) "
            "VALUES (1, '旧故事', '正文', '2026-01-01', '2026-01-01')"
        )
        connection.commit()
    finally:
        connection.close()

    engine = create_db_engine(db_path)
    try:
        apply_schema_migrations(engine)
        with engine.connect() as conn:
            row = conn.exec_driver_sql(
                "SELECT xhs_collection, xhs_declaration, xhs_repost_source "
                "FROM stories WHERE id = 1"
            ).one()
        assert row[0] == ""
        assert row[1] == "笔记含AI合成内容"
        assert row[2] == ""
    finally:
        engine.dispose()


def test_migration_maps_ai_declaration_switch_to_text(tmp_path):
    """旧库的 AI 声明关掉后迁移为「不声明」，列随后删除。"""
    db_path = tmp_path / "old.db"
    _create_old_stories_table(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "ALTER TABLE stories ADD COLUMN xhs_ai_declaration BOOLEAN "
            "NOT NULL DEFAULT 1"
        )
        connection.executemany(
            "INSERT INTO stories (id, name, content, created_at, updated_at, "
            "xhs_ai_declaration) VALUES (?, ?, '正文', '2026-01-01', "
            "'2026-01-01', ?)",
            [(1, "关掉声明", 0), (2, "保持默认", 1)],
        )
        connection.commit()
    finally:
        connection.close()

    engine = create_db_engine(db_path)
    try:
        apply_schema_migrations(engine)
        with engine.connect() as conn:
            rows = conn.exec_driver_sql(
                "SELECT id, xhs_declaration FROM stories ORDER BY id"
            ).all()
        assert [tuple(row) for row in rows] == [
            (1, ""),
            (2, "笔记含AI合成内容"),
        ]
        assert "xhs_ai_declaration" not in _columns(engine)
    finally:
        engine.dispose()


def test_app_startup_migrates_old_database(app_settings):
    """旧库也能正常启动并读取故事列表。"""
    _create_old_stories_table(app_settings.db_path)

    with TestClient(create_app(app_settings)) as client:
        response = client.get("/api/stories")
        assert response.status_code == 200
        assert response.json() == []
