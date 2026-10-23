# Checklist

- [ ] 后端 `uvicorn app.main:app` 可启动且 /api/health 返回统一 `{code, message, data}` 结构；前端 `npm run build` 通过
- [x] docker-compose 可启动 postgres(pgvector)，后端启动后扩展与六张表自动就绪，embedding 列为 vector(1024)
- [ ] 错误账号密码登录返回统一错误体；正确登录签发 JWT；无 token 访问受保护接口返回 401 且前端跳登录页
- [ ] 密码 bcrypt 存储，初始账号由环境变量注入，代码与仓库中无任何硬编码密钥
- [ ] 知识库创建/重命名/删除/列表接口可用，列表含文档数；删除知识库后文档、分块与向量记录均已级联清除
- [ ] 上传 PDF/DOCX/MD/TXT（≤20MB）后异步完成解析分块并写入 pgvector，文档状态正确流转（处理中→完成/失败+原因）
- [ ] 上传非法类型/损坏文件时状态置失败且有原因，无脏分块残留
- [ ] 未配置 DASHSCOPE_API_KEY 时，Embedding/问答接口返回友好提示而非 500
- [ ] 分块器 pytest 覆盖：空文本、短文本、长文本窗口与重叠正确性
- [ ] 提问后在指定知识库内按余弦相似度检索 TopK，SSE 逐 token 流式输出，流结束后 `sources` 事件带文档名+片段
- [ ] 大模型调用失败/客户端断开时，SSE 先发 `error` 事件再结束，前端有可见错误提示
- [ ] 知识库无相关内容时，回答明确告知「未找到」而非编造
- [ ] 会话可新建/重命名/删除，历史消息刷新后可加载；时间输出为 `yyyy-MM-dd HH:mm:ss`
- [ ] 前端流式增量更新通过不可变 state 更新，逐字渲染正常；引用来源可展开查看
- [ ] 前端所有增删改操作后主动刷新受影响列表
- [ ] 根目录 `docker compose up -d` 后三服务健康，浏览器走通 登录→建库→上传→提问 全流程
- [ ] README 含架构说明（mermaid）、技术栈、本地开发与 Docker 启动步骤、环境变量说明
- [ ] 全部 pytest 通过；规范核查无硬编码色值（走 Tailwind 主题配置）、无空 except、接口均返回统一结构、Python 下划线命名
