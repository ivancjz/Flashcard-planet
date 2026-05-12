import { useState } from 'react'
import NavBar from '../components/NavBar'
import { useUser } from '../hooks/useUser'

const FREE_FEATURES = [
  'Signal labels (BREAKOUT / MOVE / WATCH / IDLE)',
  'Up to 10 cards on your watchlist',
  'Up to 5 price alerts',
  'Card detail pages with full price history',
  '14-day free Pro trial — no credit card required',
]

const PRO_FEATURES = [
  'Everything in Free',
  'Confidence score on every signal',
  'AI-written explanation — know WHY a card is moving',
  'Unlimited watchlist',
  'Unlimited alerts',
  'Advanced sorting (Volume, Recent)',
  'CSV export',
  'Priority Discord alerts',
]

const FAQ: { q: string; a: string }[] = [
  {
    q: 'Is there a free trial?',
    a: '14 days of full Pro access, no credit card required. When your trial ends you automatically drop to the free tier. Upgrade any time during or after.',
  },
  {
    q: 'What happens if I cancel?',
    a: 'You keep Pro access until the end of your billing period. Your watchlist and alert settings are saved for 90 days — resubscribe and everything is exactly where you left it.',
  },
  {
    q: 'What currencies do you accept?',
    a: 'We bill in USD. LemonSqueezy (our payment provider) automatically shows your local currency at checkout.',
  },
  {
    q: 'Is there a money-back guarantee?',
    a: '14-day money-back guarantee, no questions asked. Email hello@flashcardplanet.com.',
  },
]

export default function PricingPage() {
  const { tier } = useUser()
  const [loading, setLoading] = useState(false)

  async function handleUpgrade() {
    setLoading(true)
    try {
      const resp = await fetch('/api/v1/account/checkout-url?variant=standard', {
        credentials: 'include',
      })
      if (!resp.ok) {
        window.location.href = '/?upgrade=1'
        return
      }
      const { checkout_url } = await resp.json()
      window.location.href = checkout_url
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <NavBar />
      <div className="page-content" style={{ maxWidth: 820, margin: '0 auto', padding: '40px 24px' }}>
        {/* Hero */}
        <div style={{ textAlign: 'center', marginBottom: 48 }}>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 36, fontWeight: 700, marginBottom: 12 }}>
            Simple pricing.
          </h1>
          <p style={{ fontSize: 16, color: 'var(--text-secondary)' }}>
            Start free. Upgrade when you need the edge.
          </p>
        </div>

        {/* Plan cards */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginBottom: 48 }}>
          {/* Free */}
          <div className="surface" style={{ padding: 28 }}>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 700, marginBottom: 4 }}>
              Free
            </div>
            <div style={{ fontSize: 32, fontWeight: 700, marginBottom: 20 }}>$0</div>
            <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 24px', display: 'flex', flexDirection: 'column', gap: 10 }}>
              {FREE_FEATURES.map(f => (
                <li key={f} style={{ display: 'flex', gap: 8, fontSize: 13, color: 'var(--text-secondary)' }}>
                  <span style={{ color: 'var(--breakout)', flexShrink: 0 }}>✓</span>
                  {f}
                </li>
              ))}
            </ul>
            {tier !== 'pro' && tier !== 'plus' && (
              <div
                className="btn btn-ghost"
                style={{ width: '100%', justifyContent: 'center', cursor: 'default' }}
              >
                Current plan
              </div>
            )}
          </div>

          {/* Pro */}
          <div
            className="surface"
            style={{ padding: 28, border: '1px solid var(--gold)', boxShadow: '0 0 32px var(--gold-glow)' }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 700 }}>Pro</div>
            </div>
            <div style={{ marginBottom: 4 }}>
              <span style={{ fontSize: 32, fontWeight: 700 }}>$12</span>
              <span style={{ fontSize: 14, color: 'var(--text-muted)', marginLeft: 4 }}>/month USD</span>
            </div>
            <div style={{ fontSize: 12, color: 'var(--gold)', marginBottom: 20 }}>
              Founders pricing: $9/month — limited spots
            </div>
            <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 24px', display: 'flex', flexDirection: 'column', gap: 10 }}>
              {PRO_FEATURES.map(f => (
                <li key={f} style={{ display: 'flex', gap: 8, fontSize: 13 }}>
                  <span style={{ color: 'var(--gold)', flexShrink: 0 }}>✓</span>
                  {f}
                </li>
              ))}
            </ul>
            {tier === 'pro' || tier === 'plus' ? (
              <div
                className="btn btn-ghost"
                style={{ width: '100%', justifyContent: 'center', cursor: 'default' }}
              >
                Current plan
              </div>
            ) : (
              <button
                className="btn btn-primary"
                style={{ width: '100%', justifyContent: 'center' }}
                disabled={loading}
                onClick={handleUpgrade}
              >
                {loading ? 'Loading…' : 'Start 14-day free trial →'}
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
