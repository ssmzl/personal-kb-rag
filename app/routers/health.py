"""健康检查路由。"""

from fastapi import APIRouter

from app.config import settings
from app.schemas.common import ApiResponse, ok
from app.schemas.health import HealthData

router = APIRouter(tags=["health"])


@router.get("/health", response_model=ApiResponse[HealthData], summary="健康检查")
async def health_check() -> ApiResponse[HealthData]:
    """返回服务基础信息，用于探活与部署健康检查。"""
    return ok(
        HealthData(
            status="ok",
            app=settings.app_name,
            version=settings.app_version,
        )
    )
