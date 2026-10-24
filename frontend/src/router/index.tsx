import type { ReactNode } from 'react'
import { createBrowserRouter, Navigate } from 'react-router-dom'

import { TOKEN_STORAGE_KEY } from '@/api/client'
import AppLayout from '@/components/layout/AppLayout'
import ChatPage from '@/pages/ChatPage'
import DocumentPage from '@/pages/DocumentPage'
import KnowledgeBasePage from '@/pages/KnowledgeBasePage'
import LoginPage from '@/pages/LoginPage'
import NotFoundPage from '@/pages/NotFoundPage'

/** 路由守卫：未携带 token 时跳转登录页 */
function RequireAuth({ children }: { children: ReactNode }) {
  if (!localStorage.getItem(TOKEN_STORAGE_KEY)) {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}

/** 已登录时访问登录页直接回主页 */
function RedirectIfAuthed({ children }: { children: ReactNode }) {
  if (localStorage.getItem(TOKEN_STORAGE_KEY)) {
    return <Navigate to="/kb" replace />
  }
  return <>{children}</>
}

export const router = createBrowserRouter([
  {
    path: '/login',
    element: (
      <RedirectIfAuthed>
        <LoginPage />
      </RedirectIfAuthed>
    ),
  },
  {
    path: '/',
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Navigate to="/kb" replace /> },
      { path: 'kb', element: <KnowledgeBasePage /> },
      { path: 'kb/:kbId/documents', element: <DocumentPage /> },
      { path: 'chat', element: <ChatPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
