export default function KnowledgeBasePage() {
  return (
    <section>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-text">知识库</h1>
          <p className="mt-1 text-sm text-text-muted">创建、重命名、删除知识库以及查看文档数</p>
        </div>
        <button
          type="button"
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-hover"
        >
          新建知识库
        </button>
      </div>

      <div className="rounded-lg border border-dashed border-border bg-surface p-10 text-center text-sm text-text-muted">
        暂无知识库，知识库管理能力将在后续任务接入
      </div>
    </section>
  )
}
