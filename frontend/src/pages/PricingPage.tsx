import { useState } from 'react'
import NavBar from '../components/NavBar'
import { useUser } from '../hooks/useUser'

const FREE_FEATURES = [
  'IDLE & WATCH signals (delayed 24h)',
  '1 game (Pokémon)',
  '1 watchlist slot',
  'Card detail pages with full price history',
]

const PLUS_FEATURES = [
  'Everything in Free',
  'Real-time BREAKOUT & MOVE signals',
  'All 3 games (Pokémon, YGO, One Piece)',
  'Discord DMs on every signal',
  'Unlimited watchlist',
  '1-sentence AI signal explanation',
  '14-day free trial — no card required',
]

const PRO_FEATURES = [
  'Everything in Plus',
  'Full AI analysis — drivers, risks, thesis',
  'Japanese lead signals (4–8 week advance)',
  'Pre-grading ROI calculator',
  'Portfolio analytics & P&L tracking',
  'API access for personal automation',
]

const FAQ: { q: string; a: string }[] = [
  {
    q: 'Is there a free trial?',
    a: '14 days of full Plus access, no credit card required. When your trial ends you drop to the Free tier automatically. Upgrade any time during or after.',
  },
  {
    q: 'What are the founders prices?',
    a: 'The first 100 Plus subscribers lock in at $7/month for life. The first 50 Pro subscribers lock in at $20/month for life. Founders pricing is permanent — it never expires.',
  },
  {
    q: 'What happens if I cancel?',
    a: 'You keep access until the end of your billing period. Your watchlist and settings are saved for 90 days — resubscribe and everything is exactly where you left it.',
  },
  {
    q: 'What currencies do you accept?',
    a: 'We bill in USD. LemonSqueezy (our payment provider) automatically shows your local currency at checkout.',
  },
]

