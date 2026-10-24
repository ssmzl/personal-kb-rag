"""登录鉴权业务逻辑：密码哈希、JWT 签发/解析、初始管理员写入。"""

import logging
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory
from app.exceptions import BizException
from app.models.user import User

logger = logging.getLogger(__name__)

JWT_ALGORITHM = "HS256"


def hash_password(plain_password: str) -> str:
    """使用 bcrypt 生成密码哈希。"""
    password_bytes = plain_password.encode("utf-8")
    if len(password_bytes) > 72:
        # bcrypt 仅使用前 72 字节，显式截断避免校验行为不一致
        password_bytes = password_bytes[:72]
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """校验明文密码与 bcrypt 哈希是否匹配，任何异常均视为不匹配。"""
    password_bytes = plain_password.encode("utf-8")
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]
    try:
        return bcrypt.checkpw(password_bytes, password_hash.encode("utf-8"))
    except ValueError:
        logger.warning("密码哈希格式非法，按校验失败处理")
        return False


def create_access_token(user: User) -> tuple[str, int]:
    """签发 JWT，返回 (token, 有效期秒数)。未配置 JWT_SECRET 时抛业务异常。"""
    if not settings.jwt_secret:
        raise BizException("登录鉴权未配置，请设置 JWT_SECRET 环境变量")

    expires_in = settings.jwt_expire_minutes * 60
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)
    return token, expires_in


def decode_access_token(token: str) -> dict:
    """解析并校验 JWT，非法/过期 token 抛 401 业务异常。"""
    if not settings.jwt_secret:
        raise BizException(
            "登录鉴权未配置，请设置 JWT_SECRET 环境变量",
            code=40100,
            http_status=401,
        )
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise BizException("登录已过期，请重新登录", code=40100, http_status=401) from exc
    except jwt.InvalidTokenError as exc:
        raise BizException("未登录或登录已失效", code=40100, http_status=401) from exc

    user_id = payload.get("sub")
    if not user_id:
        raise BizException("未登录或登录已失效", code=40100, http_status=401)
    return payload


async def authenticate_user(session: AsyncSession, username: str, password: str) -> User:
    """校验账号密码，失败统一抛业务异常（不区分账号不存在/密码错误，避免枚举账号）。"""
    stmt = select(User).where(User.username == username)
    user = (await session.execute(stmt)).scalar_one_or_none()

    if user is None or not verify_password(password, user.password_hash):
        logger.info("登录失败：username=%s", username)
        raise BizException("账号或密码错误", code=40001)

    return user


async def ensure_initial_admin() -> None:
    """首次启动时按环境变量写入初始管理员账号（已存在则跳过）。"""
    username = settings.initial_admin_username.strip()
    password = settings.initial_admin_password
    if not username or not password:
        logger.warning(
            "未配置 INITIAL_ADMIN_USERNAME / INITIAL_ADMIN_PASSWORD，跳过初始账号写入"
        )
        return
    if async_session_factory is None:
        logger.warning("数据库未就绪，跳过初始账号写入")
        return

    async with async_session_factory() as session:
        stmt = select(User).where(User.username == username)
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            logger.info("初始管理员已存在，跳过写入：username=%s", username)
            return

        session.add(User(username=username, password_hash=hash_password(password)))
        await session.commit()
        logger.info("初始管理员已写入：username=%s", username)
