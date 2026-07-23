import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import DailyReportDetailPage from './DailyReportDetailPage'
import { fetchCatalyst, fetchCatalysts, fetchDailyMarketReportByDate } from '../api/api'
import type {
  Catalyst,
  DailyMarketReport,
  DailyReportIntelligence,
} from '../types/api'

vi.mock('../api/api', () => ({
  fetchCatalyst: vi.fn(),
  fetchCatalysts: vi.fn(),
  fetchDailyMarketReportByDate: vi.fn(),
}))

vi.mock('../components/NavBar', () => ({
  default: () => <nav aria-label="Main navigation" />,
}))

function makeReport(): DailyMarketReport {
  return {
    id: 'report-2026-07-21',
    report_date: '2026-07-21',
    generated_at: '2026-07-21T10:00:00Z',
    status: 'published',
    title: 'Flashcard Planet Daily - 2026-07-21',
    market_sentiment: 'bullish',
    confidence_label: 'high',
    summary: 'Pokemon cards led a broad but evidence-backed market advance.',
    overview: {
      generated_at: '2026-07-21T10:00:00Z',
      market_sentiment: 'bullish',
      confidence_label: 'high',
      indexes: [
        {
          game: 'pokemon',
          label: 'Pokemon Market',
          change_pct: '4.25',
          direction: 'up',
          observed_assets: 18,
          current_assets: 22,
          confidence_label: 'high',
        },
      ],
      top_movers: [
        {
          asset_id: 'asset-charizard',
          name: 'Charizard',
          game: 'pokemon',
          set_name: 'Base Set',
          latest_price: '120.00',
          previous_price: '100.00',
          percent_change: '20.00',
          absolute_change: '20.00',
          direction: 'up',
        },
      ],
      signal_summary: [
        { label: 'BREAKOUT', count: 3, average_confidence: '88.00' },
      ],
      commentary: 'Raw Pokemon price series produced the strongest verified move.',
      evidence: ['market_segment=raw'],
    },
    catalysts: [],
    evidence: ['market_segment=raw', 'active price source: sample_seed'],
    intelligence: {
      status: 'unavailable',
      headline: null,
      commentary: null,
      risk_summary: null,
      key_observations: [],
      evidence_refs: [],
      evidence_catalog: [],
      generated_at: null,
    },
  }
}

function makeCatalyst(overrides: Partial<Catalyst> = {}): Catalyst {
  return {
    id: 'pokemon-regionals-2026',
    event_date: '2026-08-10T23:30:00Z',
    active_until: '2026-08-12T23:30:00Z',
    event_type: 'REGIONAL__CHAMPIONSHIP',
    description: 'Pokemon regional championship registration opens.',
    source_url: 'https://example.com/pokemon-regionals',
    affected_games: ['pokemon'],
    affected_asset_ids: [],
    affected_set_ids: [],
    expected_window_days: 3,
    impact_score: 72,
    impact_label: 'medium',
    confidence_score: '84.00',
    confidence_label: 'high',
    status: 'upcoming',
    verified_at: '2026-07-22T01:00:00Z',
    ...overrides,
  }
}

function makePublishedIntelligence(
  overrides: Partial<DailyReportIntelligence> = {},
): DailyReportIntelligence {
  return {
    status: 'published',
    headline: 'Pokemon market breadth improved',
    commentary: 'The captured Pokemon index moved 4.25%.',
    risk_summary: 'Coverage includes 4 observed assets.',
    key_observations: [
      { text: 'Charizard moved 20%.', evidence_refs: ['mover:asset-charizard'] },
    ],
    evidence_refs: ['index:pokemon', 'mover:asset-charizard'],
    evidence_catalog: [
      {
        id: 'index:pokemon',
        kind: 'index',
        label: 'Pokemon Market',
        source_record_id: 'pokemon',
        target_anchor: 'evidence-index000001',
      },
      {
        id: 'mover:asset-charizard',
        kind: 'mover',
        label: 'Charizard',
        source_record_id: 'asset-charizard',
        target_anchor: 'evidence-mover000001',
      },
    ],
    generated_at: '2026-07-22T01:00:00Z',
    ...overrides,
  }
}

