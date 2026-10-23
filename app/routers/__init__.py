"""路由层：只做参数校验与 service 调用，统一挂载在 /api 前缀下。"""

from fastapi import APIRouter

from app.routers import health

api_router = APIRouter()
api_router.include_router(health.router)
