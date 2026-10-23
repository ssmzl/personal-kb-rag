/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 后端接口基础地址，默认 /api（开发环境由 Vite 代理到后端） */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
