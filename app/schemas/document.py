"""文档相关 Pydantic 模型。"""

from datetime import datetime

from pydantic import BaseModel, Field, field_serializer

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class DocumentItem(BaseModel):
    """文档列表项，含处理状态与分块数。"""

    id: int = Field(description="文档 ID")
    kb_id: int = Field(description="所属知识库 ID")
    filename: str = Field(description="原始文件名")
    file_type: str = Field(description="文件类型（pdf/docx/md/txt）")
    file_size: int = Field(description="文件大小（字节）")
    status: str = Field(description="处理状态：pending/processing/completed/failed")
    error_message: str | None = Field(default=None, description="失败原因")
    chunk_count: int = Field(description="分块数")
    create_time: datetime = Field(description="创建时间")
    update_time: datetime = Field(description="更新时间")

    @field_serializer("create_time", "update_time")
    def serialize_time(self, value: datetime) -> str:
        """时间统一输出 yyyy-MM-dd HH:mm:ss 格式字符串。"""
        return value.strftime(TIME_FORMAT)


class DocumentChunkRequest(BaseModel):
    """手动触发分块的请求参数。"""

    chunk_strategy: str = Field(
        default="paragraph",
        description="分块策略：paragraph（段落优先）/ fixed（固定窗口）/ sentence（句子聚合）/ markdown（Markdown 标题）",
    )


class DocumentChunkItem(BaseModel):
    """文档分块项：分块序号与文本内容。"""

    id: int = Field(description="分块 ID")
    chunk_index: int = Field(description="分块序号，从 0 开始")
    content: str = Field(description="分块文本")
    create_time: datetime = Field(description="创建时间")

    @field_serializer("create_time")
    def serialize_time(self, value: datetime) -> str:
        """时间统一输出 yyyy-MM-dd HH:mm:ss 格式字符串。"""
        return value.strftime(TIME_FORMAT)
