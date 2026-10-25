# 后端镜像：FastAPI + uvicorn
FROM python:3.11-slim

# Python 运行时优化：不生成 .pyc、日志实时输出、pip 不缓存
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 先装依赖，利用镜像层缓存（requirements.txt 不变时不重复安装）
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 业务代码与建库脚本（启动时由 app.database 执行 scripts/schema.sql）
COPY app ./app
COPY scripts ./scripts

# 以非 root 用户运行；uploads 目录需可写（生产环境挂载数据卷）
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/uploads \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
