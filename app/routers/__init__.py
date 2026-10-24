"""路由层：只做参数校验与 service 调用，统一挂载在 /api 前缀下。"""

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.routers import auth, chat, documents, health, knowledge_base

api_router = APIRouter()

# 公开路由：健康检查（供部署探活）与登录
api_router.include_router(health.router)
api_router.include_router(auth.router)

# 受保护路由：除登录/健康检查外的业务接口统一挂载到本路由，强制 JWT 鉴权
protected_router = APIRouter(dependencies=[Depends(get_current_user)])
protected_router.include_router(knowledge_base.router)
protected_router.include_router(documents.router)
protected_router.include_router(chat.router)

api_router.include_router(protected_router)