export default function PricingPage() {
  const { tier } = useUser()
  const [loading, setLoading] = useState(false)

  async function handleStartTrial() {
    setLoading(true)
    try {
      const resp = await fetch('/api/v1/trial/start', {
        method: 'POST',
        credentials: 'include',
      })
      if (!resp.ok) {
        window.location.href = '/login'
        return
      }
      const data = await resp.json()
      if (data.status === 'started') {
        window.location.href = '/market'
      } else {
        await handleCheckout('plus')
      }
    } finally {
      setLoading(false)
    }
  }

  async function handleCheckout(variant: 'plus' | 'pro') {
    const resp = await fetch(`/api/v1/account/checkout-url?variant=${variant}`, {
      credentials: 'include',
    })
    if (!resp.ok) {
      window.location.href = '/?upgrade=1'
      return
    }
    const { checkout_url } = await resp.json()
    window.location.href = checkout_url
  }

  const isFree = !tier || tier === 'free'
  const isPlus = tier === 'plus'
  const isPro = tier === 'pro'

  return (
    <div>
      <NavBar />
      <div className="page-content" style={{ maxWidth: 940, margin: '0 auto', padding: '40px 24px' }}>
        {/* Hero */}
        <div style={{ textAlign: 'center', marginBottom: 48 }}>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 36, fontWeight: 700, marginBottom: 12 }}>
            Signal intelligence for TCG investors.
          </h1>
          <p style={{ fontSize: 16, color: 'var(--text-secondary)' }}>
            Start free. Upgrade when the edge matters.
          </p>
        </div>

        {/* Plan cards — 3 column */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 20, marginBottom: 48 }}>

          {/* Free */}
          <div className="surface" style={{ padding: 24 }}>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 700, marginBottom: 4 }}>
              Free
            </div>
            <div style={{ fontSize: 28, fontWeight: 700, marginBottom: 20 }}>$0</div>
            <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 24px', display: 'flex', flexDirection: 'column', gap: 10 }}>
              {FREE_FEATURES.map(f => (
                <li key={f} style={{ display: 'flex', gap: 8, fontSize: 13, color: 'var(--text-secondary)' }}>
                  <span style={{ color: 'var(--breakout)', flexShrink: 0 }}>✓</span>
                  {f}
                </li>
              ))}
            </ul>
            {isFree ? (
              <div
                className="btn btn-ghost"
                style={{ width: '100%', justifyContent: 'center', cursor: 'default' }}
              >
                Current plan
              </div>
            ) : null}
          </div>

          {/* Plus — highlighted */}
          <div
            className="surface"
            style={{ padding: 24, border: '1px solid var(--gold)', boxShadow: '0 0 32px var(--gold-glow)' }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 700 }}>Plus</div>
              <span style={{ fontSize: 11, background: 'var(--gold)', color: '#000', padding: '2px 8px', borderRadius: 4, fontWeight: 700 }}>
                POPULAR
              </span>
            </div>
            <div style={{ marginBottom: 2 }}>
              <span style={{ fontSize: 28, fontWeight: 700 }}>$9.99</span>
              <span style={{ fontSize: 13, color: 'var(--text-muted)', marginLeft: 4 }}>/month</span>
            </div>
            <div style={{ fontSize: 12, color: 'var(--gold)', marginBottom: 20 }}>
              Founders: first 100 subscribers lock in at $7/mo for life
            </div>
            <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 24px', display: 'flex', flexDirection: 'column', gap: 10 }}>
              {PLUS_FEATURES.map(f => (
                <li key={f} style={{ display: 'flex', gap: 8, fontSize: 13 }}>
                  <span style={{ color: 'var(--gold)', flexShrink: 0 }}>✓</span>
                  {f}
                </li>
              ))}
            </ul>
            {isPlus ? (
              <div
                className="btn btn-ghost"
                style={{ width: '100%', justifyContent: 'center', cursor: 'default' }}
              >
                Current plan
              </div>
            ) : isPro ? null : (
              <button
                className="btn btn-primary"
                style={{ width: '100%', justifyContent: 'center' }}
                disabled={loading}
                onClick={handleStartTrial}
              >
                {loading ? 'Loading…' : 'Start 14-day free trial →'}
              </button>
            )}
          </div>

          {/* Pro */}
          <div className="surface" style={{ padding: 24 }}>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 700, marginBottom: 4 }}>
              Pro
            </div>
            <div style={{ marginBottom: 2 }}>
              <span style={{ fontSize: 28, fontWeight: 700 }}>$30</span>
              <span style={{ fontSize: 13, color: 'var(--text-muted)', marginLeft: 4 }}>/month</span>
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 20 }}>
              Founders: first 50 subscribers lock in at $20/mo for life
            </div>
            <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 24px', display: 'flex', flexDirection: 'column', gap: 10 }}>
              {PRO_FEATURES.map(f => (
                <li key={f} style={{ display: 'flex', gap: 8, fontSize: 13, color: 'var(--text-secondary)' }}>
                  <span style={{ color: 'var(--breakout)', flexShrink: 0 }}>✓</span>
                  {f}
                </li>
              ))}
            </ul>
            {isPro ? (
              <div
                className="btn btn-ghost"
                style={{ width: '100%', justifyContent: 'center', cursor: 'default' }}
              >
                Current plan
              </div>
            ) : (
              <button
                className="btn btn-ghost"
                style={{ width: '100%', justifyContent: 'center' }}
                disabled={loading}
                onClick={() => handleCheckout('pro')}
              >
                {loading ? 'Loading…' : 'Upgrade to Pro →'}
              </button>
            )}
          </div>
        </div>

        {/* FAQ */}
        <div style={{ maxWidth: 600, margin: '0 auto' }}>
          <h2
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 20,
              fontWeight: 700,
              marginBottom: 24,
            }}
          >
            Common questions
          </h2>
          {FAQ.map(({ q, a }) => (
            <div key={q} style={{ marginBottom: 28 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>{q}</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>{a}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
