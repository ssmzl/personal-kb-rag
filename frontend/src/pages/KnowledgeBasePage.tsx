import { useCallback, useEffect, useState, type FormEvent } from 'react'

import {
  createKnowledgeBase,
  deleteKnowledgeBase,
  listKnowledgeBases,
  renameKnowledgeBase,
  type KnowledgeBaseItem,
} from '@/api/knowledgeBase'
import { ApiError } from '@/api/client'
import Modal from '@/components/Modal'

export default function KnowledgeBasePage() {
  const [items, setItems] = useState<KnowledgeBaseItem[]>([])
  const [loading, setLoading] = useState(true)
  const [hint, setHint] = useState('')

  // 新建 / 重命名弹窗共用一个名称表单；deleteTarget 控制删除确认弹窗
  const [createOpen, setCreateOpen] = useState(false)
  const [renameTarget, setRenameTarget] = useState<KnowledgeBaseItem | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<KnowledgeBaseItem | null>(null)
  const [nameInput, setNameInput] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [modalHint, setModalHint] = useState('')

  const refresh = useCallback(async () => {
    try {
      const list = await listKnowledgeBases()
      setItems(list)
      setHint('')
    } catch (error) {
      setHint(error instanceof ApiError ? error.message : '加载知识库列表失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  function openCreateModal() {
    setNameInput('')
    setModalHint('')
    setCreateOpen(true)
  }

  function openRenameModal(kb: KnowledgeBaseItem) {
    setNameInput(kb.name)
    setModalHint('')
    setRenameTarget(kb)
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const name = nameInput.trim()
    if (!name) {
      setModalHint('请输入知识库名称')
      return
    }
    setSubmitting(true)
    setModalHint('')
    try {
      await createKnowledgeBase(name)
      setCreateOpen(false)
      await refresh()
    } catch (error) {
      setModalHint(error instanceof ApiError ? error.message : '创建失败，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleRename(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!renameTarget) {
      return
    }
    const name = nameInput.trim()
    if (!name) {
      setModalHint('请输入知识库名称')
      return
    }
    setSubmitting(true)
    setModalHint('')
    try {
      await renameKnowledgeBase(renameTarget.id, name)
      setRenameTarget(null)
      await refresh()
    } catch (error) {
      setModalHint(error instanceof ApiError ? error.message : '重命名失败，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDelete() {
    if (!deleteTarget) {
      return
    }
    setSubmitting(true)
    try {
      await deleteKnowledgeBase(deleteTarget.id)
      setDeleteTarget(null)
      await refresh()
    } catch (error) {
      setHint(error instanceof ApiError ? error.message : '删除失败，请稍后重试')
      setDeleteTarget(null)
    } finally {
      setSubmitting(false)
    }
  }

  const nameFormFields = (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-text">名称</span>
      <input
        type="text"
        value={nameInput}
        maxLength={128}
        autoFocus
        onChange={(event) => setNameInput(event.target.value)}
        className="w-full rounded-md border border-border px-3 py-2 text-sm outline-none focus:border-primary"
        placeholder="请输入知识库名称"
      />
    </label>
  )

  const modalActions = (onCancel: () => void, submitText: string) => (
    <div className="mt-6 flex justify-end gap-2">
      <button
        type="button"
        onClick={onCancel}
        className="rounded-md border border-border px-4 py-2 text-sm text-text-muted transition-colors hover:bg-surface-muted"
      >
        取消
      </button>
      <button
        type="submit"
        disabled={submitting}
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-60"
      >
        {submitting ? '提交中…' : submitText}
      </button>
    </div>
  )

  return (
    <section>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-text">知识库</h1>
          <p className="mt-1 text-sm text-text-muted">创建、重命名、删除知识库以及查看文档数</p>
        </div>
        <button
          type="button"
          onClick={openCreateModal}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-hover"
        >
          新建知识库
        </button>
      </div>

      {hint && <p className="mb-4 text-sm text-danger">{hint}</p>}

      {loading ? (
        <div className="rounded-lg border border-border bg-surface p-10 text-center text-sm text-text-muted">
          加载中…
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border bg-surface p-10 text-center text-sm text-text-muted">
          暂无知识库，点击右上角「新建知识库」开始
        </div>
      ) : (
        <ul className="space-y-3">
          {items.map((kb) => (
            <li
              key={kb.id}
              className="flex items-center justify-between rounded-lg border border-border bg-surface px-5 py-4"
            >
              <div>
                <p className="text-sm font-medium text-text">{kb.name}</p>
                <p className="mt-1 text-xs text-text-muted">
                  文档数 {kb.document_count} · 创建于 {kb.create_time}
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => openRenameModal(kb)}
                  className="rounded-md border border-border px-3 py-1.5 text-sm text-text-muted transition-colors hover:bg-surface-muted"
                >
                  重命名
                </button>
                <button
                  type="button"
                  onClick={() => setDeleteTarget(kb)}
                  className="rounded-md border border-danger px-3 py-1.5 text-sm text-danger transition-colors hover:bg-danger-light"
                >
                  删除
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <Modal title="新建知识库" open={createOpen} onClose={() => setCreateOpen(false)}>
        <form onSubmit={handleCreate}>
          {nameFormFields}
          {modalHint && <p className="mt-2 text-sm text-danger">{modalHint}</p>}
          {modalActions(() => setCreateOpen(false), '创建')}
        </form>
      </Modal>

      <Modal title="重命名知识库" open={renameTarget !== null} onClose={() => setRenameTarget(null)}>
        <form onSubmit={handleRename}>
          {nameFormFields}
          {modalHint && <p className="mt-2 text-sm text-danger">{modalHint}</p>}
          {modalActions(() => setRenameTarget(null), '保存')}
        </form>
      </Modal>

      <Modal title="删除知识库" open={deleteTarget !== null} onClose={() => setDeleteTarget(null)}>
        <p className="text-sm text-text">
          确定删除知识库「{deleteTarget?.name}」吗？其下全部文档与分块将被一并删除，且不可恢复。
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
            disabled={submitting}
            onClick={handleDelete}
            className="rounded-md bg-danger px-4 py-2 text-sm font-medium text-white transition-colors hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting ? '删除中…' : '确认删除'}
          </button>
        </div>
      </Modal>
    </section>
  )
}
