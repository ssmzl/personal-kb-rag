import { useCallback, useEffect, useRef, useState, type ChangeEvent } from 'react'
import { Link, useParams } from 'react-router-dom'

import { ApiError } from '@/api/client'
import {
  deleteDocument,
  listDocumentChunks,
  listDocuments,
  uploadDocument,
  type DocumentChunkItem,
  type DocumentItem,
  type DocumentStatus,
} from '@/api/documents'
import { listKnowledgeBases } from '@/api/knowledgeBase'
import Drawer from '@/components/Drawer'
import Modal from '@/components/Modal'

const MAX_UPLOAD_MB = 20
const POLL_INTERVAL_MS = 2000
const ACCEPT_TYPES = '.pdf,.docx,.md,.txt'

const STATUS_TEXT: Record<DocumentStatus, string> = {
  processing: '处理中',
  completed: '已完成',
  failed: '失败',
}

const STATUS_CLASS: Record<DocumentStatus, string> = {
  processing: 'bg-primary-light text-primary',
  completed: 'bg-surface-muted text-text-muted',
  failed: 'bg-danger-light text-danger',
}

/** 字节数转可读大小 */
function format_file_size(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`
  }
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export default function DocumentPage() {
  const params = useParams()
  const kbId = Number(params.kbId)
  const validKbId = Number.isInteger(kbId) && kbId > 0

  const [kbName, setKbName] = useState('')
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [loading, setLoading] = useState(true)
  const [hint, setHint] = useState('')

  const [uploading, setUploading] = useState(false)
  const [uploadPercent, setUploadPercent] = useState(0)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const [deleteTarget, setDeleteTarget] = useState<DocumentItem | null>(null)
  const [deleting, setDeleting] = useState(false)

  const [chunkTarget, setChunkTarget] = useState<DocumentItem | null>(null)
  const [chunks, setChunks] = useState<DocumentChunkItem[]>([])
  const [chunksLoading, setChunksLoading] = useState(false)
  const [chunksHint, setChunksHint] = useState('')

  const refresh = useCallback(
    async (showLoading = false) => {
      if (!validKbId) {
        setLoading(false)
        return
      }
      if (showLoading) {
        setLoading(true)
      }
      try {
        const list = await listDocuments(kbId)
        setDocuments(list)
        setHint('')
      } catch (error) {
        setHint(error instanceof ApiError ? error.message : '加载文档列表失败')
      } finally {
        setLoading(false)
      }
    },
    [kbId, validKbId],
  )

  useEffect(() => {
    void refresh(true)
  }, [refresh])

  useEffect(() => {
    if (!validKbId) {
      return
    }
    let cancelled = false
    void (async () => {
      try {
        const list = await listKnowledgeBases()
        if (!cancelled) {
          setKbName(list.find((item) => item.id === kbId)?.name ?? '')
        }
      } catch {
        // 知识库名称仅用于展示，加载失败时使用兜底标题，不影响文档列表
        if (!cancelled) {
          setKbName('')
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [kbId, validKbId])

  // 有文档处于处理中时轮询刷新状态
  const hasProcessing = documents.some((item) => item.status === 'processing')
  useEffect(() => {
    if (!hasProcessing) {
      return
    }
    const timer = window.setInterval(() => {
      void refresh()
    }, POLL_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [hasProcessing, refresh])

  async function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    // 重置 input，保证同一文件可再次上传
    event.target.value = ''
    if (!file || !validKbId) {
      return
    }
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      setHint(`文件大小不能超过 ${MAX_UPLOAD_MB}MB`)
      return
    }

    setUploading(true)
    setUploadPercent(0)
    setHint('')
    try {
      await uploadDocument(kbId, file, setUploadPercent)
      await refresh()
    } catch (error) {
      setHint(error instanceof ApiError ? error.message : '上传失败，请稍后重试')
    } finally {
      setUploading(false)
      setUploadPercent(0)
    }
  }

  async function openChunks(document: DocumentItem) {
    setChunkTarget(document)
    setChunks([])
    setChunksHint('')
    setChunksLoading(true)
    try {
      setChunks(await listDocumentChunks(document.id))
    } catch (error) {
      setChunksHint(error instanceof ApiError ? error.message : '加载分块失败')
    } finally {
      setChunksLoading(false)
    }
  }

  async function handleDelete() {
    if (!deleteTarget) {
      return
    }
    setDeleting(true)
    try {
      await deleteDocument(deleteTarget.id)
      if (chunkTarget?.id === deleteTarget.id) {
        setChunkTarget(null)
      }
      setDeleteTarget(null)
      await refresh()
    } catch (error) {
      setHint(error instanceof ApiError ? error.message : '删除失败，请稍后重试')
      setDeleteTarget(null)
    } finally {
      setDeleting(false)
    }
  }

  if (!validKbId) {
    return (
      <section>
        <p className="text-sm text-danger">知识库 ID 非法</p>
        <Link to="/kb" className="mt-3 inline-block text-sm text-primary hover:underline">
          返回知识库列表
        </Link>
      </section>
    )
  }

  return (
    <section>
      <div className="mb-6">
        <Link to="/kb" className="text-sm text-primary hover:underline">
          ← 返回知识库列表
        </Link>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold text-text">{kbName || `知识库 #${kbId}`}</h1>
            <p className="mt-1 text-sm text-text-muted">
              支持 PDF / DOCX / MD / TXT，单文件不超过 {MAX_UPLOAD_MB}MB，上传后自动解析分块并向量化
            </p>
          </div>
          <div>
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPT_TYPES}
              className="hidden"
              onChange={handleUpload}
            />
            <button
              type="button"
              disabled={uploading}
              onClick={() => fileInputRef.current?.click()}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-60"
            >
              {uploading ? `上传中 ${uploadPercent}%` : '上传文档'}
            </button>
          </div>
        </div>
        {uploading && (
          <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-surface-muted">
            <div
              className="h-full rounded-full bg-primary transition-all"
              style={{ width: `${uploadPercent}%` }}
            />
          </div>
        )}
      </div>

      {hint && <p className="mb-4 text-sm text-danger">{hint}</p>}

      {loading ? (
        <div className="rounded-lg border border-border bg-surface p-10 text-center text-sm text-text-muted">
          加载中…
        </div>
      ) : documents.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border bg-surface p-10 text-center text-sm text-text-muted">
          暂无文档，点击右上角「上传文档」开始
        </div>
      ) : (
        <ul className="space-y-3">
          {documents.map((document) => (
            <li
              key={document.id}
              className="rounded-lg border border-border bg-surface px-5 py-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-text">{document.filename}</p>
                  <p className="mt-1 text-xs text-text-muted">
                    {document.file_type.toUpperCase()} · {format_file_size(document.file_size)} · 上传于{' '}
                    {document.create_time}
                    {document.status === 'completed' && ` · 分块数 ${document.chunk_count}`}
                  </p>
                  {document.status === 'failed' && document.error_message && (
                    <p className="mt-1 text-xs text-danger">失败原因：{document.error_message}</p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded-full px-2.5 py-1 text-xs ${STATUS_CLASS[document.status]}`}
                  >
                    {STATUS_TEXT[document.status]}
                  </span>
                  <button
                    type="button"
                    disabled={document.status === 'processing'}
                    onClick={() => void openChunks(document)}
                    className="rounded-md border border-border px-3 py-1.5 text-sm text-text-muted transition-colors hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    查看分块
                  </button>
                  <button
                    type="button"
                    onClick={() => setDeleteTarget(document)}
                    className="rounded-md border border-danger px-3 py-1.5 text-sm text-danger transition-colors hover:bg-danger-light"
                  >
                    删除
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      <Drawer
        title={chunkTarget ? `分块查看 · ${chunkTarget.filename}` : '分块查看'}
        open={chunkTarget !== null}
        onClose={() => setChunkTarget(null)}
      >
        {chunksLoading ? (
          <p className="text-sm text-text-muted">加载中…</p>
        ) : chunksHint ? (
          <p className="text-sm text-danger">{chunksHint}</p>
        ) : chunks.length === 0 ? (
          <p className="text-sm text-text-muted">暂无分块</p>
        ) : (
          <ol className="space-y-3">
            {chunks.map((chunk) => (
              <li key={chunk.id} className="rounded-lg border border-border bg-surface-muted p-4">
                <p className="text-xs text-text-muted">
                  片段 {chunk.chunk_index + 1} · {chunk.content.length} 字
                </p>
                <p className="mt-2 whitespace-pre-wrap break-words text-sm text-text">
                  {chunk.content}
                </p>
              </li>
            ))}
          </ol>
        )}
      </Drawer>

      <Modal
        title="删除文档"
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
      >
        <p className="text-sm text-text">
          确定删除「{deleteTarget?.filename}」吗？其全部 {deleteTarget?.chunk_count ?? 0}{' '}
          个分块与向量记录将被一并删除，且不可恢复。
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
            disabled={deleting}
            onClick={handleDelete}
            className="rounded-md bg-danger px-4 py-2 text-sm font-medium text-white transition-colors hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {deleting ? '删除中…' : '确认删除'}
          </button>
        </div>
      </Modal>
    </section>
  )
}
