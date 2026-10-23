"""健康检查相关数据模型。"""

from pydantic import BaseModel


class HealthData(BaseModel):
    """健康检查返回数据。"""

    status: str
    app: str
    version: str
