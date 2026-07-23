import { Link } from 'react-router-dom'
import type { DailyReportEvidenceCatalogItem } from '../types/api'


interface Props {
  reportDate: string
  refs: string[]
  catalog: DailyReportEvidenceCatalogItem[]
  limit?: number
}


export default function DailyReportEvidenceLinks({
  reportDate,
  refs,
  catalog,
  limit,
}: Props) {
  const byId = new Map(catalog.map(item => [item.id, item]))
  const resolved = Array.from(new Set(refs))
    .map(id => byId.get(id))
    .filter(
      (item): item is DailyReportEvidenceCatalogItem => item !== undefined,
    )
  const visible = limit === undefined
    ? resolved
    : resolved.slice(0, Math.max(0, limit))

  if (visible.length === 0) return null

  return (
    <span
      className="daily-report-ai-citations"
      aria-label="Supporting evidence"
    >
      {visible.map((item, index) => (
        <Link
          key={item.id}
          to={`/reports/${reportDate}#${item.target_anchor}`}
        >
          Evidence {index + 1}: {item.label}
        </Link>
      ))}
    </span>
  )
}
