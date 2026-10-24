import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'

import { login } from '@/api/auth'
import { ApiError } from '@/api/client'

export default function LoginPage() {
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [hint, setHint] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmedUsername = username.trim()
    if (!trimmedUsername || !password) {
      setHint('请输入账号和密码')
      return
    }

    setSubmitting(true)
    setHint('')
    try {
      await login(trimmedUsername, password)
      navigate('/kb', { replace: true })
    } catch (error) {
      setHint(error instanceof ApiError ? error.message : '登录失败，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-muted px-4">
      <div className="w-full max-w-sm rounded-xl border border-border bg-surface p-8 shadow-sm">
        <h1 className="text-xl font-semibold text-text">登录个人知识库</h1>
        <p className="mt-1 text-sm text-text-muted">使用账号密码登录后管理知识库并提问</p>

        <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-text">账号</span>
            <input
              type="text"
              value={username}
              autoComplete="username"
              onChange={(event) => setUsername(event.target.value)}
              className="w-full rounded-md border border-border px-3 py-2 text-sm outline-none focus:border-primary"
              placeholder="请输入账号"
            />
          </label>

          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-text">密码</span>
            <input
              type="password"
              value={password}
              autoComplete="current-password"
              onChange={(event) => setPassword(event.target.value)}
              className="w-full rounded-md border border-border px-3 py-2 text-sm outline-none focus:border-primary"
              placeholder="请输入密码"
            />
          </label>

          {hint && <p className="text-sm text-danger">{hint}</p>}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting ? '登录中…' : '登录'}
          </button>
        </form>
      </div>
    </div>
  )
}
