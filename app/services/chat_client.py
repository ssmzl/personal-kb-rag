"""DashScope 对话模型客户端（OpenAI 兼容接口，httpx 流式）。

- 未配置 ``DASHSCOPE_API_KEY`` 时抛友好业务异常；
- 逐行解析 SSE（``data: {...}`` / ``data: [DONE]``），只产出增量文本；
- 网络 / HTTP 异常统一转为业务异常，由上层转成 SSE ``error`` 事件。
"""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import settings
from app.exceptions import BizException

logger = logging.getLogger(__name__)

CHAT_CONNECT_TIMEOUT_SECONDS = 10.0
CHAT_READ_TIMEOUT_SECONDS = 120.0
CHAT_TEMPERATURE = 0.3
DONE_MARKER = "[DONE]"


async def stream_chat_completion(messages: list[dict[str, str]]) -> AsyncIterator[str]:
    """调用对话模型并逐段产出回答文本。"""
    if not settings.dashscope_api_key:
        raise BizException("AI 服务未配置：请设置 DASHSCOPE_API_KEY 环境变量")

    url = f"{settings.dashscope_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": settings.chat_model,
        "messages": messages,
        "stream": True,
        "temperature": CHAT_TEMPERATURE,
    }

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                CHAT_READ_TIMEOUT_SECONDS,
                connect=CHAT_CONNECT_TIMEOUT_SECONDS,
            )
        ) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                if response.status_code != 200:
                    body = (await response.aread()).decode("utf-8", errors="replace")
                    logger.warning(
                        "对话模型返回异常：status=%s model=%s body=%s",
                        response.status_code,
                        settings.chat_model,
                        body[:500],
                    )
                    raise BizException(f"大模型调用失败（HTTP {response.status_code}）")

                async for line in response.aiter_lines():
                    content = parse_stream_line(line)
                    if content is DONE_MARKER:
                        return
                    if content:
                        yield content
    except httpx.HTTPError as exc:
        logger.warning(
            "对话模型请求失败：url=%s model=%s error_type=%s detail=%s",
            url,
            settings.chat_model,
            type(exc).__name__,
            exc,
        )
        raise BizException("大模型服务调用失败，请稍后重试") from exc

    logger.info("对话流式输出完成：model=%s", settings.chat_model)


def parse_stream_line(line: str) -> str | None:
    """解析单行 SSE，返回增量文本、``[DONE]`` 标记或 None（空行/非数据行）。

    流内若返回 ``error`` 负载，直接抛业务异常交给上层转成 ``error`` 事件。
    """
    line = line.strip()
    if not line.startswith("data:"):
        return None

    data = line[len("data:"):].strip()
    if not data:
        return None
    if data == DONE_MARKER:
        return DONE_MARKER

    try:
        payload = json.loads(data)
    except ValueError:
        logger.warning("对话流式响应 JSON 解析失败：line=%s", line[:500])
        return None
    if not isinstance(payload, dict):
        return None

    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message") or "大模型服务返回错误"
        logger.warning("对话模型流内错误：%s", message)
        raise BizException(f"大模型服务返回错误：{message}")

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    delta = choices[0].get("delta")
    if not isinstance(delta, dict):
        return None
    content = delta.get("content")
    return content if isinstance(content, str) and content else None
