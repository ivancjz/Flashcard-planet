import { useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import NavBar from '../components/NavBar'
import { useUser } from '../contexts/UserContext'

export default function AccountPage() {
  const { tier, email, loading } = useUser()
  const nav = useNavigate()

  useEffect(() => {
    if (!loading && tier === 'free') nav('/', { replace: true })
  }, [loading, tier, nav])

  if (loading) return <div><NavBar /><div className="page-content">Loading…</div></div>

  return (
    <div>
      <NavBar />
      <div className="page-content" style={{ maxWidth: 480 }}>
        <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 700, marginBottom: 4 }}>
          Account
        </h1>
        <p style={{ color: 'var(--text-muted)', fontSize: 14, marginBottom: 24 }}>{email}</p>

        <div className="surface" style={{ padding: 20 }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Email preferences</div>
          <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 12 }}>
            Control your Market Digest frequency.
          </p>
          <Link to="/account/digest-preferences" style={{ fontSize: 14, color: 'var(--gold)' }}>
            Manage Market Digest →
          </Link>
        </div>
      </div>
    </div>
  )
}
