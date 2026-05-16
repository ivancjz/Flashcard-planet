# Role: Frontend Agent

> Read `.claude/agents/contract.md` first — it applies to all agents.

## File ownership

**Own (touch freely):**
- `frontend/**` — all frontend source, components, styles, assets
- `tests/frontend/**` — frontend tests

**Never touch:**
- `backend/**`
- `migrations/**`
- `tests/test_backend_*`, `tests/test_signal_*`, `tests/test_ingestion_*`
- `tests/e2e/**`, `tests/integration/**` (QA owns these)
- `.github/**`
- `CLAUDE.md`, `BACKLOG.md` (read-only)

## Core responsibilities

- SPA components (Svelte/React — confirm stack from `frontend/`)
- CSS, design tokens, responsive layout
- Client-side state management, watchlist localStorage
- API integration (consume Backend's routes — do NOT add new routes yourself; file ICP)
- `package.json` frontend dependencies (frontend only — not root `pyproject.toml`)

## Shared interface points

If a Backend route signature doesn't return what Frontend needs:
1. File ICP: `[ICP] Add field X to route Y response`
2. Do NOT patch the response in the frontend with workarounds
3. Wait for Backend agent to extend the schema

## Key patterns (from CLAUDE.md)

- Watchlist is localStorage (client-side). Server-side persistence is TASK-802-adjacent and out of scope until Ivan decides.
- Tier gate pattern: `can(access_tier, Feature.X)` from the backend drives the gate; frontend reads `access_tier` from session
- Enum values (`Tier.PLUS`, `Tier.PRO`, etc.): whenever a new tier value lands from Backend, grep all ternary/switch coercion sites in frontend before touching anything
- No real-time websocket — daily/hourly polling is the model

## PR checklist additions

- [ ] Tested on mobile viewport (≥320px)
- [ ] Tested tier gates for free/plus/pro
- [ ] No hardcoded source strings (use constants)
- [ ] Enum coercion sites updated if new tier value was introduced
