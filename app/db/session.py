"""数据库会话管理：引擎 + 会话工厂。"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def _make_engine():
    url = get_settings().database_url
    # SQLite 需要允许跨线程访问（FastAPI 的请求可能在不同线程）
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    # 确保 SQLite 文件所在目录存在
    if url.startswith("sqlite:///"):
        db_path = url.replace("sqlite:///", "")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(url, connect_args=connect_args)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    """FastAPI 依赖：每个请求给一个独立会话，用完关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """建表（幂等，重复调用不会重复建），并补齐新增的列。"""
    from app.db import models  # noqa: F401  确保模型已注册

    from app.db.base import Base

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


def _add_missing_columns() -> None:
    """给已存在的表补上后加的列。

    SQLite 的 create_all 只会建新表，不会给旧表加列，所以这里手动补。
    真实项目用 Alembic 迁移，这里演示用轻量方案。
    """
    migrations = {
        "ledger_entries": {
            "attachment": "VARCHAR(200) DEFAULT ''",
            "counterparty_id": "INTEGER",
            "payment": "VARCHAR(20) DEFAULT '银行存款'",
            # 注意：status 故意不给 DEFAULT，这样老数据补列后是 NULL，
            # 才能区分出「这是迁移前的老数据」并统一置为已入账。
            "status": "VARCHAR(20)",
            "reject_reason": "VARCHAR(200) DEFAULT ''",
            "reviewed_at": "DATETIME",
        },
    }
    with engine.connect() as conn:
        for table, columns in migrations.items():
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            added_status = False
            for col, ddl in columns.items():
                if col not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
                    if col == "status":
                        added_status = True
            # 迁移前的老数据是"直接记账"的、没有审核概念，统一视为「已入账」，
            # 否则报表会突然全空——用户会以为数据丢了。
            if added_status:
                conn.exec_driver_sql(f"UPDATE {table} SET status = 'approved'")
            conn.commit()
