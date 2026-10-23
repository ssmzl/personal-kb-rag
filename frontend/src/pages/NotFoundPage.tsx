import { Link } from 'react-router-dom'

export default function NotFoundPage() {
  return (
    <section className="py-16 text-center">
      <h1 className="text-2xl font-semibold text-text">页面不存在</h1>
      <p className="mt-2 text-sm text-text-muted">请检查地址是否正确</p>
      <Link
        to="/kb"
        className="mt-6 inline-block rounded-md bg-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-hover"
      >
        返回知识库
      </Link>
    </section>
  )
}
