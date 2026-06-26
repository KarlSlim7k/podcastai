import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import { AppLayout } from './components/layout/AppLayout'
import { Dashboard } from './pages/Dashboard'
import { ProjectsList } from './pages/ProjectsList'
import { ProjectDetail } from './pages/ProjectDetail'
import { SystemPage } from './pages/SystemPage'
import { VerticalEditorWindow } from './pages/VerticalEditorWindow'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 5_000,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/projects" element={<ProjectsList />} />
            <Route path="/projects/:id" element={<ProjectDetail />} />
            <Route path="/system" element={<SystemPage />} />
          </Route>
          {/* Standalone full-window editor — opened in a real browser popup
              via window.open(). No AppLayout (no sidebar) so it fills the
              popup. The popup is a separate browser context with its OWN
              React root and QueryClient; it stays in sync with the opener
              only through the shared backend (both windows poll the same
              API), which is all this editor needs. */}
          <Route path="/vertical-editor/:projectId/:clipId" element={<VerticalEditorWindow />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>
)
