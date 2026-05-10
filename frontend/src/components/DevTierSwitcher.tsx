import { useUser } from '../hooks/useUser'

export default function DevTierSwitcher() {
  if (!import.meta.env.DEV) return null
  const { tier, setDevTier } = useUser()
  return (
    <div style={{
      position: 'fixed', bottom: 12, right: 12, zIndex: 9999,
      background: 'rgba(0,0,0,0.8)', color: '#fff',
      padding: '6px 10px', borderRadius: 6, fontSize: 12,
      fontFamily: 'monospace',
    }}>
      Tier: <strong>{tier}</strong>
      {' '}
      <button onClick={() => setDevTier(tier === 'pro' ? 'free' : 'pro')}
        style={{ cursor: 'pointer', background: 'var(--gold, #c9a84c)', border: 'none', borderRadius: 3, padding: '2px 6px', fontFamily: 'monospace', fontSize: 11 }}>
        Switch
      </button>
    </div>
  )
}
