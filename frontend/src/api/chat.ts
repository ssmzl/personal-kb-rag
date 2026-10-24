import http, { API_BASE_URL, ApiError, TOKEN_STORAGE_KEY } from '@/api/client'
import type { ApiResponse } from '@/types/api'

export type ChatRole = 'user' | 'assistant'

export interface ChatSessionItem {
  id: number
  kb_id: number
  title: string
  /** 格式：yyyy-MM-dd HH:mm:ss */
  create_time: string
  update_time: string
}

export interface ChatSourceItem {
  document_id: number
  document_name: string
  chunk_index: number
  content: string
}

export interface ChatMessageItem {
  id: number
  role: ChatRole
  content: string
  sources: ChatSourceItem[] | null
  /** 格式：yyyy-MM-dd HH:mm:ss */
  create_time: string
}

/** 获取知识库下的会话列表 */
export async function listChatSessions(kbId: number): Promise<ChatSessionItem[]> {
  const { data } = await http.get<ApiResponse<ChatSessionItem[]>>(
    `/knowledge-bases/${kbId}/chat-sessions`,
  )
  return data.data ?? []
}

/** 新建会话（标题缺省为「新对话」） */
export async function createChatSession(kbId: number, title?: string): Promise<ChatSessionItem> {
  const { data } = await http.post<ApiResponse<ChatSessionItem>>(
    `/knowledge-bases/${kbId}/chat-sessions`,
    title === undefined ? {} : { title },
  )
  if (!data.data) {
    throw new Error('新建会话返回数据为空')
  }
  return data.data
}

/** 重命名会话 */
export async function renameChatSession(sessionId: number, title: string): Promise<void> {
  await http.put<ApiResponse<ChatSessionItem>>(`/chat-sessions/${sessionId}`, { title })
}

/** 删除会话（其下消息一并删除） */
export async function deleteChatSession(sessionId: number): Promise<void> {
  await http.delete<ApiResponse<null>>(`/chat-sessions/${sessionId}`)
}

/** 加载会话历史消息（按时间正序） */
export async function listChatMessages(sessionId: number): Promise<ChatMessageItem[]> {
  const { data } = await http.get<ApiResponse<ChatMessageItem[]>>(
    `/chat-sessions/${sessionId}/messages`,
  )
  return data.data ?? []
}

export interface AskQuestionHandlers {
  onDelta: (delta: string) => void
  onSources: (sources: ChatSourceItem[]) => void
  onError: (message: string) => void
}

interface SseMessage {
  event: string
  data: string
}

function is_record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

/** 解析单个 SSE 事件块（event + 多行 data） */
function parse_sse_block(block: string): SseMessage | null {
  let event = 'message'
  const data_lines: string[] = []
  for (const raw_line of block.split('\n')) {
    const line = raw_line.replace(/\r$/, '')
    if (line.startsWith('event:')) {
      event = line.slice('event:'.length).trim()
    } else if (line.startsWith('data:')) {
      data_lines.push(line.slice('data:'.length).trimStart())
    }
  }
  if (data_lines.length === 0) {
    return null
  }
  return { event, data: data_lines.join('\n') }
}

/** 把后端 sources 数据规整为强类型结构（仅接受结构完整的项） */
function normalize_sources(value: unknown): ChatSourceItem[] {
  if (!Array.isArray(value)) {
    return []
  }
  const sources: ChatSourceItem[] = []
  for (const item of value) {
    if (!is_record(item)) {
      continue
    }
    const document_id = Number(item.document_id)
    const chunk_index = Number(item.chunk_index)
    if (!Number.isFinite(document_id) || !Number.isFinite(chunk_index)) {
      continue
    }
    sources.push({
      document_id,
      chunk_index,
      document_name:
        typeof item.document_name === 'string' && item.document_name
          ? item.document_name
          : '未知文档',
      content: typeof item.content === 'string' ? item.content : '',
    })
  }
  return sources
}

/**
 * POST 流式问答：用 fetch + ReadableStream 解析 SSE。
 * 服务端事件：delta（增量文本）→ sources（引用来源）或 error（错误提示）。
 */
export async function askQuestion(
  sessionId: number,
  question: string,
  handlers: AskQuestionHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY)
  const response = await fetch(`${API_BASE_URL}/chat-sessions/${sessionId}/ask`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ question }),
    signal,
  })

  if (response.status === 401) {
    localStorage.removeItem(TOKEN_STORAGE_KEY)
    if (window.location.pathname !== '/login') {
      window.location.assign('/login')
    }
    throw new ApiError(401, '登录已失效，请重新登录')
  }

  if (!response.ok || !response.body) {
    const body = (await response.json().catch(() => null)) as ApiResponse<unknown> | null
    throw new ApiError(body?.code ?? response.status, body?.message ?? '问答请求失败')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let saw_sources = false
  let saw_error = false

  function handle_sse(message: SseMessage): void {
    let payload: unknown
    try {
      payload = JSON.parse(message.data)
    } catch {
      return
    }
    if (!is_record(payload)) {
      return
    }

    if (message.event === 'delta' && typeof payload.content === 'string') {
      handlers.onDelta(payload.content)
      return
    }
    if (message.event === 'sources') {
      saw_sources = true
      handlers.onSources(normalize_sources(payload.sources))
      return
    }
    if (message.event === 'error') {
      saw_error = true
      handlers.onError(
        typeof payload.message === 'string' && payload.message
          ? payload.message
          : '问答失败，请稍后重试',
      )
    }
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      break
    }
    buffer = (buffer + decoder.decode(value, { stream: true })).replace(/\r\n/g, '\n')
    let separator = buffer.indexOf('\n\n')
    while (separator >= 0) {
      const block = buffer.slice(0, separator)
      buffer = buffer.slice(separator + 2)
      const message = parse_sse_block(block)
      if (message) {
        handle_sse(message)
      }
      separator = buffer.indexOf('\n\n')
    }
  }

  // 处理流末尾没有空行分隔的残余事件
  buffer = (buffer + decoder.decode()).replace(/\r\n/g, '\n')
  if (buffer.trim()) {
    const message = parse_sse_block(buffer)
    if (message) {
      handle_sse(message)
    }
  }

  if (!saw_sources && !saw_error) {
    handlers.onError('回答流式输出意外中断，请重试')
  }
}
