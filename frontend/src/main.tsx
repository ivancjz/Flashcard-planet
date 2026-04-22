import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './styles/theme.css'
import LandingPage from './pages/LandingPage'
import DashboardPage from './pages/DashboardPage'

function Placeholder({ name }: { name: string }) {
  return (
    <div style={{ padding: 40, color: 'var(--text-primary)' }}>
      <h1 style={{ fontFamily: 'var(--font-display)' }}>{name}</h1>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/market" element={<DashboardPage />} />
        <Route path="/market/:assetId" element={<Placeholder name="CardDetailPage" />} />
        <Route path="/alerts" element={<Placeholder name="AlertsPage" />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>
)
