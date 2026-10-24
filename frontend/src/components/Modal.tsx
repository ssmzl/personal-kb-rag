import type { ReactNode } from 'react'

interface ModalProps {
  title: string
  open: boolean
  onClose: () => void
  children: ReactNode
}

/** 通用弹窗：遮罩点击关闭，内容区阻止冒泡 */
export default function Modal({ title, open, onClose, children }: ModalProps) {
  if (!open) {
    return null
  }
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-xl border border-border bg-surface p-6 shadow-lg"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-text">{title}</h2>
        <div className="mt-4">{children}</div>
      </div>
    </div>
  )
}
