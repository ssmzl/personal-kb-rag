"""DashScope Embedding 客户端（OpenAI 兼容接口，httpx 异步，分批调用）。

- 未配置 ``DASHSCOPE_API_KEY`` 时抛友好业务异常，由后台任务回写文档失败原因；
- 按 ``EMBEDDING_BATCH_SIZE`` 分批请求，校验返回数量与向量维度（1024）。
"""

import logging

import httpx

from app.config import settings
from app.exceptions import BizException

logger = logging.getLogger(__name__)

# DashScope text-embedding 单次请求文本条数上限较保守，取 10
EMBEDDING_BATCH_SIZE = 10
EMBEDDING_TIMEOUT_SECONDS = 60.0


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量生成文本向量，返回顺序与入参一致。"""
    if not texts:
        return []
    if not settings.dashscope_api_key:
        raise BizException("AI 服务未配置：请设置 DASHSCOPE_API_KEY 环境变量")

    url = f"{settings.dashscope_base_url.rstrip('/')}/embeddings"
    headers = {
        "Authorization": f"Bearer {settings.dashscope_api_key}",
        "Content-Type": "application/json",
    }
    vectors: list[list[float]] = []

    try:
        async with httpx.AsyncClient(timeout=EMBEDDING_TIMEOUT_SECONDS) as client:
            for start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
                batch = texts[start : start + EMBEDDING_BATCH_SIZE]
                response = await client.post(
                    url,
                    headers=headers,
                    json={
                        "model": settings.embedding_model,
                        "input": batch,
                        "dimensions": settings.embedding_dimension,
                        "encoding_format": "float",
                    },
                )
                vectors.extend(_parse_embeddings(response, expected_count=len(batch)))
    except httpx.HTTPError as exc:
        logger.warning(
            "Embedding 请求失败：url=%s batch_size=%s batch_count=%s error_type=%s detail=%s",
            url,
            EMBEDDING_BATCH_SIZE,
            len(texts),
            type(exc).__name__,
            exc,
        )
        raise BizException("Embedding 服务调用失败，请稍后重试") from exc

    logger.info("Embedding 完成：text_count=%s model=%s", len(texts), settings.embedding_model)
    return vectors


def _parse_embeddings(response: httpx.Response, expected_count: int) -> list[list[float]]:
    """解析并校验单批 Embedding 响应，异常响应转为业务异常。"""
    if response.status_code != 200:
        logger.warning(
            "Embedding 服务返回异常：status=%s body=%s",
            response.status_code,
            response.text[:500],
        )
        raise BizException(f"Embedding 服务调用失败（HTTP {response.status_code}）")

    try:
        items = response.json()["data"]
        ordered = sorted(items, key=lambda item: item["index"])
        vectors = [item["embedding"] for item in ordered]
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning("Embedding 响应格式异常：body=%s", response.text[:500])
        raise BizException("Embedding 服务返回格式异常") from exc

    if len(vectors) != expected_count:
        logger.warning(
            "Embedding 返回数量异常：expected=%s actual=%s",
            expected_count,
            len(vectors),
        )
        raise BizException(
            f"Embedding 返回数量异常：期望 {expected_count}，实际 {len(vectors)}"
        )

    for vector in vectors:
        if len(vector) != settings.embedding_dimension:
            logger.warning(
                "Embedding 维度异常：expected=%s actual=%s",
                settings.embedding_dimension,
                len(vector),
            )
            raise BizException(
                f"Embedding 维度异常：期望 {settings.embedding_dimension}，实际 {len(vector)}"
            )
    return vectors
