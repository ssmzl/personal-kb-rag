-- 个人知识库 RAG 数据库结构
-- 说明：脚本可重复执行（IF NOT EXISTS），后端启动时自动执行。
-- 向量维度固定 1024（text-embedding-v3），余弦距离检索。

CREATE EXTENSION IF NOT EXISTS vector;

-- 用户（个人自用，单账号；密码存 bcrypt 哈希）
CREATE TABLE IF NOT EXISTS users (
    id            BIGSERIAL PRIMARY KEY,
    username      VARCHAR(64)  NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    create_time   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    update_time   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- 知识库
CREATE TABLE IF NOT EXISTS knowledge_bases (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT       NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name        VARCHAR(128) NOT NULL,
    create_time TIMESTAMPTZ  NOT NULL DEFAULT now(),
    update_time TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_bases_user_id ON knowledge_bases (user_id);

-- 文档（上传后异步解析、分块、向量化）
CREATE TABLE IF NOT EXISTS documents (
    id            BIGSERIAL PRIMARY KEY,
    kb_id         BIGINT       NOT NULL REFERENCES knowledge_bases (id) ON DELETE CASCADE,
    filename      VARCHAR(255) NOT NULL,
    file_path     VARCHAR(512) NOT NULL,
    file_type     VARCHAR(16)  NOT NULL,
    file_size     BIGINT       NOT NULL,
    status        VARCHAR(16)  NOT NULL DEFAULT 'processing'
                  CHECK (status IN ('processing', 'completed', 'failed')),
    error_message TEXT,
    chunk_count   INTEGER      NOT NULL DEFAULT 0,
    create_time   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    update_time   TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_documents_kb_id ON documents (kb_id);

-- 文档分块与向量（embedding 固定 1024 维）
CREATE TABLE IF NOT EXISTS document_chunks (
    id          BIGSERIAL PRIMARY KEY,
    kb_id       BIGINT      NOT NULL REFERENCES knowledge_bases (id) ON DELETE CASCADE,
    document_id BIGINT      NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    chunk_index INTEGER     NOT NULL,
    content     TEXT        NOT NULL,
    embedding   vector(1024) NOT NULL,
    create_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    update_time TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks (document_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_kb_id ON document_chunks (kb_id);
-- 余弦距离向量索引（ivfflat 需与 vector_cosine_ops 搭配）
CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding
    ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- 会话
CREATE TABLE IF NOT EXISTS chat_sessions (
    id          BIGSERIAL PRIMARY KEY,
    kb_id       BIGINT       NOT NULL REFERENCES knowledge_bases (id) ON DELETE CASCADE,
    title       VARCHAR(255) NOT NULL,
    create_time TIMESTAMPTZ  NOT NULL DEFAULT now(),
    update_time TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_kb_id ON chat_sessions (kb_id);

-- 会话消息（sources 保存助手回答的引用来源：文档名 + 片段）
CREATE TABLE IF NOT EXISTS chat_messages (
    id          BIGSERIAL PRIMARY KEY,
    session_id  BIGINT      NOT NULL REFERENCES chat_sessions (id) ON DELETE CASCADE,
    role        VARCHAR(16) NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT        NOT NULL,
    sources     JSONB,
    create_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    update_time TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages (session_id);
