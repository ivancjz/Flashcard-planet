import { useEffect, useRef, useState } from 'react'
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

type WaitlistState = 'idle' | 'loading' | 'joined' | 'already_joined' | 'error'

export default function LandingPage() {
  const nav = useNavigate()
  const [stats, setStats] = useState<MarketStats | null>(null)
  const [ticker, setTicker] = useState<TickerItem[]>([])
  const [waitlistEmail, setWaitlistEmail] = useState('')
  const [waitlistState, setWaitlistState] = useState<WaitlistState>('idle')
  const waitlistInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    fetchStats().then(setStats)
    fetchTicker().then(setTicker)
  }, [])

  async function handleWaitlistSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!waitlistEmail) return
    setWaitlistState('loading')
    try {
      const res = await fetch('/api/v1/waitlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: waitlistEmail, source_page: 'landing' }),
      })
      if (!res.ok) throw new Error('server_error')
      const data = await res.json()
      setWaitlistState(data.status === 'already_joined' ? 'already_joined' : 'joined')
    } catch {
      setWaitlistState('error')
    }
  }

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

        {/* Plans */}
        <div id="plus" style={{ marginTop: 80, scrollMarginTop: 80 }}>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 700, marginBottom: 8, textAlign: 'center' }}>
            Simple pricing
          </h2>
          <p style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: 14, marginBottom: 40 }}>
            Start free. Upgrade when you need more.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 24, maxWidth: 720, margin: '0 auto' }}>
            {/* Free */}
            <div className="surface" style={{ padding: 28 }}>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 700, marginBottom: 4 }}>Free</div>
              <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 24 }}>Everything you need to start.</div>
              {['Market signals for all cards', 'TCGPlayer + eBay prices', 'Discord alerts', 'Price history charts'].map(f => (
                <div key={f} style={{ display: 'flex', gap: 8, marginBottom: 10, fontSize: 13 }}>
                  <span style={{ color: 'var(--breakout)' }}>✓</span>
                  <span style={{ color: 'var(--text-secondary)' }}>{f}</span>
                </div>
              ))}
              {['AI trend analysis', 'Cross-game signals', 'Volume sort & advanced filters'].map(f => (
                <div key={f} style={{ display: 'flex', gap: 8, marginBottom: 10, fontSize: 13 }}>
                  <span style={{ color: 'var(--text-muted)' }}>—</span>
                  <span style={{ color: 'var(--text-muted)' }}>{f}</span>
                </div>
              ))}
              <button className="btn btn-ghost" style={{ width: '100%', justifyContent: 'center', marginTop: 24 }} onClick={() => nav('/market')}>
                Start free
              </button>
            </div>

            {/* Pro */}
            <div className="surface" style={{ padding: 28, border: '1px solid var(--gold)', boxShadow: '0 0 32px var(--gold-glow)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                <div style={{ fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 700 }}>Pro</div>
                <span style={{ fontSize: 9, fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--gold)', background: 'var(--gold-glow)', border: '1px solid rgba(240,180,41,0.3)', borderRadius: 10, padding: '2px 7px' }}>COMING SOON</span>
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 24 }}>For serious TCG investors.</div>
              {[
                'Everything in Free',
                'AI-powered trend analysis per card',
                'Cross-game Franchise signals',
                'Advanced sorting & filters',
                'Priority Discord alerts',
                'Early access to new games',
              ].map(f => (
                <div key={f} style={{ display: 'flex', gap: 8, marginBottom: 10, fontSize: 13 }}>
                  <span style={{ color: 'var(--gold)' }}>✓</span>
                  <span style={{ color: 'var(--text-secondary)' }}>{f}</span>
                </div>
              ))}
              {waitlistState === 'joined' || waitlistState === 'already_joined' ? (
                <div style={{ marginTop: 24, padding: '10px 16px', borderRadius: 6, background: 'var(--gold-glow)', border: '1px solid rgba(240,180,41,0.4)', textAlign: 'center' }}>
                  <span style={{ color: 'var(--gold)', fontWeight: 700, fontSize: 13 }}>
                    {waitlistState === 'already_joined' ? "You're already on the list." : "You're on the list — we'll be in touch."}
                  </span>
                </div>
              ) : (
                <form onSubmit={handleWaitlistSubmit} style={{ marginTop: 24 }}>
                  <input
                    ref={waitlistInputRef}
                    type="email"
                    required
                    placeholder="your@email.com"
                    value={waitlistEmail}
                    onChange={e => setWaitlistEmail(e.target.value)}
                    style={{
                      width: '100%', boxSizing: 'border-box', padding: '9px 12px',
                      borderRadius: 6, border: '1px solid rgba(240,180,41,0.4)',
                      background: '#1a1a1a', color: '#f0f0f0', fontSize: 13,
                      marginBottom: 8, outline: 'none',
                    }}
                  />
                  <button
                    type="submit"
                    disabled={waitlistState === 'loading'}
                    style={{
                      width: '100%', padding: '10px 16px', borderRadius: 6,
                      background: 'var(--gold-glow)', border: '1px solid rgba(240,180,41,0.4)',
                      color: 'var(--gold)', fontWeight: 700, fontSize: 13,
                      cursor: waitlistState === 'loading' ? 'wait' : 'pointer',
                      fontFamily: 'var(--font-display)',
                    }}
                  >
                    {waitlistState === 'loading' ? 'Joining…' : 'Join the waitlist →'}
                  </button>
                  {waitlistState === 'error' && (
                    <p style={{ color: '#e55', fontSize: 12, marginTop: 6, textAlign: 'center' }}>
                      Something went wrong — try again.
                    </p>
                  )}
                </form>
              )}
            </div>
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
