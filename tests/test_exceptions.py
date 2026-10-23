"""全局异常处理测试。"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.exceptions import BizException, register_exception_handlers


@pytest.fixture
def error_app() -> FastAPI:
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/biz-error")
    async def biz_error() -> None:
        raise BizException("知识库不存在", code=40401, http_status=404)

    @test_app.get("/unexpected-error")
    async def unexpected_error() -> None:
        raise RuntimeError("模拟内部错误")

    return test_app


@pytest.fixture
async def error_client(error_app: FastAPI):
    transport = ASGITransport(app=error_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def test_biz_exception_returns_unified_body(error_client: AsyncClient) -> None:
    response = await error_client.get("/biz-error")

    assert response.status_code == 404
    assert response.json() == {"code": 40401, "message": "知识库不存在", "data": None}


async def test_not_found_returns_unified_body(error_client: AsyncClient) -> None:
    response = await error_client.get("/not-exists")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == 404
    assert body["message"] == "Not Found"


async def test_unexpected_exception_returns_unified_body(error_client: AsyncClient) -> None:
    response = await error_client.get("/unexpected-error")

    assert response.status_code == 500
    assert response.json() == {"code": 500, "message": "服务器内部错误", "data": None}
