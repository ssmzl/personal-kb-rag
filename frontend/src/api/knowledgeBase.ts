import http from '@/api/client'
import type { ApiResponse } from '@/types/api'

export interface KnowledgeBaseItem {
  id: number
  name: string
  /** 库内文档数 */
  document_count: number
  /** 格式：yyyy-MM-dd HH:mm:ss */
  create_time: string
  update_time: string
}

/** 获取当前用户知识库列表（含文档数） */
export async function listKnowledgeBases(): Promise<KnowledgeBaseItem[]> {
  const { data } = await http.get<ApiResponse<KnowledgeBaseItem[]>>('/knowledge-bases')
  return data.data ?? []
}

/** 创建知识库 */
export async function createKnowledgeBase(name: string): Promise<KnowledgeBaseItem> {
  const { data } = await http.post<ApiResponse<KnowledgeBaseItem>>('/knowledge-bases', { name })
  if (!data.data) {
    throw new Error('创建知识库返回数据为空')
  }
  return data.data
}

/** 重命名知识库 */
export async function renameKnowledgeBase(id: number, name: string): Promise<void> {
  await http.put<ApiResponse<KnowledgeBaseItem>>(`/knowledge-bases/${id}`, { name })
}

/** 删除知识库（级联删除其下文档与分块） */
export async function deleteKnowledgeBase(id: number): Promise<void> {
  await http.delete<ApiResponse<null>>(`/knowledge-bases/${id}`)
}
