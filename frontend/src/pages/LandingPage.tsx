import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import TickerBar from '../components/TickerBar'
import CardArt from '../components/CardArt'
import { fetchStats, fetchTicker } from '../api/api'
import type { MarketStats, TickerItem } from '../types/api'

const FEATURES = [
  { icon: '📊', title: 'Dual-source Data', desc: 'TCGPlayer market price + eBay sold listings, reconciled daily.' },
  { icon: '⚡', title: 'Signal Engine', desc: 'BREAKOUT / MOVE / WATCH / IDLE labels computed every ingest run.' },
  { icon: '🔔', title: 'Price Alerts', desc: 'Signal change notifications when a card moves to BREAKOUT or MOVE.' },
  { icon: '📈', title: 'Price History', desc: '30-day rolling price chart per card from both sources.' },
]

export default function LandingPage() {
  const nav = useNavigate()
  const [stats, setStats] = useState<MarketStats | null>(null)
  const [ticker, setTicker] = useState<TickerItem[]>([])

  useEffect(() => {
    fetchStats().then(setStats)
    fetchTicker().then(setTicker)
  }, [])

  return (
    <div style={{ minHeight: '100vh' }}>
      {/* Minimal header */}
      <nav className="nav">
        <div className="nav-logo">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <polygon points="10,1 12.9,7 19.5,7.6 14.8,11.8 16.2,18.2 10,15 3.8,18.2 5.2,11.8 0.5,7.6 7.1,7" fill="#f0b429" />
          </svg>
          Flashcard Planet
          <span className="nav-logo-sub">闪卡星球</span>
        </div>
        <div className="nav-links">
          <span className="nav-link" onClick={() => nav('/market')}>Market</span>
          <span className="nav-link" onClick={() => nav('/alerts')}>Alerts</span>
        </div>
      </nav>

      <TickerBar items={ticker} />

      {/* Hero */}
      <div className="page-content" style={{ paddingTop: 60 }}>
        <div className="landing-hero-grid">
          {/* Left */}
          <div className="fade-up">
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 16 }}>
              ● Live · Pokemon TCG
            </div>
            <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 52, fontWeight: 800, lineHeight: 1.1, letterSpacing: '-0.03em', marginBottom: 24 }}>
              TCG Price<br />
              <span style={{ color: 'var(--gold)' }}>Intelligence</span><br />
              Platform
            </h1>
            <p style={{ fontSize: 16, color: 'var(--text-secondary)', lineHeight: 1.6, maxWidth: 460, marginBottom: 32 }}>
              Track Pokemon TCG card prices across TCGPlayer and eBay. Get signal alerts before the market moves.
            </p>

            {/* Stats row */}
            {stats && (
              <div style={{ display: 'flex', gap: 32, marginBottom: 40, flexWrap: 'wrap' }}>
                {[
                  { label: 'Cards tracked', value: stats.total_assets.toLocaleString() },
                  { label: 'Breakout signals', value: stats.signal_counts.BREAKOUT },
                  { label: 'Data sources', value: stats.sources_active.length },
                  { label: 'Ingest interval', value: '24h' },
                ].map(({ label, value }) => (
                  <div key={label}>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>{value}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{label}</div>
                  </div>
                ))}
              </div>
            )}

            <div style={{ display: 'flex', gap: 12 }}>
              <button className="btn btn-primary" onClick={() => nav('/market')}>View Market →</button>
              <button className="btn btn-ghost" onClick={() => nav('/alerts')}>Price Alerts</button>
            </div>
          </div>

          {/* Right — floating cards */}
          <div style={{ position: 'relative', height: 340 }}>
            <div className="float" style={{ position: 'absolute', top: 0, left: 20 }}>
              <CardArt name="Charizard ex" type="Fire" rarity="ultra" size="md" />
            </div>
            <div className="float-2" style={{ position: 'absolute', top: 60, left: 130 }}>
              <CardArt name="Umbreon VMAX" type="Dark" rarity="secret" size="md" />
            </div>
            <div className="float-3" style={{ position: 'absolute', top: 30, left: 80, zIndex: -1, opacity: 0.6 }}>
              <CardArt name="Giratina VSTAR" type="Dragon" rarity="holo" size="sm" />
            </div>
          </div>
        </div>

        {/* Feature grid */}
        <div style={{ marginTop: 80 }}>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 700, marginBottom: 32, textAlign: 'center' }}>
            Built for serious collectors
          </h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 16 }}>
            {FEATURES.map(f => (
              <div key={f.title} className="surface" style={{ padding: 24 }}>
                <div style={{ fontSize: 28, marginBottom: 12 }}>{f.icon}</div>
                <h3 style={{ fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 600, marginBottom: 8 }}>{f.title}</h3>
                <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>{f.desc}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Footer CTA */}
        <div style={{ marginTop: 80, textAlign: 'center' }}>
          <div style={{ display: 'flex', gap: 12, justifyContent: 'center', marginBottom: 24 }}>
            <span className="badge badge-breakout">Pokémon · Live</span>
            <span className="badge badge-idle">Yu-Gi-Oh · Coming soon</span>
            <span className="badge badge-idle">MTG · Coming soon</span>
          </div>
          <button className="btn btn-primary" style={{ fontSize: 15, padding: '12px 32px' }} onClick={() => nav('/market')}>
            Explore the Market
          </button>
        </div>
      </div>
    </div>
  )
}
