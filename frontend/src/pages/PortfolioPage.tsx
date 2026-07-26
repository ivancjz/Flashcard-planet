import { useCallback, useEffect, useRef, useState } from 'react'
import { Plus } from 'lucide-react'
import {
  PortfolioApiError,
  createPortfolioLot,
  deletePortfolioLot,
  fetchPortfolio,
  updatePortfolioLot,
} from '../api/portfolio'
import NavBar from '../components/NavBar'
import PortfolioAllocation from '../components/PortfolioAllocation'
import PortfolioDeleteDialog from '../components/PortfolioDeleteDialog'
import PortfolioLotDialog from '../components/PortfolioLotDialog'
import PortfolioPositionTable from '../components/PortfolioPositionTable'
import PortfolioSummary from '../components/PortfolioSummary'
import { useUser } from '../hooks/useUser'
import type {
  Portfolio,
  PortfolioLot,
  PortfolioLotInput,
  PortfolioLotPatch,
  PortfolioPosition,
} from '../types/portfolio'

type LoadState = 'loading' | 'ready' | 'error'

type LotDialogState =
  | { mode: 'create' }
  | {
      mode: 'edit'
      position: PortfolioPosition
      lot: PortfolioLot
    }

interface DeleteSelection {
  position: PortfolioPosition
  lot: PortfolioLot
}

interface MutationFailure {
  message: string
  upgradeUrl: string | null
}

function mutationFailure(error: unknown): MutationFailure {
  if (error instanceof PortfolioApiError) {
    const detail = error.detail
    if (detail && typeof detail === 'object') {
      return {
        message: detail.message ?? 'Portfolio change could not be saved.',
        upgradeUrl: detail.upgrade_url ?? null,
      }
    }
    if (error.status === 404) {
      return {
        message: 'This portfolio lot is no longer available.',
        upgradeUrl: null,
      }
    }
    return {
      message: error.message,
      upgradeUrl: null,
    }
  }
  return {
    message: 'Portfolio change could not be saved.',
    upgradeUrl: null,
  }
}

