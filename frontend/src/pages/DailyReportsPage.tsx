import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import NavBar from '../components/NavBar'
import { fetchDailyMarketReports } from '../api/api'
import type { DailyMarketReport } from '../types/api'

const PAGE_SIZE = 30

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
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function sentimentColor(sentiment: DailyMarketReport['market_sentiment']): string {
  if (sentiment === 'bullish') return 'var(--up)'
  if (sentiment === 'bearish') return 'var(--down)'
  return 'var(--text-secondary)'
}

export default function DailyReportsPage() {
  const [reports, setReports] = useState<DailyMarketReport[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState(false)
  const [loadMoreError, setLoadMoreError] = useState(false)

  useEffect(() => {
    let active = true

    fetchDailyMarketReports({ limit: PAGE_SIZE, offset: 0 })
      .then(page => {
        if (!active) return
        setReports(page.reports)
        setTotal(page.total)
        setError(false)
      })
      .catch(() => {
        if (active) setError(true)
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [])

  async function loadOlderReports() {
    setLoadingMore(true)
    setLoadMoreError(false)
    try {
      const page = await fetchDailyMarketReports({ limit: PAGE_SIZE, offset: reports.length })
      setReports(current => [...current, ...page.reports])
      setTotal(page.total)
    } catch {
      setLoadMoreError(true)
    } finally {
      setLoadingMore(false)
    }
  }

  return (
    <div>
      <NavBar />
      <main className="page-content daily-reports-page">
        <header className="daily-reports-header">
          <div>
            <div className="daily-reports-eyebrow">Market Intelligence</div>
            <h1 className="page-title" style={{ margin: 0 }}>Daily Reports</h1>
            <p className="page-subtitle">Published market snapshots, preserved with their supporting evidence.</p>
          </div>
          {!loading && !error && total > 0 && (
            <div className="daily-reports-count" aria-label={`${total} published reports`}>
              {total} published
            </div>
          )}
        </header>

        {loading ? (
          <div className="surface daily-reports-state" role="status" aria-live="polite" aria-busy="true">
            Loading daily reports...
          </div>
        ) : error ? (
          <div className="surface daily-reports-state" role="status" aria-live="polite">
            Daily report history is unavailable.
          </div>
        ) : reports.length === 0 ? (
          <div className="surface daily-reports-state" role="status" aria-live="polite">
            No daily reports have been published yet.
          </div>
        ) : (
          <>
            <div className="daily-reports-list" aria-label="Published daily reports">
              {reports.map(report => (
                <Link
                  key={report.id}
                  to={`/reports/${report.report_date}`}
                  className="daily-report-row"
                >
                  <time className="daily-report-row-date" dateTime={report.report_date}>
                    {formatReportDate(report.report_date)}
                  </time>
                  <div className="daily-report-row-content">
                    <h2>{report.title}</h2>
                    <p>{report.summary}</p>
                  </div>
                  <div className="daily-report-row-meta">
                    <span style={{ color: sentimentColor(report.market_sentiment) }}>
                      {formatLabel(report.market_sentiment)}
                    </span>
                    <span>{formatLabel(report.confidence_label)} confidence</span>
                  </div>
                  <span className="daily-report-row-arrow" aria-hidden="true">&rsaquo;</span>
                </Link>
              ))}
            </div>

            {loadMoreError && (
              <div className="daily-reports-more-error" role="status" aria-live="polite">
                Older reports could not be loaded. Try again.
              </div>
            )}

            {reports.length < total && (
              <div className="daily-reports-more">
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={loadOlderReports}
                  disabled={loadingMore}
                >
                  {loadingMore ? 'Loading older reports...' : 'Load older reports'}
                </button>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  )
}
