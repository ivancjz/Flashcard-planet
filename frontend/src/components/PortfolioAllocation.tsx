import type { PortfolioAllocation as PortfolioAllocationType } from '../types/portfolio'

interface PortfolioAllocationProps {
  allocations: PortfolioAllocationType[]
  unpricedPositionCount: number
}

const allocationClasses = [
  'portfolio-allocation-gold',
  'portfolio-allocation-cyan',
  'portfolio-allocation-green',
  'portfolio-allocation-rose',
  'portfolio-allocation-neutral',
]

function label(value: string): string {
  return value
    .split('_')
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(' ')
}

function missingPriceMessage(count: number): string | null {
  if (count === 0) return null
  return count === 1
    ? '1 position is missing a raw market price'
    : `${count} positions are missing a raw market price`
}

export default function PortfolioAllocation({
  allocations,
  unpricedPositionCount,
}: PortfolioAllocationProps) {
  const missingMessage = missingPriceMessage(unpricedPositionCount)

  return (
    <section className="portfolio-allocation" aria-labelledby="portfolio-allocation-title">
      <div className="portfolio-section-heading">
        <h2 id="portfolio-allocation-title">Allocation</h2>
        <span>Priced raw market value</span>
      </div>

      {allocations.length === 0 ? (
        <p className="portfolio-allocation-empty">
          No raw market prices are available for allocation yet.
        </p>
      ) : (
        <>
          <div
            className="portfolio-allocation-band"
            aria-label="Allocation by priced market value"
          >
            {allocations.map((allocation, index) => {
              const percentage = Number(allocation.percentage)
              const game = label(allocation.game)
              return (
                <span
                  key={allocation.game}
                  className={
                    allocationClasses[index % allocationClasses.length]
                  }
                  style={{
                    width: `${allocation.percentage}%`,
                    minWidth: percentage > 0 ? '2px' : undefined,
                  }}
                  aria-label={
                    `${game}: ${Number(allocation.percentage).toFixed(2)}% ` +
                    'of priced market value'
                  }
                />
              )
            })}
          </div>
          <div className="portfolio-allocation-legend">
            {allocations.map((allocation, index) => (
              <div className="portfolio-allocation-legend-item" key={allocation.game}>
                <span
                  className={
                    `portfolio-allocation-swatch ` +
                    allocationClasses[index % allocationClasses.length]
                  }
                  aria-hidden="true"
                />
                <span>{label(allocation.game)}</span>
                <strong>{Number(allocation.percentage).toFixed(2)}%</strong>
              </div>
            ))}
          </div>
        </>
      )}

      {missingMessage && (
        <p className="portfolio-allocation-note">{missingMessage}</p>
      )}
    </section>
  )
}
