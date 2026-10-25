# Tasks

- [x] Task 1: 工程骨架搭建：单仓结构，后端 FastAPI，前端 Vite + React + TS + Tailwind
  - [x] SubTask 1.1: 初始化后端（代码直接放仓库根目录）：`requirements.txt`（fastapi、uvicorn、sqlalchemy[asyncio]、asyncpg、pgvector、pypdf、python-docx、httpx、PyJWT、bcrypt、python-multipart、pytest、pytest-asyncio），`app/main.py` 入口、配置模块（全部敏感项走环境变量）、目录分层（app/routers、app/services、app/models、app/schemas）
  - [x] SubTask 1.2: 落地全局规范件：统一返回 `{code, message, data}` 包装、业务异常 `BizException` + 全局异常处理器、统一响应模型
  - [x] SubTask 1.3: 初始化 `frontend/`（Vite + React18 + TS + Tailwind + react-router），封装 axios 实例（baseURL、token 拦截、401 跳登录）、Tailwind 主题色板统一配置（组件内不硬编码色值）
  - [x] SubTask 1.4: 验证：`uvicorn app.main:app` 可启动且 /api/health 返回统一结构；前端 `npm run build` 通过

- [x] Task 2: 数据库基础：docker-compose postgres(pgvector) + schema + 异步 ORM
  - [x] SubTask 2.1: 根目录 `docker-compose.yml`（先含 pgvector/pgvector:pg16），`.env.example` 模板
  - [x] SubTask 2.2: `scripts/schema.sql`：`CREATE EXTENSION vector`；users / knowledge_bases / documents / document_chunks（含 `embedding vector(1024)`）/ chat_sessions / chat_messages（主键 BIGSERIAL，统一 create_time/update_time），为 document_chunks(embedding) 建 ivfflat 索引
  - [x] SubTask 2.3: SQLAlchemy async engine + 六张表 ORM 模型（embedding 列用 pgvector sqlalchemy 类型），启动时自动执行 schema
  - [x] SubTask 2.4: 验证：compose 起 postgres 后，后端启动建表成功；pytest 连真实库插入/检索一条向量通过

- [x] Task 3: 登录鉴权（后端 + 前端登录页）
  - [x] SubTask 3.1: 登录接口（bcrypt 校验、签发 JWT）、FastAPI 依赖注入式鉴权（除 /api/auth/login 外全校验，失败 401）；初始账号密码由环境变量注入并在首次启动写入
  - [x] SubTask 3.2: 前端登录页 + 路由守卫 + axios 携带 token，401 自动回登录页
  - [x] SubTask 3.3: 验证：错误密码返回统一错误体；正确登录拿到 token 并访问受保护接口成功；pytest 覆盖登录成功/失败两路径

- [x] Task 4: 知识库管理（后端 CRUD + 前端管理页）
  - [x] SubTask 4.1: 知识库 router/service：创建、重命名、删除（事务内级联删文档与分块向量）、列表（含文档数聚合）
  - [x] SubTask 4.2: 前端知识库列表/新建/重命名/删除确认页（Tailwind 样式），操作后主动刷新列表
  - [x] SubTask 4.3: 验证：pytest 覆盖创建与级联删除；前端联调走通

- [x] Task 5: 文档上传与向量化管线
  - [x] SubTask 5.1: 上传接口（类型/大小校验：pdf/docx/md/txt ≤ 20MB），文件存本地 uploads 目录，文档记录入库（状态：处理中）
  - [x] SubTask 5.2: 解析器：pypdf（pdf）、python-docx（docx）、纯文本（md/txt），统一输出纯文本
  - [x] SubTask 5.3: 分块器（段落优先 + 500 字窗口 + 50 字重叠）+ DashScope Embedding 客户端（OpenAI 兼容，text-embedding-v3，httpx 异步）+ 批量写入 pgvector；用 FastAPI BackgroundTasks/异步任务执行，完成/失败回写状态与原因，失败不留脏分块
  - [x] SubTask 5.4: 前端文档列表页：上传（进度/状态轮询）、分块查看抽屉、删除文档（级联删分块）
  - [x] SubTask 5.5: 验证：分块器 pytest（空文本、短文本、窗口与重叠正确性）；上传真实 PDF 后分块入库且向量检索可查回

- [x] Task 6: RAG 流式问答（后端 SSE + 前端对话页）
  - [x] SubTask 6.1: 会话管理接口：新建/重命名/删除会话、消息历史加载（时间字段统一输出 `yyyy-MM-dd HH:mm:ss` 格式字符串）
  - [x] SubTask 6.2: 问答接口：问题 embedding → pgvector 余弦 TopK 检索（按 kb_id 过滤）→ 拼接 system prompt（强制「仅依据资料回答，未命中则明说未找到」）+ 近 6 轮历史 → DashScope 流式调用 → SSE 输出（httpx 流式 + StreamingResponse）；异常先发 `error` 事件再结束流；流结束后发 `sources` 事件（文档名+片段）并持久化问答消息
  - [x] SubTask 6.3: 前端对话页：会话侧栏 + 消息流（react-markdown 渲染）+ 输入框；POST 流式用 fetch ReadableStream 解析 SSE，增量更新走 React state 不可变更新；回答完成后展示可展开引用来源
  - [x] SubTask 6.4: 验证：检索拼接 pytest；端到端提问上传过的资料，流式输出正常且引用正确

- [x] Task 7: 一键部署与交付文档
  - [x] SubTask 7.1: 根目录 `Dockerfile`（后端，python:3.11-slim）、`frontend/Dockerfile`（node 构建 + nginx 托管 + /api 反代）
  - [x] SubTask 7.2: 完善根目录 `docker-compose.yml`（postgres、backend、frontend 三服务编排、健康检查、启动顺序、数据卷）
  - [x] SubTask 7.3: `README.md`：项目简介、架构图（mermaid）、技术栈、本地开发与 Docker 一键启动步骤、环境变量说明、功能截图位
  - [x] SubTask 7.4: 验证：`docker compose up -d` 后全流程走通（登录→建库→上传→提问）

- [ ] Task 8: 收尾联调与规范核查
  - [ ] SubTask 8.1: 逐项核查（统一返回结构、业务异常不外抛 500、无空 except、主题色不硬编码、api-key 无硬编码、SSE error 事件、增删改后刷新列表、下划线命名）
  - [ ] SubTask 8.2: 全部 pytest 通过，前端 `npm run build` 通过

# Task Dependencies
- Task 2 depends on Task 1
- Task 3、Task 4 depend on Task 2（两者可并行）
- Task 5 depends on Task 4
- Task 6 depends on Task 5
- Task 7 depends on Task 6
- Task 8 depends on Task 7
