"""数据库连接、会话与初始化。

- 异步引擎使用 asyncpg 驱动；
- 启动时执行 ``scripts/schema.sql``（幂等），确保扩展与六张表就绪；
- 未配置 ``DATABASE_URL`` 时跳过初始化并给出警告，健康检查等无库接口仍可用。
"""

import logging
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)

# 建库脚本路径（仓库根目录 scripts/schema.sql）
SCHEMA_FILE = Path(__file__).resolve().parent.parent / "scripts" / "schema.sql"


class Base(DeclarativeBase):
    """ORM 声明式基类。"""


engine: AsyncEngine | None = (
    create_async_engine(settings.database_url, echo=settings.debug, pool_pre_ping=True)
    if settings.database_url
    else None
)

async_session_factory: async_sessionmaker[AsyncSession] | None = (
    async_sessionmaker(engine, expire_on_commit=False) if engine is not None else None
)


async def init_database() -> None:
    """执行建库脚本，创建扩展、表与索引（可重复执行）。"""
    if engine is None:
        logger.warning("未配置 DATABASE_URL，跳过数据库初始化")
        return

    try:
        schema_sql = SCHEMA_FILE.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"读取建库脚本失败：{SCHEMA_FILE}") from exc

    async with engine.begin() as conn:
        # asyncpg 的预处理语句一次只允许一条命令，建库脚本含多条语句，
        # 这里走底层驱动的简单查询协议整体执行。
        raw_connection = await conn.get_raw_connection()
        await raw_connection.driver_connection.execute(schema_sql)

    logger.info("数据库初始化完成：已执行 %s", SCHEMA_FILE)


async def close_database() -> None:
    """释放连接池。"""
    if engine is not None:
        await engine.dispose()
        logger.info("数据库连接池已释放")


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：提供请求级异步会话，异常时回滚。"""
    if async_session_factory is None:
        raise RuntimeError("未配置 DATABASE_URL，无法创建数据库会话")

    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
