import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './styles/theme.css'
import LandingPage from './pages/LandingPage'
import DashboardPage from './pages/DashboardPage'
import CardDetailPage from './pages/CardDetailPage'
import AlertsPage from './pages/AlertsPage'
import WatchlistPage from './pages/WatchlistPage'
import PortfolioPage from './pages/PortfolioPage'
import ComparePage from './pages/ComparePage'
import AccountPage from './pages/AccountPage'
import DigestPreferencesPage from './pages/DigestPreferencesPage'
import PricingPage from './pages/PricingPage'
import SealedPage from './pages/SealedPage'
import DevTierSwitcher from './components/DevTierSwitcher'
import { UserProvider } from './contexts/UserContext'
import PublicCallsLayout from './pages/calls/PublicCallsLayout'
import CallsPage from './pages/calls/CallsPage'
import MethodologyPage from './pages/calls/MethodologyPage'
import DailyReportsPage from './pages/DailyReportsPage'
import DailyReportDetailPage from './pages/DailyReportDetailPage'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <UserProvider>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/market" element={<DashboardPage />} />
        <Route path="/market/:assetId" element={<CardDetailPage />} />
        <Route path="/alerts" element={<AlertsPage />} />
        <Route path="/watchlist" element={<WatchlistPage />} />
        <Route path="/portfolio" element={<PortfolioPage />} />
        <Route path="/compare" element={<ComparePage />} />
        <Route path="/account" element={<AccountPage />} />
        <Route path="/account/digest-preferences" element={<DigestPreferencesPage />} />
        <Route path="/pricing" element={<PricingPage />} />
        <Route path="/sealed" element={<SealedPage />} />
        <Route path="/reports" element={<DailyReportsPage />} />
        <Route path="/reports/:reportDate" element={<DailyReportDetailPage />} />
        <Route path="/calls" element={<PublicCallsLayout />}>
          <Route index element={<CallsPage />} />
        </Route>
        <Route path="/methodology" element={<PublicCallsLayout />}>
          <Route index element={<MethodologyPage />} />
        </Route>
      </Routes>
      <DevTierSwitcher />
    </BrowserRouter>
    </UserProvider>
  </StrictMode>
)
