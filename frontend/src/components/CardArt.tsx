import { useState } from 'react'
import { typeToColor } from '../lib/utils'
import type { Rarity } from '../types/api'

const SIZE = { sm: { w: 120, h: 168, font: 10 }, md: { w: 180, h: 252, font: 13 }, lg: { w: 240, h: 336, font: 16 } }

interface CardArtProps {
  name: string
  type: string | null
  rarity: Rarity | null
  imageUrl?: string | null
  size?: 'sm' | 'md' | 'lg'
}

const RARITY_DOTS: Record<string, number> = { secret: 3, ultra: 2, holo: 1 }

export default function CardArt({ name, type, rarity, imageUrl, size = 'md' }: CardArtProps) {
  const [imgError, setImgError] = useState(false)
  const color = typeToColor(type)
  const { w, h, font } = SIZE[size]
  const dots = RARITY_DOTS[rarity ?? ''] ?? 0

  if (imageUrl && !imgError) {
    return (
      <img
        src={imageUrl}
        alt={name}
        loading="lazy"
        decoding="async"
        width={w}
        height={h}
        style={{ borderRadius: 8, display: 'block', flexShrink: 0, objectFit: 'cover' }}
        onError={() => setImgError(true)}
      />
    )
  }

  return (
    <svg
      width={w} height={h}
      viewBox={`0 0 ${w} ${h}`}
      style={{ borderRadius: 8, display: 'block', flexShrink: 0 }}
    >
      <defs>
        <linearGradient id={`card-${name}-bg`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.9" />
          <stop offset="100%" stopColor="#0c0c10" stopOpacity="0.95" />
        </linearGradient>
        <radialGradient id={`card-${name}-glow`} cx="50%" cy="40%" r="55%">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor="transparent" stopOpacity="0" />
        </radialGradient>
      </defs>
      {/* Card background */}
      <rect width={w} height={h} fill={`url(#card-${name}-bg)`} rx={8} />
      <rect width={w} height={h} fill={`url(#card-${name}-glow)`} rx={8} />
      {/* Border */}
      <rect width={w} height={h} fill="none" stroke={color} strokeOpacity="0.4" strokeWidth="1" rx={8} />
      {/* Creature silhouette — abstract circle cluster */}
      <circle cx={w * 0.5} cy={h * 0.38} r={w * 0.22} fill={color} fillOpacity="0.15" />
      <circle cx={w * 0.5} cy={h * 0.35} r={w * 0.14} fill={color} fillOpacity="0.25" />
      <circle cx={w * 0.5} cy={h * 0.33} r={w * 0.07} fill={color} fillOpacity="0.5" />
      {/* Card name */}
      <text x={w / 2} y={h - 32} textAnchor="middle" fontSize={font} fontFamily="'Syne', sans-serif" fontWeight="700" fill="white" fillOpacity="0.9">
        {name.length > 18 ? name.slice(0, 17) + '…' : name}
      </text>
      {/* Type chip */}
      {type && (
        <>
          <rect x={w / 2 - 24} y={h - 22} width={48} height={14} rx={4} fill={color} fillOpacity="0.3" />
          <text x={w / 2} y={h - 12} textAnchor="middle" fontSize={8} fontFamily="'Space Mono', monospace" fill="white" fillOpacity="0.8">
            {type.toUpperCase()}
          </text>
        </>
      )}
      {/* Rarity dots */}
      {Array.from({ length: dots }, (_, i) => (
        <circle key={i} cx={w / 2 - (dots - 1) * 5 + i * 10} cy={h - 38} r={2.5} fill={color} fillOpacity="0.8" />
      ))}
    </svg>
  )
}
