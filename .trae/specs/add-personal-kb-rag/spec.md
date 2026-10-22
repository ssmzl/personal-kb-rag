# 个人知识库 RAG 全栈应用 Spec

## Why
打造一个可日常使用的个人知识库问答产品：上传课程笔记/资料后，用自然语言提问并获得带引用来源的回答。同时作为课程设计作品与简历项目，完整展示「全栈 + RAG + 向量数据库 + Docker 部署」能力。

## 技术选型（用户指定，已定）
- 前端：React 18 + Vite + TypeScript + Tailwind CSS
- 后端：**FastAPI**（Python 3.11+，async）——二选一已定 FastAPI
- 数据库：PostgreSQL 16 + pgvector（业务数据与向量同库，向量列 `vector(1024)`，余弦相似度检索）
- 大模型/Embedding：阿里云百炼 DashScope（OpenAI 兼容接口，qwen 系列 + text-embedding-v3，1024 维），API Key 走环境变量，未配置时接口返回友好提示
- 部署：根目录 docker-compose 一键启动（postgres+pgvector、backend、nginx 前端）

## What Changes
- 新增单仓全栈工程：**FastAPI 后端代码直接写在仓库根目录**（`app/`、`requirements.txt`、`Dockerfile` 等），`frontend/`（React），根目录 `docker-compose.yml` 与 `README.md`（课程设计/部署说明）
- 登录鉴权：单用户账号密码登录 + JWT（个人自用，不做注册开放）
- 知识库管理：多知识库 CRUD
- 文档接入：上传 PDF / Word(docx) / Markdown / TXT，解析 → 分块 → Embedding → 写入 pgvector，异步处理并展示状态；支持查看分块、删除文档（级联删分块与向量）
- RAG 对话：多会话管理，提问后向量检索 TopK → 拼 prompt → SSE 流式输出回答，回答附引用来源（可定位原文片段）
- 部署：提供完整 docker-compose 与 README

## Impact
- Affected specs：无（全新工程）
- Affected code：根目录（`app/`、`requirements.txt`、`Dockerfile`）、`frontend/`、`docker-compose.yml`、`README.md`（全部新增）

## ADDED Requirements

### Requirement: 用户登录鉴权
系统 SHALL 提供账号密码登录，签发 JWT；除登录外的所有接口必须校验 JWT，校验失败返回 401。密码以 bcrypt 存储，初始账号由环境变量注入并在首次启动写入。

#### Scenario: 登录成功
- **WHEN** 用户提交正确账号密码
- **THEN** 返回统一结构 `{code, message, data}` 包裹的 token，前端跳转主页并在后续请求头携带 token

#### Scenario: 未登录访问
- **WHEN** 请求未携带或携带非法 token
- **THEN** 返回 401 与统一错误体，前端跳转登录页

### Requirement: 知识库管理
系统 SHALL 提供知识库的创建、重命名、删除与列表接口；删除知识库须级联删除其下文档、分块及向量（同库事务内完成）。

#### Scenario: 创建知识库
- **WHEN** 用户提交非空名称
- **THEN** 创建成功并出现在列表中，列表同时展示各库文档数

#### Scenario: 删除知识库
- **WHEN** 用户确认删除
- **THEN** 该库文档、分块与向量记录全部清除，前端列表刷新

### Requirement: 文档上传与向量化
系统 SHALL 支持上传 PDF / DOCX / MD / TXT 文件（单文件 ≤ 20MB），解析文本后按「段落优先 + 固定长度（约 500 字）+ 重叠（约 50 字）」分块，调用 Embedding 接口写入 pgvector；处理异步执行（后台任务），文档状态（处理中/完成/失败）可在列表查看；支持查看分块文本与删除文档。

#### Scenario: 上传成功
- **WHEN** 用户上传支持的文件
- **THEN** 文档记录入库，状态为处理中；处理完成后状态变为完成，分块数可见

#### Scenario: 不支持的类型或解析失败
- **WHEN** 上传非法类型或文件损坏
- **THEN** 状态置为失败并记录原因，不产生脏分块/向量数据

#### Scenario: 未配置 API Key
- **WHEN** 环境变量缺失导致 Embedding 不可用
- **THEN** 文档置为失败并提示「AI 服务未配置」，接口不抛 500

### Requirement: RAG 流式问答
系统 SHALL 提供会话管理（新建、重命名、删除、历史消息加载）。提问时用问题向量在指定知识库内检索 TopK（默认 5）分块，拼接 system prompt 与多轮历史后调用大模型，以 SSE 流式返回回答，流结束后返回引用来源列表（文档名 + 片段）。未命中任何相关分块时明确回答「知识库中未找到相关内容」，不编造。

#### Scenario: 流式问答成功
- **WHEN** 用户在选定知识库下提问
- **THEN** 前端逐字渲染回答，完成后展示引用来源，消息持久化到 PostgreSQL

#### Scenario: SSE 异常
- **WHEN** 大模型调用失败或客户端断开
- **THEN** 先发送 `error` 事件再结束流，前端展示错误提示而非静默

### Requirement: 一键部署
系统 SHALL 提供根目录 docker-compose 编排（postgres(pgvector)、backend、nginx 前端）与 README 说明，使本项目可在装好 Docker 的机器上一键启动。

#### Scenario: 一键启动
- **WHEN** 配置 `.env` 后执行 `docker compose up -d`
- **THEN** 三个服务全部健康，浏览器访问前端可完整走通上传→提问流程

## MODIFIED Requirements
无（全新工程）。

## REMOVED Requirements
无。
