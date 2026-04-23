import { useState } from 'react'

type Game = { id: string; label: string; icon: string; status: 'active' | 'coming_soon' }

const GAMES: Game[] = [
  { id: 'pokemon',  label: 'Pokémon',              icon: '🎴', status: 'active' },
  { id: 'yugioh',   label: 'Yu-Gi-Oh',             icon: '⚔️', status: 'active' },
  { id: 'mtg',      label: 'Magic: The Gathering',  icon: '🧙', status: 'coming_soon' },
  { id: 'onepiece', label: 'One Piece',             icon: '☠️', status: 'coming_soon' },
  { id: 'lorcana',  label: 'Lorcana',               icon: '✨', status: 'coming_soon' },
]

interface Props {
  activeGame: string
  onGameChange: (gameId: string) => void
}

export default function GameSwitcher({ activeGame, onGameChange }: Props) {
  const [showMore, setShowMore] = useState(false)
  const visible = GAMES.slice(0, 2)
  const more = GAMES.slice(2)

  const activePill: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', gap: 6,
    padding: '5px 14px', borderRadius: 20, fontSize: 13, fontWeight: 600,
    background: 'var(--gold-glow)', color: 'var(--gold)',
    border: '1px solid rgba(240,180,41,0.35)', cursor: 'pointer',
    fontFamily: 'var(--font-display)',
  }
  const ghostPill: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', gap: 6,
    padding: '5px 14px', borderRadius: 20, fontSize: 13,
    background: 'transparent', color: 'var(--text-muted)',
    border: '1px dashed var(--border-subtle)', cursor: 'not-allowed',
    fontFamily: 'var(--font-display)',
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '10px 24px', borderBottom: '1px solid var(--border-subtle)', background: 'var(--bg-surface)' }}>
      {visible.map(g => {
        const isActive = g.id === activeGame
        return isActive ? (
          <button key={g.id} style={activePill} onClick={() => onGameChange(g.id)}>
            {g.icon} {g.label}
          </button>
        ) : (
          <button
            key={g.id}
            style={ghostPill}
            title={g.status === 'coming_soon' ? `Coming soon — ${g.label} support is in development` : undefined}
            onClick={() => g.status === 'active' && onGameChange(g.id)}
          >
            {g.icon} {g.label}
            {g.status === 'coming_soon' && <span style={{ fontSize: 9, fontFamily: 'var(--font-mono)', marginLeft: 2 }}>soon</span>}
          </button>
        )
      })}

      <div style={{ position: 'relative' }}>
        <button style={ghostPill} onClick={() => setShowMore(v => !v)}>
          + More
        </button>
        {showMore && (
          <>
            <div
              style={{ position: 'fixed', inset: 0, zIndex: 99 }}
              onClick={() => setShowMore(false)}
            />
            <div style={{
              position: 'absolute', top: 'calc(100% + 6px)', left: 0, zIndex: 100,
              background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)',
              borderRadius: 8, padding: '6px 0', minWidth: 220,
            }}>
              {more.map(g => (
                <div key={g.id} style={{ padding: '8px 16px', display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--text-muted)', cursor: 'not-allowed' }}>
                  <span>{g.icon}</span>
                  <span style={{ flex: 1 }}>{g.label}</span>
                  <span style={{ fontSize: 9, fontFamily: 'var(--font-mono)', color: 'var(--nodata)' }}>soon</span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
