import axios, { type AxiosError } from 'axios'

import type { ApiResponse } from '@/types/api'

export const TOKEN_STORAGE_KEY = 'kb_token'

/** 统一的接口错误：code 为 0 以外的业务码或 HTTP 状态码 */
export class ApiError extends Error {
  readonly code: number

  constructor(code: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.code = code
  }
}

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '/api',
  timeout: 30000,
})

http.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (response) => {
    const body = response.data as ApiResponse<unknown> | undefined
    if (body && typeof body.code === 'number' && body.code !== 0) {
      return Promise.reject(new ApiError(body.code, body.message))
    }
    return response
  },
  (error: AxiosError<ApiResponse<unknown>>) => {
    if (error.response?.status === 401) {
      localStorage.removeItem(TOKEN_STORAGE_KEY)
      if (window.location.pathname !== '/login') {
        window.location.assign('/login')
      }
      return Promise.reject(new ApiError(401, '登录已失效，请重新登录'))
    }

    const body = error.response?.data
    return Promise.reject(new ApiError(body?.code ?? -1, body?.message ?? error.message ?? '请求失败'))
  },
)

export default http
