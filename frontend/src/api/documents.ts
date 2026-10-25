import http from '@/api/client'
import type { ApiResponse } from '@/types/api'

export type DocumentStatus = 'pending' | 'processing' | 'completed' | 'failed'

/** 分块策略，需与后端 ChunkStrategy 枚举值保持一致 */
export type ChunkStrategy = 'paragraph' | 'fixed' | 'sentence' | 'markdown'

export interface DocumentItem {
  id: number
  kb_id: number
  filename: string
  file_type: string
  file_size: number
  status: DocumentStatus
  error_message: string | null
  chunk_count: number
  /** 格式：yyyy-MM-dd HH:mm:ss */
  create_time: string
  update_time: string
}

export interface DocumentChunkItem {
  id: number
  chunk_index: number
  content: string
  /** 格式：yyyy-MM-dd HH:mm:ss */
  create_time: string
}

/** 获取知识库下的文档列表（含处理状态） */
export async function listDocuments(kbId: number): Promise<DocumentItem[]> {
  const { data } = await http.get<ApiResponse<DocumentItem[]>>(`/knowledge-bases/${kbId}/documents`)
  return data.data ?? []
}

/** 上传文档（仅保存文件），onProgress 回调返回上传百分比（0-100） */
export async function uploadDocument(
  kbId: number,
  file: File,
  onProgress?: (percent: number) => void,
): Promise<DocumentItem> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await http.post<ApiResponse<DocumentItem>>(
    `/knowledge-bases/${kbId}/documents`,
    form,
    {
      onUploadProgress: (event) => {
        if (onProgress && event.total) {
          onProgress(Math.round((event.loaded / event.total) * 100))
        }
      },
    },
  )
  if (!data.data) {
    throw new Error('上传文档返回数据为空')
  }
  return data.data
}

/** 按指定策略开始/重新分块并向量化 */
export async function chunkDocument(
  documentId: number,
  chunkStrategy: ChunkStrategy,
): Promise<DocumentItem> {
  const { data } = await http.post<ApiResponse<DocumentItem>>(`/documents/${documentId}/chunk`, {
    chunk_strategy: chunkStrategy,
  })
  if (!data.data) {
    throw new Error('启动分块返回数据为空')
  }
  return data.data
}

/** 获取文档全部分块文本 */
export async function listDocumentChunks(documentId: number): Promise<DocumentChunkItem[]> {
  const { data } = await http.get<ApiResponse<DocumentChunkItem[]>>(
    `/documents/${documentId}/chunks`,
  )
  return data.data ?? []
}

/** 删除文档（级联删除分块与向量） */
export async function deleteDocument(documentId: number): Promise<void> {
  await http.delete<ApiResponse<null>>(`/documents/${documentId}`)
}
