import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import NavBar from '../components/NavBar'
import { useUser } from '../contexts/UserContext'

type Frequency = 'daily' | 'weekly' | 'off'

export default function DigestPreferencesPage() {
  const { tier } = useUser()
  const nav = useNavigate()
  const [frequency, setFrequency] = useState<Frequency>('daily')
  const [lastSent, setLastSent] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (tier === 'free') {
      nav('/', { replace: true })
      return
    }
    fetch('/api/v1/account/digest-preferences')
      .then(r => r.json())
      .then(d => {
        setFrequency(d.digest_frequency ?? 'daily')
        setLastSent(d.last_digest_sent_at ?? null)
      })
      .finally(() => setLoading(false))
  }, [tier, nav])

  const save = async () => {
    setSaving(true)
    setSaved(false)
    await fetch('/api/v1/account/digest-preferences', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ digest_frequency: frequency }),
    })
    setSaving(false)
    setSaved(true)
  }

  if (loading) return <div><NavBar /><div className="page-content">Loading…</div></div>

  return (
    <div>
      <NavBar />
      <div className="page-content" style={{ maxWidth: 480 }}>
        <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 700, marginBottom: 4 }}>
          Market Digest
        </h1>
        <p style={{ color: 'var(--text-muted)', fontSize: 14, marginBottom: 24 }}>
          Sent at UTC 07:00 when there are active signals.
        </p>

        {(['daily', 'weekly', 'off'] as Frequency[]).map(opt => (
          <label key={opt} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14, cursor: 'pointer' }}>
            <input
              type="radio"
              name="freq"
              value={opt}
              checked={frequency === opt}
              onChange={() => setFrequency(opt)}
            />
            <span style={{ fontWeight: frequency === opt ? 600 : 400 }}>
              {opt === 'daily' && 'Daily — send when there are new signals'}
              {opt === 'weekly' && 'Weekly — at most once every 7 days'}
              {opt === 'off' && 'Off — no digest emails'}
            </span>
          </label>
        ))}

        <button
          className="btn btn-primary"
          style={{ marginTop: 8 }}
          onClick={save}
          disabled={saving}
        >
          {saving ? 'Saving…' : saved ? 'Saved ✓' : 'Save preferences'}
        </button>

        {lastSent && (
          <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 16 }}>
            Last digest sent: {new Date(lastSent).toLocaleString()}
          </p>
        )}
      </div>
    </div>
  )
}
