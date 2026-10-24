"""FastAPI 公共依赖：鉴权与请求级资源注入。"""

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.exceptions import BizException
from app.models.user import User
from app.services.auth_service import decode_access_token

BEARER_PREFIX = "Bearer "


async def get_current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db),
) -> User:
    """解析 Authorization Bearer Token，校验并返回当前登录用户。

    除公开路由（登录、健康检查）外，所有业务接口均应通过本依赖强制鉴权，
    校验失败统一抛 401，便于前端拦截后跳转登录页。
    """
    if not authorization or not authorization.startswith(BEARER_PREFIX):
        raise BizException("未登录或登录已失效", code=40100, http_status=401)

    token = authorization[len(BEARER_PREFIX):].strip()
    if not token:
        raise BizException("未登录或登录已失效", code=40100, http_status=401)

    payload = decode_access_token(token)
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise BizException("未登录或登录已失效", code=40100, http_status=401) from exc

    user = await session.get(User, user_id)
    if user is None:
        raise BizException("未登录或登录已失效", code=40100, http_status=401)
    return user
