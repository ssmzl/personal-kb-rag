"""应用配置。

所有敏感项（数据库口令、JWT 密钥、初始账号、DashScope API Key）一律通过环境变量注入，
代码中不提供真实值；缺失时由对应功能在运行时返回友好提示。
"""

import os
from dataclasses import dataclass, field


def _env_bool(name: str, default: bool) -> bool:
    """读取布尔型环境变量，无法识别时退回默认值。"""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    """读取整型环境变量，非法值直接报错，避免配置错误被静默忽略。"""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"环境变量 {name} 必须为整数，当前值：{raw!r}") from exc


def _env_list(name: str, default: list[str]) -> list[str]:
    """读取逗号分隔的列表型环境变量。"""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    """应用运行配置（进程启动时从环境变量加载一次）。"""

    app_name: str = os.getenv("APP_NAME", "personal-kb-rag")
    app_version: str = "0.1.0"
    debug: bool = field(default_factory=lambda: _env_bool("DEBUG", False))
    api_prefix: str = "/api"
    cors_origins: list[str] = field(
        default_factory=lambda: _env_list(
            "CORS_ORIGINS",
            ["http://localhost:5173", "http://127.0.0.1:5173"],
        )
    )

    # 数据库
    database_url: str = os.getenv("DATABASE_URL", "")

    # 登录鉴权
    jwt_secret: str = os.getenv("JWT_SECRET", "")
    jwt_expire_minutes: int = field(default_factory=lambda: _env_int("JWT_EXPIRE_MINUTES", 1440))
    initial_admin_username: str = os.getenv("INITIAL_ADMIN_USERNAME", "")
    initial_admin_password: str = os.getenv("INITIAL_ADMIN_PASSWORD", "")

    # 阿里云百炼 DashScope（OpenAI 兼容接口）
    dashscope_api_key: str = os.getenv("DASHSCOPE_API_KEY", "")
    dashscope_base_url: str = os.getenv(
        "DASHSCOPE_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    chat_model: str = os.getenv("CHAT_MODEL", "qwen-plus")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-v3")
    embedding_dimension: int = 1024

    # 文件上传
    upload_dir: str = os.getenv("UPLOAD_DIR", "uploads")
    upload_max_mb: int = field(default_factory=lambda: _env_int("UPLOAD_MAX_MB", 20))


settings = Settings()
