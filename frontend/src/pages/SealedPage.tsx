import { useEffect, useState } from 'react'
import NavBar from '../components/NavBar'

interface SealedProduct {
  asset_id: string
  name: string
  set_name: string | null
  product_type: string | null
  game: string
  from_price: number | null
  trend_pct: number | null
  trend_label: string | null
  last_updated: string | null
  listing_count: number
  min_count_met: boolean
}

const PRODUCT_TYPE_LABELS: Record<string, string> = {
  booster_box: 'Booster Box',
  etb: 'ETB',
  case: 'Case',
  blister: 'Blister',
  other: 'Other',
}

function TrendBadge({ trend_pct, trend_label }: { trend_pct: number | null; trend_label: string | null }) {
  if (trend_label) {
    return <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{trend_label}</span>
  }
  if (trend_pct === null) {
    return <span style={{ color: 'var(--text-muted)' }}>—</span>
  }
  const isUp = trend_pct > 0
  const isDown = trend_pct < 0
  const color = isUp ? 'var(--move)' : isDown ? '#e05252' : 'var(--text-secondary)'
  const symbol = isUp ? '▲' : isDown ? '▼' : '—'
  return (
    <span style={{ color, fontSize: 13, fontWeight: 600 }}>
      {symbol} {Math.abs(trend_pct).toFixed(1)}%
    </span>
  )
}

export default function SealedPage() {
  const [products, setProducts] = useState<SealedProduct[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/v1/sealed/products', { credentials: 'include' })
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(data => {
        setProducts(data.products || [])
        setLoading(false)
      })
      .catch(_err => {
        setError('Failed to load sealed products.')
        setLoading(false)
      })
  }, [])

  return (
    <div>
      <NavBar />
      <div className="page-content" style={{ maxWidth: 960, margin: '0 auto', padding: '32px 24px' }}>
        <div style={{ marginBottom: 28 }}>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 24, fontWeight: 700, marginBottom: 6 }}>
            Sealed Products
          </h1>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: 0 }}>
            From-price (cheapest credible ask incl. shipping) updated every 6 hours. 7-day trend shows price direction.
          </p>
        </div>

        {loading && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {[...Array(6)].map((_, i) => (
              <div
                key={i}
                className="surface"
                style={{ height: 52, borderRadius: 6, opacity: 0.4, background: 'var(--surface)' }}
              />
            ))}
          </div>
        )}

        {error && (
          <div className="surface" style={{ padding: 24, color: 'var(--text-secondary)', textAlign: 'center' }}>
            {error}
          </div>
        )}

        {!loading && !error && products.length === 0 && (
          <div className="surface" style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>📦</div>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>No sealed products yet</div>
            <div style={{ fontSize: 13 }}>Data will appear after the first ingest run (every 6 hours).</div>
          </div>
        )}

        {!loading && !error && products.length > 0 && (
          <div className="surface" style={{ overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  <th style={{ textAlign: 'left', padding: '12px 16px', fontWeight: 600, color: 'var(--text-secondary)' }}>Product</th>
                  <th style={{ textAlign: 'left', padding: '12px 16px', fontWeight: 600, color: 'var(--text-secondary)' }}>Type</th>
                  <th style={{ textAlign: 'right', padding: '12px 16px', fontWeight: 600, color: 'var(--text-secondary)' }}>From Price</th>
                  <th style={{ textAlign: 'right', padding: '12px 16px', fontWeight: 600, color: 'var(--text-secondary)' }}>7d Change</th>
                  <th style={{ textAlign: 'right', padding: '12px 16px', fontWeight: 600, color: 'var(--text-secondary)' }}>Listings</th>
                </tr>
              </thead>
              <tbody>
                {products.map((product, idx) => (
                  <tr
                    key={product.asset_id}
                    style={{
                      borderBottom: idx < products.length - 1 ? '1px solid var(--border)' : 'none',
                    }}
                  >
                    <td style={{ padding: '14px 16px' }}>
                      <div style={{ fontWeight: 600 }}>{product.name}</div>
                      {product.set_name && (
                        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{product.set_name}</div>
                      )}
                    </td>
                    <td style={{ padding: '14px 16px', color: 'var(--text-secondary)' }}>
                      {product.product_type ? PRODUCT_TYPE_LABELS[product.product_type] ?? product.product_type : '—'}
                    </td>
                    <td style={{ padding: '14px 16px', textAlign: 'right' }}>
                      {product.from_price !== null
                        ? <span style={{ fontWeight: 600 }}>${product.from_price.toFixed(2)}</span>
                        : <span style={{ color: 'var(--text-muted)' }}>—</span>
                      }
                    </td>
                    <td style={{ padding: '14px 16px', textAlign: 'right' }}>
                      <TrendBadge trend_pct={product.trend_pct} trend_label={product.trend_label} />
                    </td>
                    <td style={{ padding: '14px 16px', textAlign: 'right', color: 'var(--text-secondary)' }}>
                      {product.min_count_met ? (product.listing_count >= 50 ? '50+' : product.listing_count) : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 16 }}>
          Prices are ask prices (eBay Buy It Now, item + shipping), not sold prices.
          From-price = median of 5 cheapest credible listings after filtering outliers.
        </p>
      </div>
    </div>
  )
}
