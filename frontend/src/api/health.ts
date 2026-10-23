import http from '@/api/client'
import type { ApiResponse } from '@/types/api'

export interface HealthData {
  status: string
  app: string
  version: string
}

/** 查询后端健康状态 */
export async function getHealth(): Promise<HealthData> {
  const { data } = await http.get<ApiResponse<HealthData>>('/health')
  if (!data.data) {
    throw new Error('健康检查返回数据为空')
  }
  return data.data
}
