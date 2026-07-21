import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import NavBar from '../components/NavBar'
import { fetchDailyMarketReportByDate } from '../api/api'
import type { DailyMarketReport, MarketNumber } from '../types/api'

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
  const sentimentColor = report.market_sentiment === 'bullish'
    ? 'var(--up)'
    : report.market_sentiment === 'bearish'
      ? 'var(--down)'
      : 'var(--text-secondary)'

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

      <section className="daily-report-section daily-report-evidence" aria-labelledby="report-evidence-title">
        <div className="daily-report-section-heading">
          <h2 id="report-evidence-title">Evidence</h2>
          <span>{report.evidence.length} observations</span>
        </div>
        {report.evidence.length > 0 ? (
          <ul>
            {report.evidence.map(item => <li key={item}>{item}</li>)}
          </ul>
        ) : (
          <p className="daily-report-empty">No supporting evidence was captured.</p>
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
                  <tr key={`${index.game}-${index.label}`}>
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
                  <tr key={mover.asset_id}>
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
              <div className="daily-report-signal-row" key={signal.label}>
                <strong>{formatLabel(signal.label)}</strong>
                <span>{signal.count} signal{signal.count === 1 ? '' : 's'}</span>
                <span>{Number(signal.average_confidence).toFixed(2)}% confidence</span>
              </div>
            ))}
          </div>
        )}
      </section>
    </article>
  )
}
