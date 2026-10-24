"""知识库相关 Pydantic 模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class KnowledgeBaseCreateRequest(BaseModel):
    """创建知识库请求体。"""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=128, description="知识库名称")


class KnowledgeBaseRenameRequest(BaseModel):
    """重命名知识库请求体。"""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=128, description="知识库新名称")


class KnowledgeBaseItem(BaseModel):
    """知识库列表项，含文档数聚合。"""

    id: int = Field(description="知识库 ID")
    name: str = Field(description="知识库名称")
    document_count: int = Field(description="库内文档数")
    create_time: datetime = Field(description="创建时间")
    update_time: datetime = Field(description="更新时间")

    @field_serializer("create_time", "update_time")
    def serialize_time(self, value: datetime) -> str:
        """时间统一输出 yyyy-MM-dd HH:mm:ss 格式字符串。"""
        return value.strftime(TIME_FORMAT)
