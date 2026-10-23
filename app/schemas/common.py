"""统一响应模型：所有接口返回 {code, message, data} 结构。"""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

SUCCESS_CODE = 0


class ApiResponse(BaseModel, Generic[T]):
    """统一响应包装。code 为 0 表示成功，非 0 表示业务失败。"""

    code: int = Field(default=SUCCESS_CODE, description="业务码，0 表示成功")
    message: str = Field(default="success", description="提示信息")
    data: T | None = Field(default=None, description="业务数据")


def ok(data: Any = None, message: str = "success") -> ApiResponse[Any]:
    """构造成功响应。"""
    return ApiResponse(code=SUCCESS_CODE, message=message, data=data)
