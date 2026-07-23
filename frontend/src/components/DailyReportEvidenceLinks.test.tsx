import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { DailyReportEvidenceCatalogItem } from '../types/api'
import DailyReportEvidenceLinks from './DailyReportEvidenceLinks'


const catalog: DailyReportEvidenceCatalogItem[] = [
  {
    id: 'index:pokemon',
    kind: 'index',
    label: 'Pokemon Market',
    source_record_id: 'pokemon',
    target_anchor: 'evidence-abc123abc123',
  },
  {
    id: 'mover:charizard',
    kind: 'mover',
    label: 'Charizard',
    source_record_id: 'charizard',
    target_anchor: 'evidence-def456def456',
  },
]


function renderLinks(
  refs: string[],
  limit?: number,
) {
  return render(
    <MemoryRouter>
      <DailyReportEvidenceLinks
        reportDate="2026-07-22"
        refs={refs}
        catalog={catalog}
        limit={limit}
      />
    </MemoryRouter>,
  )
}


describe('DailyReportEvidenceLinks', () => {
  it('links known evidence to the dated report anchor', () => {
    renderLinks(['index:pokemon'])

    expect(
      screen
        .getByRole('link', { name: 'Evidence 1: Pokemon Market' })
        .getAttribute('href'),
    ).toBe('/reports/2026-07-22#evidence-abc123abc123')
  })

  it('omits unknown references instead of creating a broken link', () => {
    renderLinks(['index:missing'])

    expect(screen.queryByRole('link')).toBeNull()
    expect(screen.queryByLabelText('Supporting evidence')).toBeNull()
  })

  it('preserves first-reference order, removes duplicates, and applies the limit', () => {
    renderLinks(
      ['mover:charizard', 'index:pokemon', 'mover:charizard'],
      1,
    )

    const links = screen.getAllByRole('link')
    expect(links).toHaveLength(1)
    expect(links[0].textContent).toBe('Evidence 1: Charizard')
  })
})
