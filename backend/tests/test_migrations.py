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

        # 幂等：重复执行不报错
        apply_schema_migrations(engine)
        assert "art_style_id" in _columns(engine)
    finally:
        engine.dispose()


def test_app_startup_migrates_old_database(app_settings):
    """旧库也能正常启动并读取故事列表。"""
    _create_old_stories_table(app_settings.db_path)

    with TestClient(create_app(app_settings)) as client:
        response = client.get("/api/stories")
        assert response.status_code == 200
        assert response.json() == []