function makeReportWithCatalogForEveryKind(): DailyMarketReport {
  const report = makeReport()
  const catalyst = makeCatalyst()
  report.catalysts = [catalyst]
  report.intelligence = makePublishedIntelligence({
    evidence_refs: [
      'index:pokemon',
      'mover:asset-charizard',
      'signal:breakout',
      `catalyst:${catalyst.id}`,
      'report:evidence:2',
    ],
    evidence_catalog: [
      {
        id: 'index:pokemon',
        kind: 'index',
        label: 'Pokemon Market',
        source_record_id: 'pokemon',
        target_anchor: 'evidence-index000001',
      },
      {
        id: 'mover:asset-charizard',
        kind: 'mover',
        label: 'Charizard',
        source_record_id: 'asset-charizard',
        target_anchor: 'evidence-mover000001',
      },
      {
        id: 'signal:breakout',
        kind: 'signal',
        label: 'BREAKOUT',
        source_record_id: 'BREAKOUT',
        target_anchor: 'evidence-signal00001',
      },
      {
        id: `catalyst:${catalyst.id}`,
        kind: 'catalyst',
        label: catalyst.description,
        source_record_id: catalyst.id,
        target_anchor: 'evidence-catalyst001',
      },
      {
        id: 'report:evidence:2',
        kind: 'report_evidence',
        label: 'market_segment=raw',
        source_record_id: null,
        target_anchor: 'evidence-report00001',
      },
    ],
  })
  return report
}

