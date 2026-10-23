import { createBrowserRouter, Navigate } from 'react-router-dom'

import AppLayout from '@/components/layout/AppLayout'
import ChatPage from '@/pages/ChatPage'
import KnowledgeBasePage from '@/pages/KnowledgeBasePage'
import LoginPage from '@/pages/LoginPage'
import NotFoundPage from '@/pages/NotFoundPage'

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/kb" replace /> },
      { path: 'kb', element: <KnowledgeBasePage /> },
      { path: 'chat', element: <ChatPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
