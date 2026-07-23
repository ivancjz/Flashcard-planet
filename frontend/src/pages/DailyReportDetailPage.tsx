import { useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import NavBar from '../components/NavBar'
import DailyReportEvidenceLinks from '../components/DailyReportEvidenceLinks'
import { fetchDailyMarketReportByDate } from '../api/api'
import type {
  Catalyst,
  DailyMarketReport,
  DailyReportEvidenceKind,
  MarketNumber,
} from '../types/api'

function formatReportDate(value: string): string {
  const parsed = new Date(`${value}T00:00:00Z`)
  if (Number.isNaN(parsed.getTime())) return value
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(parsed)
}

function formatLabel(value: string): string {
  return value
    .split('_')
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
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

function getExternalSourceUrl(value: string): string | null {
  try {
    const parsed = new URL(value)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? value : null
  } catch {
    return null
  }
}

function formatCatalystImpact(catalyst: Catalyst): string {
  if (catalyst.impact_score === null || catalyst.impact_label === 'unscored') {
    return 'Impact: Unscored'
  }

  const score = formatSafeNumber(catalyst.impact_score)
  const label = formatLabel(catalyst.impact_label)
  return score === null ? `Impact: ${label}` : `Impact: ${label} (${score})`
}

function formatCatalystConfidence(catalyst: Catalyst): string {
  if (catalyst.confidence_score === null || catalyst.confidence_label === 'insufficient_data') {
    return 'Confidence: Insufficient evidence'
  }

  const score = formatSafeNumber(catalyst.confidence_score)
  const label = formatLabel(catalyst.confidence_label)
  return score === null ? `Confidence: ${label}` : `Confidence: ${label} (${score}%)`
}

function formatPercent(value: MarketNumber): string {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return 'N/A'
  return `${numeric >= 0 ? '+' : ''}${numeric.toFixed(2)}%`
}

function formatMoney(value: MarketNumber): string {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return 'N/A'
  return `$${numeric.toFixed(2)}`
}

function formatConfidence(value: MarketNumber | null): string {
  if (value === null) return 'Confidence unavailable'
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return 'Confidence unavailable'
  return `${numeric.toFixed(2)}% confidence`
}

function directionColor(direction: 'up' | 'down' | 'flat'): string {
  if (direction === 'up') return 'var(--up)'
  if (direction === 'down') return 'var(--down)'
  return 'var(--text-secondary)'
}

export default function DailyReportDetailPage() {
  const { reportDate = '' } = useParams()
  const [request, setRequest] = useState<{
    reportDate: string
    report: DailyMarketReport | null
    error: boolean
  } | null>(null)

  useEffect(() => {
    let active = true

    fetchDailyMarketReportByDate(reportDate)
      .then(result => {
        if (active) setRequest({ reportDate, report: result, error: false })
      })
      .catch(() => {
        if (active) setRequest({ reportDate, report: null, error: true })
      })

    return () => {
      active = false
    }
  }, [reportDate])

  const loading = request?.reportDate !== reportDate
  const report = loading ? undefined : request.report
  const error = !loading && request.error

  return (
    <div>
      <NavBar />
      <main className="page-content daily-report-detail-page">
        <Link to="/reports" className="daily-report-back-link">All daily reports</Link>

        {error ? (
          <div className="surface daily-reports-state" role="status" aria-live="polite">
            This daily report is temporarily unavailable.
          </div>
        ) : report === undefined ? (
          <div className="surface daily-reports-state" role="status" aria-live="polite" aria-busy="true">
            Loading daily report...
          </div>
        ) : report === null ? (
          <section className="surface daily-report-not-found" aria-labelledby="missing-report-title">
            <h1 id="missing-report-title">Daily report not found</h1>
            <p>No published market snapshot is available for {reportDate}.</p>
            <Link to="/reports" className="btn btn-ghost">Return to daily reports</Link>
          </section>
        ) : (
          <DailyReportContent report={report} />
        )}
      </main>
    </div>
  )
}

function DailyReportContent({ report }: { report: DailyMarketReport }) {
  const location = useLocation()
  const sentimentColor = report.market_sentiment === 'bullish'
    ? 'var(--up)'
    : report.market_sentiment === 'bearish'
      ? 'var(--down)'
      : 'var(--text-secondary)'
  const evidenceCatalog = report.intelligence.evidence_catalog

  const targetPropsForSource = (
    kind: DailyReportEvidenceKind,
    sourceRecordId: string,
  ) => {
    const item = evidenceCatalog.find(
      candidate => candidate.kind === kind && candidate.source_record_id === sourceRecordId,
    )
    return item === undefined ? {} : { id: item.target_anchor, tabIndex: -1 }
  }

  const targetPropsForExactLabel = (
    kind: DailyReportEvidenceKind,
    label: string,
  ) => {
    const item = evidenceCatalog.find(
      candidate => (
        candidate.kind === kind
        && candidate.source_record_id === null
        && candidate.label === label
      ),
    )
    return item === undefined ? {} : { id: item.target_anchor, tabIndex: -1 }
  }

  useEffect(() => {
    if (!location.hash) return undefined

    const frame = window.requestAnimationFrame(() => {
      const target = document.getElementById(location.hash.slice(1))
      if (target === null) return
      target.focus({ preventScroll: true })
      target.scrollIntoView({ block: 'center' })
    })

    return () => window.cancelAnimationFrame(frame)
  }, [location.hash, report.id])

  const anchoredEvidenceLabels = new Set<string>()

  return (
    <article>
      <header className="surface-emphasis daily-report-detail-hero">
        <div className="daily-reports-eyebrow">Flashcard Planet Daily</div>
        <div className="daily-report-detail-heading">
          <h1>{report.title}</h1>
          <time dateTime={report.report_date}>{formatReportDate(report.report_date)}</time>
        </div>
        <div className="daily-report-detail-meta">
          <span style={{ color: sentimentColor }}>{formatLabel(report.market_sentiment)}</span>
          <span aria-hidden="true">|</span>
          <span>{formatLabel(report.confidence_label)} confidence</span>
          <span aria-hidden="true">|</span>
          <span>{formatLabel(report.status)}</span>
        </div>
        <p className="daily-report-detail-summary">{report.summary}</p>
      </header>

      {report.intelligence.status === 'unavailable' ? null : (
        <section className="daily-report-ai-section" aria-label="AI Market Commentary">
          <div className="daily-report-section-heading">
            <h2>AI Market Commentary</h2>
            <span>Evidence-linked analysis</span>
          </div>

          {report.intelligence.status === 'insufficient_evidence' ? (
            <p className="daily-report-ai-copy">Insufficient evidence.</p>
          ) : (
            <>
              {report.intelligence.headline === null ? null : (
                <h3 className="daily-report-ai-headline">{report.intelligence.headline}</h3>
              )}

              {report.intelligence.commentary === null ? null : (
                <div className="daily-report-ai-block">
                  <p className="daily-report-ai-copy">{report.intelligence.commentary}</p>
                  <DailyReportEvidenceLinks
                    reportDate={report.report_date}
                    refs={report.intelligence.evidence_refs}
                    catalog={evidenceCatalog}
                  />
                </div>
              )}

              {report.intelligence.key_observations.length === 0 ? null : (
                <ul className="daily-report-ai-observations">
                  {report.intelligence.key_observations.map((observation, index) => (
                    <li key={`${observation.text}-${index}`}>
                      <p>{observation.text}</p>
                      <DailyReportEvidenceLinks
                        reportDate={report.report_date}
                        refs={observation.evidence_refs}
                        catalog={evidenceCatalog}
                      />
                    </li>
                  ))}
                </ul>
              )}

              {report.intelligence.risk_summary === null ? null : (
                <div className="daily-report-ai-risk">
                  <h3>Risk Summary</h3>
                  <p>{report.intelligence.risk_summary}</p>
                  <DailyReportEvidenceLinks
                    reportDate={report.report_date}
                    refs={report.intelligence.evidence_refs}
                    catalog={evidenceCatalog}
                  />
                </div>
              )}
            </>
          )}
        </section>
      )}

      <section className="daily-report-section daily-report-evidence" aria-labelledby="report-evidence-title">
        <div className="daily-report-section-heading">
          <h2 id="report-evidence-title">Evidence</h2>
          <span>{report.evidence.length} observations</span>
        </div>
        {report.evidence.length > 0 ? (
          <ul>
            {report.evidence.map((item, index) => {
              const targetProps = anchoredEvidenceLabels.has(item)
                ? {}
                : targetPropsForExactLabel('report_evidence', item)
              anchoredEvidenceLabels.add(item)

              return (
                <li
                  className="daily-report-evidence-target"
                  key={`${item}-${index}`}
                  {...targetProps}
                >
                  {item}
                </li>
              )
            })}
          </ul>
        ) : (
          <p className="daily-report-empty">No supporting evidence was captured.</p>
        )}
      </section>

      <section
        className="daily-report-section daily-report-catalysts"
        aria-labelledby="report-catalysts-title"
      >
        <div className="daily-report-section-heading">
          <h2 id="report-catalysts-title">Market Catalysts</h2>
          <span>
            {report.catalysts.length} captured event{report.catalysts.length === 1 ? '' : 's'}
          </span>
        </div>
        {report.catalysts.length === 0 ? (
          <p className="daily-report-empty">No verified catalysts were captured for this report.</p>
        ) : (
          <div className="daily-report-catalyst-list">
            {report.catalysts.map(catalyst => {
              const eventType = formatLabel(catalyst.event_type)
              const sourceUrl = getExternalSourceUrl(catalyst.source_url)

              return (
                <article
                  className="daily-report-catalyst-row daily-report-evidence-target"
                  key={catalyst.id}
                  {...targetPropsForSource('catalyst', catalyst.id)}
                >
                  <div className="daily-report-catalyst-identity">
                    <span className="daily-report-catalyst-status">{formatLabel(catalyst.status)}</span>
                    <span className="daily-report-catalyst-type">{eventType}</span>
                  </div>

                  <div className="daily-report-catalyst-dates">
                    <span>
                      <strong>Event</strong>
                      <time dateTime={catalyst.event_date}>{formatEventDate(catalyst.event_date)}</time>
                    </span>
                    <span>
                      <strong>Active until</strong>
                      <time dateTime={catalyst.active_until}>{formatEventDate(catalyst.active_until)}</time>
                    </span>
                  </div>

                  <p className="daily-report-catalyst-description">{catalyst.description}</p>

                  <div className="daily-report-catalyst-evidence">
                    <span>{formatCatalystImpact(catalyst)}</span>
                    <span>{formatCatalystConfidence(catalyst)}</span>
                    {sourceUrl === null ? (
                      <span>Evidence unavailable</span>
                    ) : (
                      <a
                        aria-label={`View evidence for ${eventType}: ${catalyst.description}`}
                        className="daily-report-catalyst-source-link"
                        href={sourceUrl}
                        target="_blank"
                        rel="noreferrer"
                      >
                        View evidence
                      </a>
                    )}
                  </div>
                </article>
              )
            })}
          </div>
        )}
      </section>

      <section className="daily-report-section" aria-label="Market Indexes">
        <div className="daily-report-section-heading">
          <h2>Market Indexes</h2>
          <span>{report.overview.indexes.length} tracked markets</span>
        </div>
        {report.overview.indexes.length === 0 ? (
          <p className="daily-report-empty">No comparable market indexes were captured.</p>
        ) : (
          <div className="daily-report-table-wrap">
            <table className="daily-report-table">
              <thead>
                <tr>
                  <th scope="col">Market</th>
                  <th scope="col">Change</th>
                  <th scope="col">Coverage</th>
                  <th scope="col">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {report.overview.indexes.map(index => (
                  <tr
                    className="daily-report-evidence-target"
                    key={`${index.game}-${index.label}`}
                    {...targetPropsForSource('index', index.game)}
                  >
                    <td>
                      <strong>{index.label}</strong>
                      <span>{formatLabel(index.game)}</span>
                    </td>
                    <td style={{ color: directionColor(index.direction) }}>{formatPercent(index.change_pct)}</td>
                    <td>{index.observed_assets} of {index.current_assets} assets</td>
                    <td>{formatLabel(index.confidence_label)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="daily-report-section" aria-label="Top Movers">
        <div className="daily-report-section-heading">
          <h2>Top Movers</h2>
          <span>{report.overview.top_movers.length} qualifying assets</span>
        </div>
        {report.overview.top_movers.length === 0 ? (
          <p className="daily-report-empty">No qualifying movers were captured.</p>
        ) : (
          <div className="daily-report-table-wrap">
            <table className="daily-report-table">
              <thead>
                <tr>
                  <th scope="col">Asset</th>
                  <th scope="col">Latest</th>
                  <th scope="col">Previous</th>
                  <th scope="col">Change</th>
                </tr>
              </thead>
              <tbody>
                {report.overview.top_movers.map(mover => (
                  <tr
                    className="daily-report-evidence-target"
                    key={mover.asset_id}
                    {...targetPropsForSource('mover', mover.asset_id)}
                  >
                    <td>
                      <Link to={`/market/${mover.asset_id}`}>{mover.name}</Link>
                      <span>{mover.set_name ?? formatLabel(mover.game)}</span>
                    </td>
                    <td>{formatMoney(mover.latest_price)}</td>
                    <td>{formatMoney(mover.previous_price)}</td>
                    <td style={{ color: directionColor(mover.direction) }}>{formatPercent(mover.percent_change)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="daily-report-section" aria-label="Signal Summary">
        <div className="daily-report-section-heading">
          <h2>Signal Summary</h2>
          <span>{report.overview.signal_summary.length} active labels</span>
        </div>
        {report.overview.signal_summary.length === 0 ? (
          <p className="daily-report-empty">No active signals were captured.</p>
        ) : (
          <div className="daily-report-signal-list">
            {report.overview.signal_summary.map(signal => (
              <div
                className="daily-report-signal-row daily-report-evidence-target"
                key={signal.label}
                {...targetPropsForSource('signal', signal.label)}
              >
                <strong>{formatLabel(signal.label)}</strong>
                <span>{signal.count} signal{signal.count === 1 ? '' : 's'}</span>
                <span>{formatConfidence(signal.average_confidence)}</span>
              </div>
            ))}
          </div>
        )}
      </section>
    </article>
  )
}
