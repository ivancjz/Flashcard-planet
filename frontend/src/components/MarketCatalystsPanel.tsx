import type { Catalyst, MarketNumber } from '../types/api'

interface MarketCatalystsPanelProps {
  catalysts: Catalyst[] | undefined
  unavailable: boolean
}

function formatLabel(value: string): string {
  return value
    .split('_')
    .filter(Boolean)
    .map(part => {
      const normalized = part.toLowerCase()
      return normalized.charAt(0).toUpperCase() + normalized.slice(1)
    })
    .join(' ')
}

function formatEventDate(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value

  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(parsed)
}

function formatSafeNumber(value: MarketNumber): string | null {
  const formatted = String(value).trim()
  if (!formatted || !Number.isFinite(Number(formatted))) return null
  return formatted
}

function formatImpact(catalyst: Catalyst): string {
  if (catalyst.impact_score == null || catalyst.impact_label === 'unscored') {
    return 'Impact: Unscored'
  }

  const score = formatSafeNumber(catalyst.impact_score)
  const label = formatLabel(catalyst.impact_label)
  return score === null ? `Impact: ${label}` : `Impact: ${label} (${score})`
}

function formatConfidence(catalyst: Catalyst): string {
  if (catalyst.confidence_score == null || catalyst.confidence_label === 'insufficient_data') {
    return 'Confidence: Insufficient evidence'
  }

  const score = formatSafeNumber(catalyst.confidence_score)
  const label = formatLabel(catalyst.confidence_label)
  return score === null ? `Confidence: ${label}` : `Confidence: ${label} (${score}%)`
}

export default function MarketCatalystsPanel({
  catalysts,
  unavailable,
}: MarketCatalystsPanelProps) {
  const loading = catalysts === undefined && !unavailable

  return (
    <section
      aria-label="Market Catalysts"
      aria-live="polite"
      aria-atomic="true"
      aria-busy={loading || undefined}
      className="market-catalysts-panel surface"
    >
      <header className="market-catalysts-header">
        <h2>Market Catalysts</h2>
      </header>

      {unavailable ? (
        <div className="market-catalysts-state">Market catalysts unavailable.</div>
      ) : catalysts === undefined ? (
        <div className="market-catalysts-state">Loading market catalysts...</div>
      ) : catalysts.length === 0 ? (
        <div className="market-catalysts-state">No verified catalysts are active or upcoming for this market.</div>
      ) : (
        <div className="market-catalysts-list">
          {catalysts.slice(0, 3).map(catalyst => (
            <article className="market-catalyst-row" key={catalyst.id}>
              <div className="market-catalyst-identity">
                <span className="market-catalyst-status">{formatLabel(catalyst.status)}</span>
                <span className="market-catalyst-type">{formatLabel(catalyst.event_type)}</span>
                <time dateTime={catalyst.event_date}>{formatEventDate(catalyst.event_date)}</time>
              </div>

              <p className="market-catalyst-description">{catalyst.description}</p>

              <div className="market-catalyst-evidence">
                <span>{formatImpact(catalyst)}</span>
                <span>{formatConfidence(catalyst)}</span>
                <a
                  className="market-catalyst-source-link"
                  href={catalyst.source_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  View evidence
                </a>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
