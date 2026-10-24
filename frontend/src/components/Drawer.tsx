import type { ReactNode } from 'react'

interface DrawerProps {
  title: string
  open: boolean
  onClose: () => void
  children: ReactNode
}

/** 通用右侧抽屉：遮罩点击关闭，内容区阻止冒泡 */
export default function Drawer({ title, open, onClose, children }: DrawerProps) {
  if (!open) {
    return null
  }
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onClick={onClose}>
      <aside
        className="flex h-full w-full max-w-xl flex-col border-l border-border bg-surface shadow-lg"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="text-base font-semibold text-text">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-border px-3 py-1 text-sm text-text-muted transition-colors hover:bg-surface-muted"
          >
            关闭
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
      </aside>
    </div>
  )
}
