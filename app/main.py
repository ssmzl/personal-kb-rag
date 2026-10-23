"""FastAPI 应用入口。"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.exceptions import register_exception_handlers
from app.routers import api_router

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """创建并装配 FastAPI 应用。"""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="个人知识库 RAG 后端服务",
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

    if not settings.database_url:
        logger.warning("未配置 DATABASE_URL，数据库相关接口将在后续任务中不可用")
    if not settings.dashscope_api_key:
        logger.warning("未配置 DASHSCOPE_API_KEY，AI 相关接口将返回友好提示")

    return app


app = create_app()
