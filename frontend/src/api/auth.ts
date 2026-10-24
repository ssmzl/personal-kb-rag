import http, { TOKEN_STORAGE_KEY } from '@/api/client'
import type { ApiResponse } from '@/types/api'

export interface LoginData {
  token: string
  token_type: string
  /** 有效期（秒） */
  expires_in: number
  username: string
}

export interface CurrentUserData {
  id: number
  username: string
}

/** 账号密码登录，成功后写入 token 到 localStorage */
export async function login(username: string, password: string): Promise<LoginData> {
  const { data } = await http.post<ApiResponse<LoginData>>('/auth/login', { username, password })
  if (!data.data) {
    throw new Error('登录返回数据为空')
  }
  localStorage.setItem(TOKEN_STORAGE_KEY, data.data.token)
  return data.data
}

/** 退出登录：清除本地 token */
export function logout(): void {
  localStorage.removeItem(TOKEN_STORAGE_KEY)
}

/** 获取当前登录用户（校验 token 有效性） */
export async function getCurrentUser(): Promise<CurrentUserData> {
  const { data } = await http.get<ApiResponse<CurrentUserData>>('/auth/me')
  if (!data.data) {
    throw new Error('用户信息返回为空')
  }
  return data.data
}
