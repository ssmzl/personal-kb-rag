import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
} from 'react'
import ReactMarkdown from 'react-markdown'
import { Link } from 'react-router-dom'

import {
  askQuestion,
  createChatSession,
  deleteChatSession,
  listChatMessages,
  listChatSessions,
  renameChatSession,
  type ChatMessageItem,
  type ChatSessionItem,
} from '@/api/chat'
import { ApiError } from '@/api/client'
import { listKnowledgeBases, type KnowledgeBaseItem } from '@/api/knowledgeBase'
import Modal from '@/components/Modal'

/** 本地消息气泡：pending 表示流式生成中，error 保存本次问答的错误提示 */
interface ChatBubble extends ChatMessageItem {
  pending?: boolean
  error?: string | null
}

/** 不可变更新最后一条助手消息 */
function update_last_assistant(
  messages: ChatBubble[],
  update: (message: ChatBubble) => ChatBubble,
): ChatBubble[] {
  const last = messages[messages.length - 1]
  if (!last || last.role !== 'assistant') {
    return messages
  }
  return [...messages.slice(0, -1), update(last)]
}

export default function ChatPage() {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBaseItem[]>([])
  const [kbLoading, setKbLoading] = useState(true)
  const [kbId, setKbId] = useState<number | null>(null)

  const [sessions, setSessions] = useState<ChatSessionItem[]>([])
  const [sessionsLoading, setSessionsLoading] = useState(false)
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null)

  const [messages, setMessages] = useState<ChatBubble[]>([])
  const [messagesLoading, setMessagesLoading] = useState(false)
  const [question, setQuestion] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [hint, setHint] = useState('')

  const [renameTarget, setRenameTarget] = useState<ChatSessionItem | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<ChatSessionItem | null>(null)
  const [titleInput, setTitleInput] = useState('')
  const [modalHint, setModalHint] = useState('')
  const [modalSubmitting, setModalSubmitting] = useState(false)

  const abortRef = useRef<AbortController | null>(null)
  const scrollRef = useRef<HTMLDivElement | null>(null)

  // 加载知识库列表，默认选中第一个
  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const list = await listKnowledgeBases()
        if (cancelled) {
          return
        }
        setKnowledgeBases(list)
        setKbId((current) => current ?? list[0]?.id ?? null)
      } catch (error) {
        if (!cancelled) {
          setHint(error instanceof ApiError ? error.message : '加载知识库列表失败')
        }
      } finally {
        if (!cancelled) {
          setKbLoading(false)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const refreshSessions = useCallback(async (targetKbId: number): Promise<ChatSessionItem[]> => {
    const list = await listChatSessions(targetKbId)
    setSessions(list)
    return list
  }, [])

  // 切换知识库：中止进行中的流，重置会话与消息
  useEffect(() => {
    abortRef.current?.abort()
    setActiveSessionId(null)
    setMessages([])
    if (kbId === null) {
      setSessions([])
      return
    }

    let cancelled = false
    setSessionsLoading(true)
    setHint('')
    void (async () => {
      try {
        const list = await listChatSessions(kbId)
        if (!cancelled) {
          setSessions(list)
        }
      } catch (error) {
        if (!cancelled) {
          setHint(error instanceof ApiError ? error.message : '加载会话列表失败')
        }
      } finally {
        if (!cancelled) {
          setSessionsLoading(false)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [kbId])

  // 切换会话：加载历史消息
  useEffect(() => {
    if (activeSessionId === null) {
      setMessages([])
      return
    }

    let cancelled = false
    setMessagesLoading(true)
    setHint('')
    void (async () => {
      try {
        const list = await listChatMessages(activeSessionId)
        if (!cancelled) {
          setMessages(list)
        }
      } catch (error) {
        if (!cancelled) {
          setMessages([])
          setHint(error instanceof ApiError ? error.message : '加载历史消息失败')
        }
      } finally {
        if (!cancelled) {
          setMessagesLoading(false)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [activeSessionId])

  // 新消息或流式增量时滚动到底部
  useEffect(() => {
    const container = scrollRef.current
    if (container) {
      container.scrollTop = container.scrollHeight
    }
  }, [messages])

  // 组件卸载时中止流式请求
  useEffect(() => {
    return () => {
      abortRef.current?.abort()
    }
  }, [])

  async function handleCreateSession() {
    if (kbId === null) {
      return
    }
    // 新建会话前中止当前流，避免增量写入即将切换掉的会话
    abortRef.current?.abort()
    try {
      const created = await createChatSession(kbId)
      await refreshSessions(kbId)
      setActiveSessionId(created.id)
    } catch (error) {
      setHint(error instanceof ApiError ? error.message : '新建会话失败，请稍后重试')
    }
  }

  function handleSelectSession(session: ChatSessionItem) {
    if (session.id === activeSessionId) {
      return
    }
    // 切换会话前中止当前流，避免增量写到错误的会话
    abortRef.current?.abort()
    setActiveSessionId(session.id)
  }

  function handleKbChange(event: ChangeEvent<HTMLSelectElement>) {
    const value = Number(event.target.value)
    setKbId(Number.isInteger(value) && value > 0 ? value : null)
  }

  function openRenameModal(session: ChatSessionItem) {
    setTitleInput(session.title)
    setModalHint('')
    setRenameTarget(session)
  }

  async function handleRename(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!renameTarget) {
      return
    }
    const title = titleInput.trim()
    if (!title) {
      setModalHint('请输入会话标题')
      return
    }
    setModalSubmitting(true)
    setModalHint('')
    try {
      await renameChatSession(renameTarget.id, title)
      setRenameTarget(null)
      if (kbId !== null) {
        await refreshSessions(kbId)
      }
    } catch (error) {
      setModalHint(error instanceof ApiError ? error.message : '重命名失败，请稍后重试')
    } finally {
      setModalSubmitting(false)
    }
  }

  async function handleDelete() {
    if (!deleteTarget || kbId === null) {
      return
    }
    const deletingId = deleteTarget.id
    // 删除当前会话前先中止流，避免服务端继续向已删除会话写入消息
    if (deletingId === activeSessionId) {
      abortRef.current?.abort()
    }
    setModalSubmitting(true)
    try {
      await deleteChatSession(deletingId)
      setDeleteTarget(null)
      const list = await refreshSessions(kbId)
      if (activeSessionId === deletingId) {
        setActiveSessionId(list[0]?.id ?? null)
      }
    } catch (error) {
      setHint(error instanceof ApiError ? error.message : '删除失败，请稍后重试')
      setDeleteTarget(null)
    } finally {
      setModalSubmitting(false)
    }
  }

  async function handleSend(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault()
    const text = question.trim()
    if (!text || streaming || activeSessionId === null) {
      return
    }

    setQuestion('')
    setHint('')
    const stamp = Date.now()
    const userBubble: ChatBubble = {
      id: -stamp,
      role: 'user',
      content: text,
      sources: null,
      create_time: '',
    }
    const assistantBubble: ChatBubble = {
      id: -stamp - 1,
      role: 'assistant',
      content: '',
      sources: null,
      create_time: '',
      pending: true,
    }
    setMessages((prev) => [...prev, userBubble, assistantBubble])
    setStreaming(true)

    const controller = new AbortController()
    abortRef.current = controller
    try {
      await askQuestion(
        activeSessionId,
        text,
        {
          onDelta: (delta) => {
            setMessages((prev) =>
              update_last_assistant(prev, (message) => ({
                ...message,
                content: message.content + delta,
              })),
            )
          },
          onSources: (sources) => {
            setMessages((prev) =>
              update_last_assistant(prev, (message) => ({
                ...message,
                sources,
                pending: false,
              })),
            )
          },
          onError: (message) => {
            setMessages((prev) =>
              update_last_assistant(prev, (bubble) => ({
                ...bubble,
                pending: false,
                error: message,
              })),
            )
          },
        },
        controller.signal,
      )
    } catch (error) {
      if (!controller.signal.aborted) {
        setMessages((prev) =>
          update_last_assistant(prev, (bubble) => ({
            ...bubble,
            pending: false,
            error: error instanceof ApiError ? error.message : '问答失败，请稍后重试',
          })),
        )
      }
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null
      }
      setStreaming(false)
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void handleSend()
    }
  }

  return (
    <section className="flex h-[calc(100vh-9rem)] min-h-[520px] flex-col">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-text">对话</h1>
          <p className="mt-1 text-sm text-text-muted">基于知识库检索并流式回答，回答附带可展开的引用来源</p>
        </div>
        {knowledgeBases.length > 0 && (
          <label className="flex items-center gap-2 text-sm text-text-muted">
            知识库
            <select
              value={kbId ?? ''}
              onChange={handleKbChange}
              className="rounded-md border border-border bg-surface px-3 py-1.5 text-sm text-text outline-none focus:border-primary"
            >
              {knowledgeBases.map((kb) => (
                <option key={kb.id} value={kb.id}>
                  {kb.name}（{kb.document_count} 文档）
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {hint && <p className="mb-3 text-sm text-danger">{hint}</p>}

      {kbLoading ? (
        <div className="flex flex-1 items-center justify-center rounded-lg border border-border bg-surface text-sm text-text-muted">
          加载中…
        </div>
      ) : knowledgeBases.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-surface text-sm text-text-muted">
          <p>还没有知识库，请先创建并上传文档</p>
          <Link
            to="/kb"
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-hover"
          >
            去创建知识库
          </Link>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 gap-4">
          <aside className="flex w-60 shrink-0 flex-col rounded-lg border border-border bg-surface">
            <div className="flex items-center justify-between border-b border-border px-3 py-2.5">
              <span className="text-sm font-medium text-text">会话</span>
              <button
                type="button"
                onClick={() => void handleCreateSession()}
                className="rounded-md bg-primary px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-primary-hover"
              >
                新建
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-2">
              {sessionsLoading ? (
                <p className="px-1 py-2 text-xs text-text-muted">加载中…</p>
              ) : sessions.length === 0 ? (
                <p className="px-1 py-2 text-xs text-text-muted">暂无会话，点击「新建」开始</p>
              ) : (
                <ul className="space-y-1">
                  {sessions.map((session) => {
                    const active = session.id === activeSessionId
                    return (
                      <li
                        key={session.id}
                        className={`rounded-md px-2 py-2 ${active ? 'bg-primary-light' : 'hover:bg-surface-muted'}`}
                      >
                        <button
                          type="button"
                          onClick={() => handleSelectSession(session)}
                          title={session.title}
                          className={`block w-full truncate text-left text-sm ${active ? 'text-primary' : 'text-text'}`}
                        >
                          {session.title}
                        </button>
                        <div className="mt-1 flex items-center justify-between gap-2">
                          <span className="truncate text-xs text-text-muted">{session.create_time}</span>
                          <div className="flex shrink-0 gap-1">
                            <button
                              type="button"
                              onClick={() => openRenameModal(session)}
                              className="text-xs text-text-muted hover:text-primary"
                            >
                              重命名
                            </button>
                            <button
                              type="button"
                              onClick={() => setDeleteTarget(session)}
                              className="text-xs text-danger hover:underline"
                            >
                              删除
                            </button>
                          </div>
                        </div>
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          </aside>

          <div className="flex min-w-0 flex-1 flex-col rounded-lg border border-border bg-surface">
            {activeSessionId === null ? (
              <div className="flex flex-1 items-center justify-center text-sm text-text-muted">
                选择左侧会话或新建会话后开始提问
              </div>
            ) : (
              <>
                <div ref={scrollRef} className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
                  {messagesLoading ? (
                    <p className="text-sm text-text-muted">加载中…</p>
                  ) : messages.length === 0 ? (
                    <div className="flex h-full items-center justify-center text-center text-sm text-text-muted">
                      当前会话还没有消息，输入问题开始提问
                    </div>
                  ) : (
                    messages.map((message) => (
                      <div
                        key={message.id}
                        className={message.role === 'user' ? 'flex justify-end' : 'flex justify-start'}
                      >
                        <div
                          className={
                            message.role === 'user'
                              ? 'max-w-[80%] rounded-lg bg-primary px-4 py-2'
                              : 'w-full max-w-[85%] rounded-lg border border-border bg-surface-muted px-4 py-3'
                          }
                        >
                          {message.role === 'user' ? (
                            <p className="whitespace-pre-wrap break-words text-sm text-white">
                              {message.content}
                            </p>
                          ) : (
                            <>
                              {message.content ? (
                                <div className="markdown-body break-words text-sm text-text">
                                  <ReactMarkdown>{message.content}</ReactMarkdown>
                                </div>
                              ) : message.pending ? (
                                <p className="text-sm text-text-muted">正在检索并生成回答…</p>
                              ) : null}
                              {message.error && (
                                <p className="mt-2 text-sm text-danger">{message.error}</p>
                              )}
                              {message.sources && message.sources.length > 0 && (
                                <details className="mt-3 rounded-md border border-border bg-surface px-3 py-2">
                                  <summary className="cursor-pointer text-xs text-text-muted">
                                    引用来源（{message.sources.length}）
                                  </summary>
                                  <ul className="mt-2 space-y-2">
                                    {message.sources.map((source, index) => (
                                      <li
                                        key={`${message.id}-${source.document_id}-${source.chunk_index}-${index}`}
                                        className="rounded-md bg-surface-muted px-3 py-2"
                                      >
                                        <p className="text-xs font-medium text-text">
                                          {source.document_name} · 片段 {source.chunk_index + 1}
                                        </p>
                                        <p className="mt-1 line-clamp-4 whitespace-pre-wrap text-xs text-text-muted">
                                          {source.content}
                                        </p>
                                      </li>
                                    ))}
                                  </ul>
                                </details>
                              )}
                            </>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                </div>

                <form onSubmit={handleSend} className="border-t border-border p-3">
                  <div className="flex items-end gap-2">
                    <textarea
                      value={question}
                      onChange={(event) => setQuestion(event.target.value)}
                      onKeyDown={handleKeyDown}
                      rows={2}
                      maxLength={2000}
                      disabled={streaming}
                      placeholder="输入问题，Enter 发送，Shift + Enter 换行"
                      className="min-h-[44px] flex-1 resize-none rounded-md border border-border px-3 py-2 text-sm outline-none focus:border-primary disabled:bg-surface-muted disabled:text-text-muted"
                    />
                    <button
                      type="submit"
                      disabled={streaming || !question.trim()}
                      className="h-[44px] rounded-md bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {streaming ? '回答中…' : '发送'}
                    </button>
                  </div>
                </form>
              </>
            )}
          </div>
        </div>
      )}

      <Modal title="重命名会话" open={renameTarget !== null} onClose={() => setRenameTarget(null)}>
        <form onSubmit={handleRename}>
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-text">标题</span>
            <input
              type="text"
              value={titleInput}
              maxLength={255}
              autoFocus
              onChange={(event) => setTitleInput(event.target.value)}
              className="w-full rounded-md border border-border px-3 py-2 text-sm outline-none focus:border-primary"
              placeholder="请输入会话标题"
            />
          </label>
          {modalHint && <p className="mt-2 text-sm text-danger">{modalHint}</p>}
          <div className="mt-6 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setRenameTarget(null)}
              className="rounded-md border border-border px-4 py-2 text-sm text-text-muted transition-colors hover:bg-surface-muted"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={modalSubmitting}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-60"
            >
              {modalSubmitting ? '保存中…' : '保存'}
            </button>
          </div>
        </form>
      </Modal>

      <Modal title="删除会话" open={deleteTarget !== null} onClose={() => setDeleteTarget(null)}>
        <p className="text-sm text-text">
          确定删除会话「{deleteTarget?.title}」吗？其全部历史消息将被一并删除，且不可恢复。
        </p>
        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={() => setDeleteTarget(null)}
            className="rounded-md border border-border px-4 py-2 text-sm text-text-muted transition-colors hover:bg-surface-muted"
          >
            取消
          </button>
          <button
            type="button"
            disabled={modalSubmitting}
            onClick={() => void handleDelete()}
            className="rounded-md bg-danger px-4 py-2 text-sm font-medium text-white transition-colors hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {modalSubmitting ? '删除中…' : '确认删除'}
          </button>
        </div>
      </Modal>
    </section>
  )
}
