"""登录鉴权路由。"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.auth import CurrentUserData, LoginData, LoginRequest
from app.schemas.common import ApiResponse, ok
from app.services.auth_service import authenticate_user, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=ApiResponse[LoginData], summary="账号密码登录")
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[LoginData]:
    """校验账号密码，成功签发 JWT；失败返回统一错误体（不区分账号/密码错误）。"""
    user = await authenticate_user(session, body.username, body.password)
    token, expires_in = create_access_token(user)
    return ok(
        LoginData(
            token=token,
            expires_in=expires_in,
            username=user.username,
        ),
        message="登录成功",
    )


@router.get("/me", response_model=ApiResponse[CurrentUserData], summary="获取当前登录用户")
async def get_me(
    current_user: User = Depends(get_current_user),
) -> ApiResponse[CurrentUserData]:
    """受保护接口示例：校验 token 并返回当前用户信息。"""
    return ok(CurrentUserData(id=current_user.id, username=current_user.username))
