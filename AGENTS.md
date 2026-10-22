# AGENTS.md

> 本文件是 AI 编码代理在本仓库工作的约定与规则。修改代码前请先阅读。

## 1. 项目概述

个人知识库 RAG 全栈应用：上传文档（PDF/DOCX/MD/TXT）→ 解析分块 → Embedding 入库 → 基于知识库的流式问答（带引用溯源）。详细需求见 `.trae/specs/add-personal-kb-rag/`。

- 后端：**FastAPI**（Python 3.11+，async），代码直接在仓库根目录（`app/`）
- 前端：**React 18 + Vite + TypeScript + Tailwind CSS**（`frontend/`）
- 数据库：**PostgreSQL 16 + pgvector**（业务数据与向量同库，向量列 `vector(1024)`）
- 大模型/Embedding：阿里云百炼 DashScope（OpenAI 兼容接口，qwen 系列 + text-embedding-v3）
- 部署：根目录 `docker-compose.yml` 一键启动（postgres / backend / frontend 三服务）

## 2. 目录结构

```
├── app/                    # FastAPI 后端
│   ├── main.py             # 入口（创建 app、注册路由与异常处理器）
│   ├── config.py           # 配置（全部敏感项走环境变量）
│   ├── database.py         # SQLAlchemy async engine / session
│   ├── models/             # ORM 模型
│   ├── schemas/            # Pydantic 模型
│   ├── routers/            # 路由层（只做参数校验与调用 service）
│   └── services/           # 业务逻辑层
├── scripts/schema.sql      # 建库脚本（CREATE EXTENSION vector + 全部表）
├── tests/                  # pytest 测试
├── uploads/                # 上传文件存储（本地开发用，不入库不提交）
├── frontend/               # React 前端
│   └── src/
│       ├── api/            # axios 实例与各模块接口定义
│       ├── pages/          # 页面
│       └── components/     # 通用组件
├── docker-compose.yml
├── Dockerfile              # 后端镜像（根目录）
└── requirements.txt
```

## 3. 后端编码规范（Python / FastAPI）

- **命名**：下划线命名（snake_case）；类 `UpperCamelCase`，常量 `UPPER_SNAKE_CASE`。
- **统一返回**：所有接口返回 `{"code": int, "message": str, "data": Any}` 结构，不裸返回实体。
- **分层**：router → service → model；router 不直接写 SQL/ORM 操作。
- **异常**：业务错误抛出业务异常 `BizException`，由全局异常处理器转统一错误体；**严禁空 `except` 吞异常**，捕获必须带具体异常类型并记录诊断信息（关键参数、失败原因）。
- **持久层**：SQLAlchemy 2.x async（asyncpg）；向量检索用 pgvector 余弦距离（`embedding.cosine_distance`），按 `kb_id` 过滤。
- **时间字段**：统一 `create_time` / `update_time`；对外输出时间字符串格式为 `yyyy-MM-dd HH:mm:ss`。
- **接口路径**：以 `/api` 为前缀；路径必须与前端 `api/` 定义逐字对齐，改路径前后端同步改。

## 4. 前端编码规范（React + Tailwind）

- 函数组件 + Hooks + TypeScript；接口统一走封装的 axios 实例（token 拦截、401 跳登录页）。
- **通用组件放 `components/`，页面放 `pages/`**：多页面共用的 UI 抽成组件，不复制粘贴。
- **主题色**：色板统一定义在 `tailwind.config.js` 的 `theme.extend.colors`，组件内用语义化类名（如 `bg-primary`），不硬编码色值。
- **流式渲染**：SSE 用 fetch + ReadableStream 解析；增量更新必须走 React state 不可变更新（展开运算符/新数组），不原地改对象。
- **增删改后刷新受影响的列表**：操作会级联影响其他已展示数据时，前端必须主动重新拉取，不能假设后端提示信息够用。

## 5. 通用踩坑约定

- **SSE 流式接口**：异常必须先发送 `error` 事件再结束流，严禁只结束不发事件（前端会静默无响应）；工具/检索执行失败不外抛，返回错误信息交由上层解释，保证流不中断。
- **密钥管理**：`DASHSCOPE_API_KEY`、数据库口令、初始账号密码等一律走环境变量，严禁硬编码进代码或提交仓库；AI 功能未配置时接口返回友好提示而非 500。
- **文档向量化**：异步执行（后台任务）；失败必须回写文档状态与失败原因，且不留脏分块/向量数据。
- **级联删除**：删除知识库/文档时，同事务级联删除分块与向量记录。
- **数据库**：主键 `BIGSERIAL`；`document_chunks.embedding` 为 `vector(1024)` 并建 ivfflat 索引。

## 6. 测试与验证

- 测试用 pytest（异步用 pytest-asyncio）；为每个完成的功能模块写对应单元测试，覆盖核心逻辑与边界（如分块器：空文本、短文本、窗口与重叠正确性）。
- 提交前自查：`pytest` 全部通过；前端 `npm run build` 通过。
- 变更策略：**最小改动**，优先从现有代码扩展；不做无必要的重构与过度设计。

## 7. Git 约定

- 远程仓库：`git@github.com:ssmzl/personal-kb-rag.git`，推送到 `main` 分支。
- 默认不做任何 git 操作；需要提交时按「提交并推送」处理，并给出可追踪的变更说明。