function renderPage(initialEntry = '/reports/2026-07-21') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/reports/:reportDate" element={<DailyReportDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('DailyReportDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('announces the report loading state', () => {
    vi.mocked(fetchDailyMarketReportByDate).mockReturnValue(new Promise(() => {}))

    renderPage()

    const status = screen.getByRole('status')
    expect(status.getAttribute('aria-busy')).toBe('true')
    expect(status.textContent).toContain('Loading daily report')
  })

  it('renders the full persisted report and its evidence', async () => {
    vi.mocked(fetchDailyMarketReportByDate).mockResolvedValue(makeReport())

    renderPage()

    expect(await screen.findByRole('heading', { name: 'Flashcard Planet Daily - 2026-07-21' })).toBeTruthy()
    expect(screen.getByText('Jul 21, 2026')).toBeTruthy()
    expect(screen.getByText('Pokemon cards led a broad but evidence-backed market advance.')).toBeTruthy()
    expect(screen.getByText('active price source: sample_seed')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'All daily reports' }).getAttribute('href')).toBe('/reports')
    expect(fetchDailyMarketReportByDate).toHaveBeenCalledWith('2026-07-21')
    expect(fetchDailyMarketReportByDate).toHaveBeenCalledTimes(1)
  })

  it('renders published AI commentary, observations, risk, and local citations', async () => {
    const report = makeReport()
    report.intelligence = makePublishedIntelligence()
    vi.mocked(fetchDailyMarketReportByDate).mockResolvedValue(report)

    renderPage()

    const section = await screen.findByRole('region', { name: 'AI Market Commentary' })
    expect(within(section).getByRole('heading', { name: report.intelligence.headline! })).toBeTruthy()
    expect(within(section).getByText(report.intelligence.commentary!)).toBeTruthy()
    expect(within(section).getByText(report.intelligence.key_observations[0].text)).toBeTruthy()
    expect(within(section).getByText(report.intelligence.risk_summary!)).toBeTruthy()
    expect(within(section).getAllByRole('link', { name: /Evidence \d:/ })).toHaveLength(5)
  })

  it('shows exact neutral text for insufficient evidence', async () => {
    const report = makeReport()
    report.intelligence.status = 'insufficient_evidence'
    report.intelligence.commentary = 'Insufficient evidence.'
    vi.mocked(fetchDailyMarketReportByDate).mockResolvedValue(report)

    renderPage()

    const section = await screen.findByRole('region', { name: 'AI Market Commentary' })
    expect(within(section).getByText('Insufficient evidence.')).toBeTruthy()
  })

  it('omits AI section when intelligence is unavailable', async () => {
    vi.mocked(fetchDailyMarketReportByDate).mockResolvedValue(makeReport())

    renderPage()

    await screen.findByRole('heading', { name: 'Flashcard Planet Daily - 2026-07-21' })
    expect(screen.queryByRole('region', { name: 'AI Market Commentary' })).toBeNull()
  })

  it('assigns server-provided anchors to every evidence target', async () => {
    const report = makeReportWithCatalogForEveryKind()
    vi.mocked(fetchDailyMarketReportByDate).mockResolvedValue(report)

    const { container } = renderPage()

    await screen.findByRole('region', { name: 'AI Market Commentary' })
    for (const item of report.intelligence.evidence_catalog) {
      const target = container.querySelector(`#${item.target_anchor}`)
      expect(target).not.toBeNull()
      expect(target?.getAttribute('tabindex')).toBe('-1')
    }
  })

  it('matches Unicode rows through exact server source IDs without reconstructing evidence IDs', async () => {
    const report = makeReportWithCatalogForEveryKind()
    report.overview.indexes[0].game = 'Pokémon'
    report.overview.indexes[0].label = 'Pokémon Market'
    const catalogItem = report.intelligence.evidence_catalog.find(item => item.kind === 'index')!
    catalogItem.id = 'index:pokemon'
    catalogItem.label = 'Pokémon Market'
    catalogItem.source_record_id = 'Pokémon'
    vi.mocked(fetchDailyMarketReportByDate).mockResolvedValue(report)

    const { container } = renderPage()

    await screen.findByRole('region', { name: 'AI Market Commentary' })
    const target = container.querySelector(`#${catalogItem.target_anchor}`)
    expect(target?.textContent).toContain('Pokémon Market')
  })

  it('focuses the cited target when the report route has an evidence fragment', async () => {
    const report = makeReportWithCatalogForEveryKind()
    vi.mocked(fetchDailyMarketReportByDate).mockResolvedValue(report)
    Element.prototype.scrollIntoView = vi.fn()

    renderPage('/reports/2026-07-21#evidence-index000001')

    await waitFor(() => expect(document.activeElement?.id).toBe('evidence-index000001'))
  })

  it('renders model-looking markup as plain text', async () => {
    const report = makeReport()
    report.intelligence = makePublishedIntelligence({
      commentary: '<strong>Observed</strong> **market**',
    })
    vi.mocked(fetchDailyMarketReportByDate).mockResolvedValue(report)

    const { container } = renderPage()

    expect(await screen.findByText('<strong>Observed</strong> **market**')).toBeTruthy()
    expect(container.querySelector('strong')?.textContent).not.toBe('Observed')
  })

  it('renders the empty persisted catalyst snapshot between evidence and indexes', async () => {
    vi.mocked(fetchDailyMarketReportByDate).mockResolvedValue(makeReport())

    renderPage()

    const catalysts = await screen.findByRole('region', { name: 'Market Catalysts' })
    expect(catalysts.classList.contains('daily-report-section')).toBe(true)
    expect(catalysts.classList.contains('daily-report-catalysts')).toBe(true)
    expect(within(catalysts).getByRole('heading', { name: 'Market Catalysts' })).toBeTruthy()
    expect(within(catalysts).getByText('0 captured events')).toBeTruthy()
    expect(within(catalysts).getByText('No verified catalysts were captured for this report.')).toBeTruthy()

    const sectionHeadings = screen.getAllByRole('heading', { level: 2 }).map(heading => heading.textContent)
    expect(sectionHeadings).toEqual([
      'Evidence',
      'Market Catalysts',
      'Market Indexes',
      'Top Movers',
      'Signal Summary',
    ])
  })

  it('renders every stored catalyst in snapshot order with safe evidence handling', async () => {
    const report = makeReport()
    report.catalysts = [
      makeCatalyst(),
      makeCatalyst({
        id: 'pokemon-supply-update',
        event_date: '2026-08-14',
        active_until: '2026-08-20',
        event_type: 'supply_chain_update',
        description: 'Distributor allocation details changed for the next product wave.',
        source_url: 'javascript:alert(1)',
        impact_score: null,
        impact_label: 'high',
        confidence_score: null,
        confidence_label: 'high',
        status: 'active',
      }),
      makeCatalyst({
        id: 'pokemon-restock-watch',
        event_date: '2026-08-21',
        active_until: '2026-08-28',
        event_type: 'RETAIL_RESTOCK_WATCH',
        description: 'Retail restock evidence remains too limited for a scored assessment.',
        source_url: '/evidence/restock-watch',
        impact_score: 45,
        impact_label: 'unscored',
        confidence_score: '91',
        confidence_label: 'insufficient_data',
      }),
      makeCatalyst({
        id: 'pokemon-supply-review',
        event_date: '2026-09-01',
        active_until: '2026-09-05',
        event_type: 'POST_LAUNCH_SUPPLY_REVIEW',
        description: 'Post-launch supply evidence was retained as the fourth captured event.',
        source_url: 'not a url',
        status: 'expired',
      }),
    ]
    vi.mocked(fetchDailyMarketReportByDate).mockResolvedValue(report)

    const { container } = renderPage()

    const catalysts = await screen.findByRole('region', { name: 'Market Catalysts' })
    expect(within(catalysts).getByText('4 captured events')).toBeTruthy()

    const rows = Array.from(container.querySelectorAll<HTMLElement>('.daily-report-catalyst-row'))
    expect(rows).toHaveLength(4)
    expect(rows.map(row => row.querySelector('.daily-report-catalyst-description')?.textContent)).toEqual(
      report.catalysts.map(catalyst => catalyst.description),
    )

    expect(within(rows[0]).getByText('Upcoming')).toBeTruthy()
    expect(within(rows[0]).getByText('Regional Championship')).toBeTruthy()
    expect(within(rows[0]).getByText('Event')).toBeTruthy()
    expect(within(rows[0]).getByText('Aug 10, 2026')).toBeTruthy()
    expect(within(rows[0]).getByText('Active until')).toBeTruthy()
    expect(within(rows[0]).getByText('Aug 12, 2026')).toBeTruthy()
    expect(within(rows[0]).getByText('Impact: Medium (72)')).toBeTruthy()
    expect(within(rows[0]).getByText('Confidence: High (84.00%)')).toBeTruthy()

    expect(within(rows[1]).getByText('Active')).toBeTruthy()
    expect(within(rows[1]).getByText('Supply Chain Update')).toBeTruthy()
    expect(within(rows[1]).getByText('Impact: Unscored')).toBeTruthy()
    expect(within(rows[1]).getByText('Confidence: Insufficient evidence')).toBeTruthy()
    expect(within(rows[2]).getByText('Impact: Unscored')).toBeTruthy()
    expect(within(rows[2]).getByText('Confidence: Insufficient evidence')).toBeTruthy()

    const evidenceLink = within(rows[0]).getByRole('link', {
      name: 'View evidence for Regional Championship: Pokemon regional championship registration opens.',
    })
    expect(evidenceLink.textContent).toBe('View evidence')
    expect(evidenceLink.getAttribute('href')).toBe('https://example.com/pokemon-regionals')
    expect(evidenceLink.getAttribute('target')).toBe('_blank')
    expect(evidenceLink.getAttribute('rel')).toBe('noreferrer')

    expect(within(catalysts).getAllByText('Evidence unavailable')).toHaveLength(3)
    expect(within(catalysts).getAllByRole('link')).toEqual([evidenceLink])
    expect(fetchDailyMarketReportByDate).toHaveBeenCalledTimes(1)
    expect(fetchCatalysts).not.toHaveBeenCalled()
    expect(fetchCatalyst).not.toHaveBeenCalled()
  })

  it('renders indexes, movers, and signal summary', async () => {
    vi.mocked(fetchDailyMarketReportByDate).mockResolvedValue(makeReport())

    renderPage()

    const indexes = await screen.findByRole('region', { name: 'Market Indexes' })
    expect(within(indexes).getByText('Pokemon Market')).toBeTruthy()
    expect(within(indexes).getByText('+4.25%')).toBeTruthy()

    const movers = screen.getByRole('region', { name: 'Top Movers' })
    expect(within(movers).getByRole('link', { name: 'Charizard' }).getAttribute('href')).toBe('/market/asset-charizard')
    expect(within(movers).getByText('$120.00')).toBeTruthy()
    expect(within(movers).getByText('+20.00%')).toBeTruthy()

    const signals = screen.getByRole('region', { name: 'Signal Summary' })
    expect(within(signals).getByText('Breakout')).toBeTruthy()
    expect(within(signals).getByText('3 signals')).toBeTruthy()
    expect(within(signals).getByText('88.00% confidence')).toBeTruthy()
  })

  it('does not turn unavailable signal confidence into a numeric measurement', async () => {
    const report = makeReport()
    report.overview.signal_summary = [
      { label: 'WATCH', count: 2, average_confidence: null },
    ]
    vi.mocked(fetchDailyMarketReportByDate).mockResolvedValue(report)

    renderPage()

    const signals = await screen.findByRole('region', { name: 'Signal Summary' })
    expect(within(signals).getByText('Confidence unavailable')).toBeTruthy()
    expect(within(signals).queryByText('0.00% confidence')).toBeNull()
  })

  it('renders a missing report state', async () => {
    vi.mocked(fetchDailyMarketReportByDate).mockResolvedValue(null)

    renderPage()

    expect(await screen.findByRole('heading', { name: 'Daily report not found' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Return to daily reports' }).getAttribute('href')).toBe('/reports')
  })

  it('renders a request error state', async () => {
    vi.mocked(fetchDailyMarketReportByDate).mockRejectedValue(new Error('network error'))

    renderPage()

    expect(await screen.findByText('This daily report is temporarily unavailable.')).toBeTruthy()
  })

  it('labels empty report subsections instead of leaving blank space', async () => {
    const report = makeReport()
    report.overview.indexes = []
    report.overview.top_movers = []
    report.overview.signal_summary = []
    vi.mocked(fetchDailyMarketReportByDate).mockResolvedValue(report)

    renderPage()

    expect(await screen.findByText('No comparable market indexes were captured.')).toBeTruthy()
    expect(screen.getByText('No qualifying movers were captured.')).toBeTruthy()
    expect(screen.getByText('No active signals were captured.')).toBeTruthy()
  })
})
