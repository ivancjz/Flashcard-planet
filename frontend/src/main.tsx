import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './styles/theme.css'
import LandingPage from './pages/LandingPage'
import DashboardPage from './pages/DashboardPage'
import CardDetailPage from './pages/CardDetailPage'
import AlertsPage from './pages/AlertsPage'
import WatchlistPage from './pages/WatchlistPage'
import ComparePage from './pages/ComparePage'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/market" element={<DashboardPage />} />
        <Route path="/market/:assetId" element={<CardDetailPage />} />
        <Route path="/alerts" element={<AlertsPage />} />
        <Route path="/watchlist" element={<WatchlistPage />} />
        <Route path="/compare" element={<ComparePage />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>
)
