"""登录鉴权相关 Pydantic 模型。"""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """登录请求体。"""

    username: str = Field(min_length=1, max_length=64, description="账号")
    password: str = Field(min_length=1, max_length=128, description="密码")


class LoginData(BaseModel):
    """登录成功返回的数据。"""

    token: str = Field(description="JWT 访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型")
    expires_in: int = Field(description="有效期（秒）")
    username: str = Field(description="账号")


class CurrentUserData(BaseModel):
    """当前登录用户信息。"""

    id: int = Field(description="用户 ID")
    username: str = Field(description="账号")
