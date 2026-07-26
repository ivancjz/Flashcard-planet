import type {
  Portfolio,
  PortfolioApiErrorDetail,
  PortfolioLot,
  PortfolioLotInput,
  PortfolioLotPatch,
} from '../types/portfolio'

export class PortfolioApiError extends Error {
  public readonly status: number
  public readonly detail: string | PortfolioApiErrorDetail | null

  constructor(
    status: number,
    detail: string | PortfolioApiErrorDetail | null,
  ) {
    super(
      typeof detail === 'string'
        ? detail
        : detail?.message ?? 'Portfolio request failed.',
    )
    this.name = 'PortfolioApiError'
    this.status = status
    this.detail = detail
  }
}

async function portfolioRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: 'same-origin',
  })
  if (!response.ok) {
    let detail: string | PortfolioApiErrorDetail | null = null
    try {
      const body = await response.json() as {
        detail?: string | PortfolioApiErrorDetail
      }
      detail = body.detail ?? null
    } catch {
      detail = null
    }
    throw new PortfolioApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function fetchPortfolio(): Promise<Portfolio> {
  return portfolioRequest<Portfolio>('/api/v1/portfolio')
}

export function createPortfolioLot(
  input: PortfolioLotInput,
): Promise<PortfolioLot> {
  return portfolioRequest<PortfolioLot>('/api/v1/portfolio/lots', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
}

export function updatePortfolioLot(
  lotId: string,
  patch: PortfolioLotPatch,
): Promise<PortfolioLot> {
  return portfolioRequest<PortfolioLot>(
    `/api/v1/portfolio/lots/${encodeURIComponent(lotId)}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    },
  )
}

export function deletePortfolioLot(lotId: string): Promise<void> {
  return portfolioRequest<void>(
    `/api/v1/portfolio/lots/${encodeURIComponent(lotId)}`,
    { method: 'DELETE' },
  )
}