export default function PortfolioPage() {
  const { email, loading: userLoading } = useUser()
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null)
  const [loadState, setLoadState] = useState<LoadState>('loading')
  const [pageError, setPageError] = useState<string | null>(null)
  const [lotDialog, setLotDialog] = useState<LotDialogState | null>(null)
  const [deleteSelection, setDeleteSelection] = useState<DeleteSelection | null>(
    null,
  )
  const [mutationBusy, setMutationBusy] = useState(false)
  const [mutationError, setMutationError] = useState<string | null>(null)
  const [mutationUpgradeUrl, setMutationUpgradeUrl] = useState<string | null>(
    null,
  )
  const loadSequence = useRef(0)

  const loadPortfolio = useCallback(async (): Promise<boolean> => {
    const sequence = ++loadSequence.current
    try {
      const next = await fetchPortfolio()
      if (sequence !== loadSequence.current) return false
      setPortfolio(next)
      setLoadState('ready')
      setPageError(null)
      return true
    } catch {
      if (sequence !== loadSequence.current) return false
      setLoadState('error')
      setPageError('Portfolio data is unavailable.')
      return false
    }
  }, [])

  useEffect(() => {
    if (userLoading || !email) return
    const timer = window.setTimeout(() => {
      void loadPortfolio()
    }, 0)
    return () => {
      window.clearTimeout(timer)
      loadSequence.current += 1
    }
  }, [email, loadPortfolio, userLoading])

  useEffect(() => () => {
    loadSequence.current += 1
  }, [])

  function clearMutationError() {
    setMutationError(null)
    setMutationUpgradeUrl(null)
  }

  function openCreate() {
    clearMutationError()
    setLotDialog({ mode: 'create' })
  }

  function openEditLot(position: PortfolioPosition, lot: PortfolioLot) {
    clearMutationError()
    setLotDialog({ mode: 'edit', position, lot })
  }

  function openDeleteLot(position: PortfolioPosition, lot: PortfolioLot) {
    clearMutationError()
    setDeleteSelection({ position, lot })
  }

  function closeLotDialog() {
    if (mutationBusy) return
    clearMutationError()
    setLotDialog(null)
  }

  function closeDeleteDialog() {
    if (mutationBusy) return
    clearMutationError()
    setDeleteSelection(null)
  }

  async function runMutation(
    action: () => Promise<unknown>,
    close: () => void,
  ): Promise<void> {
    setMutationBusy(true)
    clearMutationError()
    try {
      await action()
      const refreshed = await loadPortfolio()
      if (refreshed) close()
    } catch (error) {
      const failure = mutationFailure(error)
      setMutationError(failure.message)
      setMutationUpgradeUrl(failure.upgradeUrl)
    } finally {
      setMutationBusy(false)
    }
  }

  async function createLot(input: PortfolioLotInput): Promise<void> {
    await runMutation(
      () => createPortfolioLot(input),
      () => setLotDialog(null),
    )
  }

  async function patchLot(input: PortfolioLotPatch): Promise<void> {
    if (lotDialog?.mode !== 'edit') return
    const lotId = lotDialog.lot.id
    await runMutation(
      () => updatePortfolioLot(lotId, input),
      () => setLotDialog(null),
    )
  }

  async function deleteLot(lotId: string): Promise<void> {
    await runMutation(
      () => deletePortfolioLot(lotId),
      () => setDeleteSelection(null),
    )
  }

  function retry() {
    setLoadState('loading')
    setPageError(null)
    void loadPortfolio()
  }

  if (userLoading) {
    return (
      <div className="portfolio-shell">
        <NavBar />
        <main className="page-content portfolio-page">
          <PortfolioPageHeader disabled />
          <PortfolioSkeleton />
        </main>
      </div>
    )
  }

  if (!email) {
    return (
      <div className="portfolio-shell">
        <NavBar />
        <main className="page-content portfolio-page">
          <section className="portfolio-auth-state">
            <h1>Sign in to view your portfolio</h1>
            <p>Your purchase lots and valuation are private to your account.</p>
            <a className="btn btn-primary" href="/login">Sign in</a>
          </section>
        </main>
      </div>
    )
  }

  const positionLimit = portfolio?.summary.position_limit ?? null
  const positionAssetIds = portfolio?.positions.map(item => item.asset_id) ?? []

  return (
    <div className="portfolio-shell">
      <NavBar />
      <main className="page-content portfolio-page">
        <PortfolioPageHeader
          disabled={mutationBusy}
          onAdd={openCreate}
          positionLabel={portfolio
            ? portfolio.summary.position_limit === null
              ? `${portfolio.summary.position_count} positions`
              : `${portfolio.summary.position_count} of ${
                  portfolio.summary.position_limit
                } positions used`
            : undefined}
        />

        {portfolio && pageError && (
          <div className="portfolio-page-alert" role="status" aria-live="polite">
            <span>{pageError}</span>
            <button type="button" className="btn btn-ghost btn-sm" onClick={retry}>
              Retry
            </button>
          </div>
        )}

        {!portfolio && loadState === 'loading' ? (
          <PortfolioSkeleton />
        ) : !portfolio ? (
          <section className="portfolio-load-error" role="alert">
            <h2>{pageError ?? 'Portfolio data is unavailable.'}</h2>
            <button type="button" className="btn btn-ghost" onClick={retry}>
              Retry
            </button>
          </section>
        ) : (
          <>
            <PortfolioSummary summary={portfolio.summary} />
            <PortfolioAllocation
              allocations={portfolio.allocations}
              unpricedPositionCount={
                portfolio.summary.unpriced_position_count
              }
            />
            {portfolio.positions.length === 0 ? (
              <section className="portfolio-empty-state">
                <h2>Add your first position</h2>
                <p>Record a purchase lot to start tracking cost and raw value.</p>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={openCreate}
                >
                  <Plus size={16} aria-hidden="true" />
                  Add lot
                </button>
              </section>
            ) : (
              <PortfolioPositionTable
                positions={portfolio.positions}
                onEditLot={openEditLot}
                onDeleteLot={openDeleteLot}
              />
            )}
          </>
        )}
      </main>

      {lotDialog?.mode === 'create' && (
        <PortfolioLotDialog
          mode="create"
          open
          positionAssetIds={positionAssetIds}
          positionLimit={positionLimit}
          busy={mutationBusy}
          error={mutationError}
          upgradeUrl={mutationUpgradeUrl}
          onClose={closeLotDialog}
          onSubmit={createLot}
        />
      )}
      {lotDialog?.mode === 'edit' && (
        <PortfolioLotDialog
          mode="edit"
          open
          position={lotDialog.position}
          lot={lotDialog.lot}
          busy={mutationBusy}
          error={mutationError}
          upgradeUrl={mutationUpgradeUrl}
          onClose={closeLotDialog}
          onSubmit={patchLot}
        />
      )}
      <PortfolioDeleteDialog
        open={deleteSelection !== null}
        position={deleteSelection?.position ?? null}
        lot={deleteSelection?.lot ?? null}
        busy={mutationBusy}
        onClose={closeDeleteDialog}
        onConfirm={deleteLot}
      />
    </div>
  )
}

function PortfolioPageHeader({
  disabled = false,
  onAdd,
  positionLabel,
}: {
  disabled?: boolean
  onAdd?: () => void
  positionLabel?: string
}) {
  return (
    <header className="portfolio-page-header">
      <div>
        <h1 className="page-title">Portfolio</h1>
        <p className="page-subtitle">
          Purchase lots, raw market value, and unrealized performance.
        </p>
        {positionLabel && (
          <span className="portfolio-position-limit">{positionLabel}</span>
        )}
      </div>
      {onAdd && (
        <button
          type="button"
          className="btn btn-primary"
          disabled={disabled}
          onClick={onAdd}
        >
          <Plus size={16} aria-hidden="true" />
          Add lot
        </button>
      )}
    </header>
  )
}

function PortfolioSkeleton() {
  return (
    <div className="portfolio-loading" aria-label="Loading portfolio" aria-busy="true">
      <span className="sr-only">Loading portfolio...</span>
      <div className="portfolio-summary portfolio-summary-skeleton" aria-hidden="true">
        {[0, 1, 2, 3].map(item => (
          <div
            className="portfolio-summary-item"
            data-testid="portfolio-skeleton"
            key={item}
          >
            <span className="skeleton portfolio-skeleton-label" />
            <span className="skeleton portfolio-skeleton-value" />
            <span className="skeleton portfolio-skeleton-detail" />
          </div>
        ))}
      </div>
      <div className="skeleton portfolio-allocation-skeleton" aria-hidden="true" />
      <div className="portfolio-table-skeleton" aria-hidden="true">
        <span className="skeleton" />
        <span className="skeleton" />
        <span className="skeleton" />
      </div>
    </div>
  )
}
