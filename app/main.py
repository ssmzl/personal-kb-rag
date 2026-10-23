"""FastAPI 应用入口。"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401  # 导入以注册全部 ORM 模型
from app.config import settings
from app.database import close_database, init_database
from app.exceptions import register_exception_handlers
from app.routers import api_router

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """应用生命周期：启动时执行建库脚本，关闭时释放连接池。"""
    await init_database()
    yield
    await close_database()


def create_app() -> FastAPI:
    """创建并装配 FastAPI 应用。"""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="个人知识库 RAG 后端服务",
        lifespan=lifespan,
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)

    if not settings.dashscope_api_key:
        logger.warning("未配置 DASHSCOPE_API_KEY，AI 相关接口将返回友好提示")

    return app


app = create_app()
