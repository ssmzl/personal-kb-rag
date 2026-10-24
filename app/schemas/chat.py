"""问答会话相关 Pydantic 模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class ChatSessionCreateRequest(BaseModel):
    """新建会话请求体。"""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, max_length=255, description="会话标题，缺省为「新对话」")


class ChatSessionRenameRequest(BaseModel):
    """重命名会话请求体。"""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=255, description="会话新标题")


class ChatAskRequest(BaseModel):
    """提问请求体。"""

    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=2000, description="用户问题")


class ChatSourceItem(BaseModel):
    """回答引用的资料来源：文档名 + 片段。"""

    document_id: int = Field(description="文档 ID")
    document_name: str = Field(description="文档名")
    chunk_index: int = Field(description="分块序号，从 0 开始")
    content: str = Field(description="引用的分块文本")


class ChatSessionItem(BaseModel):
    """会话列表项。"""

    id: int = Field(description="会话 ID")
    kb_id: int = Field(description="所属知识库 ID")
    title: str = Field(description="会话标题")
    create_time: datetime = Field(description="创建时间")
    update_time: datetime = Field(description="更新时间")

    @field_serializer("create_time", "update_time")
    def serialize_time(self, value: datetime) -> str:
        """时间统一输出 yyyy-MM-dd HH:mm:ss 格式字符串。"""
        return value.strftime(TIME_FORMAT)


class ChatMessageItem(BaseModel):
    """会话消息项；assistant 消息附带引用来源。"""

    id: int = Field(description="消息 ID")
    role: str = Field(description="角色：user/assistant")
    content: str = Field(description="消息内容")
    sources: list[ChatSourceItem] | None = Field(default=None, description="引用来源")
    create_time: datetime = Field(description="创建时间")

    @field_serializer("create_time")
    def serialize_time(self, value: datetime) -> str:
        """时间统一输出 yyyy-MM-dd HH:mm:ss 格式字符串。"""
        return value.strftime(TIME_FORMAT)
