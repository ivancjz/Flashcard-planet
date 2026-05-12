# Flashcard Planet — Build Playbook

**Date:** 2026-05-13
**Type:** Executable build playbook (the HOW)
**Companion document:** `2026-05-13-phase-1-enterprise-rebuild.md` (the WHAT and WHY — the strategy spec)
**Audience:** A Claude session (any model, any chat) with access to Claude Code or terminal tooling, being asked to execute the Phase 1 rebuild
**Filename suggested in repo:** `.claude/playbooks/2026-05-13-build-playbook.md`

---

## How to use this document

This playbook is a step-by-step execution guide. Read **Part 1** in full before doing anything. Then proceed **phase by phase** — each phase is self-contained with prompts, commands, code patterns, and verification recipes. Do not skip ahead.

If you are a fresh Claude session reading this for the first time: pretend you know nothing about the project. Everything you need is below. If you find yourself wanting to ask Ivan a question that this document doesn't already answer, surface it — that means the playbook has a gap.

The companion strategy spec (`2026-05-13-phase-1-enterprise-rebuild.md`) is the authoritative source on **what** to build. This playbook is the authoritative source on **how** to build it. When they conflict, the spec wins on intent and this playbook wins on procedure.

---

## Part 1: Project Onboarding

### 1.1 What Flashcard Planet is

A market-intelligence platform for trading card investors. Tracks card prices across TCGPlayer and eBay, computes signals (SURGE / DRIFT / STIR / FLAT / COOLING), surfaces them through a React SPA, and notifies users via Discord and email.

The product positioning, in one sentence:

> Flashcard Planet is the founder-led, signal-first, multi-TCG intelligence platform that makes serious card investing legible — and feels like the cards themselves.

### 1.2 Who's involved

- **Ivan** (solo developer + product owner, GitHub `ivancjz`) — final decision authority. Bilingual EN/中文. Based Melbourne (AEST, UTC+10).
- **Claude Code** — execution agent inside the project boundary. Push to main permitted. This is who builds the code.
- **Codex CLI v0.118.0** — mandatory independent reviewer. Every PR must include a `## Codex Review` section.
- **claude.ai** — strategy/architecture. The spec and this playbook came from here. Surface ambiguities back to claude.ai, not to Claude Code.

If Claude Code, Codex, and Ivan disagree, the resolution is: one round of position-stating with evidence, then Ivan decides. No relitigation.

### 1.3 Current state of the project (as of 2026-05-13)

**Stack:**
- Backend: Python 3.13 + FastAPI + SQLAlchemy 2 + APScheduler + httpx + PostgreSQL 18
- Frontend: Vite + React 18 + TypeScript + plain CSS (Tailwind not yet adopted — that's Phase 1)
- Hosted on Railway Hobby plan
- No automatic backups (P0 risk — fixed in PR #14)

**Architecture invariants:**
- Branching: `feat/*` branches → PR → merge to main → Railway auto-deploys from main only
- `source` column values are `'pokemon_tcg_api'` (not shortened)
- `metadata->>'set_id'` is how set identity is stored in `assets` (no `set_code` column)
- TDD is standard; tests ship with every fix
- Every PR must have Codex review
- "Shipped" means verified in production via SQL/curl/observed behavior, not just merged

**Active production state:**
- Four scheduled jobs running: ingestion, bulk-refresh, signal-sweep, heartbeat
- Discord bot for alerts is live
- ~4,371 cards tracked across 25 Pokémon sets
- Yu-Gi-Oh scaffolded but not active (Phase 2)

**Known issues to avoid relitigating:**
- Issue A (orphaned `running` rows): RESOLVED — `cleanup_stale_runs()` shipped
- Issue B (3 days no Pokémon data): VERIFICATION PENDING — needs 7-day SQL evidence
- Issue C (audit log gaps): PARTIALLY RESOLVED — see PR #14 for completion

### 1.4 Three patterns that have hurt this project before

Be vigilant for all three. Per Ivan's memory of past incidents:

1. **"Designed but never ran"** — A feature exists in code but has never executed in production. Three things have been silently dormant in the past (signal sweep, eBay ingest, bulk-refresh over-aggressive import). Always verify execution in `scheduler_run_log` before claiming a feature works.

2. **"Claimed vs. shipped"** — Local code changes don't matter until they're committed, deployed, and observed. There has been a ~10-hour false belief that 429 fixes were live before, when they were only local. Always confirm deploy ID + production observation.

3. **"What's the evidence?"** — Ivan's discipline. Don't accept "this should work" without seeing the SQL output, the Discord alert, or the production log. Confident first-round answers have repeatedly been wrong.

### 1.5 Where everything lives in the repo

```
c:/Flashcard-planet/
├── backend/
│   ├── app/
│   │   ├── api/routes/         FastAPI route handlers
│   │   ├── services/           Business logic
│   │   ├── models/             SQLAlchemy models
│   │   ├── alembic/versions/   Database migrations
│   │   ├── scheduler.py        APScheduler jobs
│   │   ├── main.py             FastAPI app entry
│   │   └── email/templates/    Email HTML templates
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/                API adapter layer
│   │   ├── components/         React components
│   │   ├── pages/              Route-level pages
│   │   ├── hooks/              Custom React hooks
│   │   ├── lib/                Pure utility functions
│   │   ├── types/              TypeScript types
│   │   ├── styles/             CSS files (theme.css today; tokens.css after PR #15)
│   │   ├── i18n/               After PR #15 — locales and config
│   │   └── main.tsx            App entry
│   ├── public/
│   └── package.json
├── scripts/                     One-off scripts
├── docs/
│   ├── superpowers/
│   │   ├── specs/              Design specs
│   │   └── plans/              Build plans
│   └── runbooks/                After PR #14 — operational procedures
├── infra/                       After PR #21 — Uptime Kuma config etc.
├── .claude/
│   ├── specs/                   ← This playbook's spec lives here
│   ├── playbooks/               ← This playbook lives here
│   └── session-handoff-*.md     Git-ignored state snapshots
└── CLAUDE.md                    Auto-read by Claude Code on session start
```

---

## Part 2: Environment & Tooling

### 2.1 Required accounts (verify all exist before starting)

- [ ] **Railway** — backend hosting, Postgres
- [ ] **Cloudflare** — DNS, R2 (backups), Pages (frontend, post PR #24)
- [ ] **GitHub** — repo `ivancjz/flashcard-planet` (or equivalent)
- [ ] **Sentry** — error tracking (free tier, 5K errors/month)
- [ ] **PostHog** — product analytics (free tier, 1M events/month)
- [ ] **Resend** (or existing email provider) — transactional emails
- [ ] **Pokémon TCG API** key (already in use, in env vars)
- [ ] **eBay API** key (already in use)
- [ ] **Discord webhook** for alerts (already configured)

### 2.2 Required tools (verify on machine before starting)

```bash
node --version       # Should be 20.x or 22.x
npm --version        # Should be 10+
python --version     # Should be 3.13.x
pip --version        # Should be 24+
git --version        # Any modern version
psql --version       # 17 or 18, needed for pg_dump
docker --version     # Optional but useful for Uptime Kuma local test
```

Also needed:
- Claude Code (the agent) — confirm version with Ivan
- Codex CLI v0.118.0+
- Access to Railway CLI (`npm install -g @railway/cli`)
- Access to Cloudflare Wrangler CLI (`npm install -g wrangler`)

### 2.3 Required environment variables

Production environment variables in Railway (verify they exist; add the new ones in the relevant PR):

```bash
# Database
DATABASE_URL=postgresql://...           # Existing
DATABASE_URL_DIRECT=postgresql://...    # NEW (PR #14) — bypasses PgBouncer for migrations

# API keys
POKEMON_TCG_API_KEY=...                 # Existing
EBAY_APP_ID=...                         # Existing
EBAY_CERT_ID=...                        # Existing
EBAY_DAILY_BUDGET_LIMIT=...             # Existing

# Discord
DISCORD_WEBHOOK_URL=...                 # Existing

# Email
RESEND_API_KEY=...                      # Existing or add

# Scheduler
EBAY_SCHEDULED_INGEST_ENABLED=true      # Existing
SWEEP_BATCH_SIZE=100                    # Existing (don't bump above 100)

# NEW (PR #14)
CLOUDFLARE_R2_ACCOUNT_ID=...
CLOUDFLARE_R2_ACCESS_KEY_ID=...
CLOUDFLARE_R2_SECRET_ACCESS_KEY=...
CLOUDFLARE_R2_BUCKET=flashcard-planet-backups
SENTRY_DSN=...
POSTHOG_API_KEY=...
POSTHOG_HOST=https://app.posthog.com    # Or self-hosted URL

# Auth (existing per project memory)
SESSION_SECRET=...
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...
```

Frontend env vars (Vite, set in `.env.production` or Cloudflare Pages env):

```bash
VITE_API_BASE_URL=https://api.flashcardplanet.com  # Post PR #24
VITE_SENTRY_DSN=...                                # PR #14
VITE_POSTHOG_API_KEY=...                           # PR #14
VITE_POSTHOG_HOST=https://app.posthog.com
```

### 2.4 Local development setup (for a fresh Claude session)

```bash
# 1. Clone
git clone https://github.com/ivancjz/flashcard-planet.git
cd flashcard-planet

# 2. Backend
cd backend
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env       # Then edit with local credentials

# 3. Local Postgres
docker run -d --name fp-postgres \
  -e POSTGRES_PASSWORD=localdev \
  -e POSTGRES_DB=flashcard_planet \
  -p 5432:5432 postgres:18

# 4. Run migrations
alembic upgrade head

# 5. Backend dev server
uvicorn app.main:app --reload --port 8000

# 6. Frontend (new terminal)
cd ../frontend
npm install
npm run dev
# Visit http://localhost:5173
```

### 2.5 Verifying local setup works

```bash
# Backend health
curl http://localhost:8000/api/v1/web/stats
# Should return JSON with cards_tracked, breakout_signals, etc.

# Frontend
open http://localhost:5173
# Should see the dark landing page with floating cards

# Database
psql $DATABASE_URL -c "SELECT COUNT(*) FROM assets;"
# Should return a non-zero count if seed data is loaded
```

---

## Part 3: Pre-flight Checklist

Before starting ANY phase, run through this checklist. Skipping items here causes pain later.

- [ ] You have read Parts 0, 1, 2 of the strategy spec (`2026-05-13-phase-1-enterprise-rebuild.md`)
- [ ] You have read Part 1 of this playbook
- [ ] You have Claude Code working in the project directory
- [ ] You have Codex CLI ready to run reviews
- [ ] Ivan is available for: founder voice copy, Chinese translation review, escalation
- [ ] Railway, Cloudflare, Sentry, PostHog accounts are all confirmed
- [ ] You understand the three failure patterns from section 1.4
- [ ] You have read `CLAUDE.md` in the repo if it exists
- [ ] You have read the most recent `.claude/session-handoff-*.md` if one exists
- [ ] You have the strategy spec open in another tab — you'll reference it constantly
- [ ] You have set up your terminal to log commands (so you can paste verification output into PR descriptions)

If any are unchecked, stop and resolve them. The cost of a 30-minute setup is much less than the cost of debugging a missing credential mid-deploy.

---

## Part 4: The Build Sequence

Each phase below corresponds to a PR in the strategy spec. The strategy spec defines goal/scope/acceptance; this playbook defines step-by-step execution.

**Recommended parallelization:**
- PR #13 and PR #14 can be built in parallel (different code paths)
- After both ship: PR #15 (foundation, sequential)
- After #15: PR #16, #17, #18 can be built in parallel
- PR #19 needs #15 + #18 (foundation + joy moments)
- PR #20+ are sequential

---

### Phase 1: PR #13 — Critical Bug Fixes

**Estimated time:** 1–2 days
**Branch:** `feat/pr-13-critical-bug-fixes`
**Strategy spec reference:** PR #13 section

#### Prompt to give Claude Code to start

```
Read .claude/specs/2026-05-13-phase-1-enterprise-rebuild.md section "PR #13".
Read .claude/playbooks/2026-05-13-build-playbook.md "Phase 1" in full.
Create branch feat/pr-13-critical-bug-fixes from main.
Execute the four bug fixes in the order listed. After each fix, run TypeScript build and verify no console errors.
Do NOT modify any files outside the four specified. Do NOT add Tailwind or shadcn (those are in PR #15).
Stop after the fourth fix and surface the PR for Codex review.
```

#### Step-by-step execution

**Step 1: Fix star/badge overlap in `CardGrid.tsx`**

In `frontend/src/components/CardGrid.tsx`, the watchlist star is at `top: 8; right: 8` (absolute) and collides with the `<SignalBadge>` in the card header row.

Change the star button positioning from top-right of the card to **top-left of the card art**, with a dark scrim:

```tsx
// Before (causes overlap):
<button
  onClick={e => { e.stopPropagation(); onToggleWatch() }}
  style={{
    position: 'absolute', top: 8, right: 8, zIndex: 2,
    // ...
  }}
>

// After (no overlap):
<button
  onClick={e => { e.stopPropagation(); onToggleWatch() }}
  style={{
    position: 'absolute', top: 6, left: 6, zIndex: 2,
    background: 'rgba(12,12,16,0.7)',
    backdropFilter: 'blur(4px)',
    border: 'none', borderRadius: '50%',
    width: 26, height: 26, cursor: 'pointer',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: 14, color: watched ? 'var(--gold)' : 'rgba(255,255,255,0.7)',
    transition: 'color 0.15s, transform 0.1s',
  }}
>
```

The wrapper around `<CardArt>` needs `position: relative` so the absolute child positions correctly. Confirm before/after.

**Step 2: Slow the ticker and add reduced-motion fallback**

In `frontend/src/styles/theme.css`, find the ticker section:

```css
/* Before */
.ticker-inner {
  display: inline-flex;
  align-items: center;
  gap: 40px;
  padding: 0 40px;
  animation: scroll-ticker 35s linear infinite;
}
```

Change to:

```css
/* After */
.ticker-inner {
  display: inline-flex;
  align-items: center;
  gap: 40px;
  padding: 0 40px;
  /*
   * Ticker scrolls right-to-left at 90s (industry standard for financial tickers).
   * Earlier 35s was too fast to read; user feedback was the underlying complaint.
   * Do NOT reverse direction — RTL reads naturally as items enter from the right.
   */
  animation: scroll-ticker 90s linear infinite;
}

@media (prefers-reduced-motion: reduce) {
  .ticker-inner {
    animation: none;
    transform: none;
  }
}
```

In the `TickerBar.tsx` component, when `prefers-reduced-motion` is set, render the first 8 items statically (no scroll). Use the `useReducedMotion` hook from Motion library, OR a simple `useState` + `matchMedia` check.

**Step 3: Stop horizontal page scroll**

Add to `frontend/src/styles/theme.css` at the top of the body section:

```css
html, body {
  overflow-x: hidden;
  max-width: 100vw;
}
```

Then **find the root cause**. Run:

```bash
cd frontend
grep -rn "100vw\|max-content\|absolute.*right:-\|width:.*1[2-9][0-9][0-9]px" src/
```

Most likely culprits in the existing code:
- The hero floating cards using `position: absolute` with translates that overshoot
- The ticker's `width: max-content`
- Any element with hardcoded width > 1200px

Fix the root cause; document what it was in the PR description.

**Step 4: Reorder the NavBar**

In `frontend/src/components/NavBar.tsx`, restructure to this order:

```
[Logo]  [Market]  [Watchlist (count)]  [Alerts (unread)]   ─spacer─   [PRO badge]  [Avatar/Email]
```

The current code has `Sign out` as a top-level nav item — move it into an avatar dropdown. Since shadcn `DropdownMenu` isn't available until PR #15, implement a minimal manual dropdown:

```tsx
{email && (
  <div style={{ position: 'relative' }}>
    <button
      onClick={() => setMenuOpen(!menuOpen)}
      style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '6px 10px', borderRadius: 6,
        background: menuOpen ? 'var(--bg-elevated)' : 'transparent',
        color: 'var(--text-secondary)',
        cursor: 'pointer',
      }}
    >
      <span style={{ fontSize: 12 }}>{truncateEmail(email)}</span>
      <ChevronDownIcon />
    </button>
    {menuOpen && (
      <div style={{
        position: 'absolute', top: 'calc(100% + 4px)', right: 0,
        background: 'var(--bg-floating)', border: '1px solid var(--border-default)',
        borderRadius: 8, minWidth: 180, padding: 6,
        boxShadow: 'var(--shadow-lg)',
        zIndex: 50,
      }}>
        <div style={{ padding: '8px 12px', fontSize: 11, color: 'var(--text-muted)' }}>
          {email}
        </div>
        <hr style={{ border: 'none', borderTop: '1px solid var(--border-subtle)', margin: '4px 0' }} />
        <button onClick={() => nav('/account')} className="dropdown-item">Account</button>
        <button onClick={() => { window.location.href = '/auth/logout' }} className="dropdown-item">Sign out</button>
      </div>
    )}
  </div>
)}
```

Watchlist comes before Alerts. PRO badge sits to the immediate left of the avatar (not floating in the nav).

#### Verification recipe

```bash
# 1. TypeScript build passes
cd frontend
npx tsc --noEmit
# Expected: no errors

# 2. Production build succeeds
npm run build
# Expected: no errors, dist/ created

# 3. Visual check — open dev server
npm run dev
# Open http://localhost:5173
# - Resize browser from 320px to 2560px wide
# - At every width, confirm: no horizontal scrollbar
# - Hover a card: star is top-left, badge is top-right of header, no overlap
# - Watch the ticker: text is readable as it passes (not blurred from speed)
# - Open DevTools, Settings → "Emulate CSS prefers-reduced-motion: reduce"
# - Reload: ticker should be static (no animation)

# 4. Navbar check
# - Logo on left
# - Market, Watchlist, Alerts in that order in primary nav
# - PRO badge + avatar on right
# - Click avatar: dropdown opens with Account, Sign out
# - Press Escape: dropdown should close (add this if missing)
```

#### Acceptance criteria checklist

- [ ] No horizontal scrollbar at any viewport from 320px to 2560px
- [ ] Ticker takes 90 seconds for one cycle (count it)
- [ ] Star button never overlaps SignalBadge at any card width
- [ ] Navbar order matches: Logo · Market · Watchlist · Alerts · (spacer) · PRO · Avatar
- [ ] `prefers-reduced-motion: reduce` stops the ticker entirely
- [ ] `npx tsc --noEmit` exits 0
- [ ] `npm run build` succeeds
- [ ] No new console errors in DevTools

#### Common failures and recovery

- **TypeScript errors in unrelated files** → don't fix them in this PR. Note them and surface to Ivan.
- **The horizontal scroll comes back at narrow widths** → likely the landing page floating cards. Wrap them in `<div style={{ overflow: 'hidden', position: 'relative' }}>` and constrain.
- **The dropdown stays open when you click outside** → add a `useEffect` with `document.addEventListener('click', closeMenu)` cleanup pattern.

#### Codex review prompt (paste verbatim into Codex)

```
Review PR #13 for Flashcard Planet. Focus on:
1. Does the star/badge fix prevent ALL overlap states, including narrow mobile widths (320–375px) and cards with very long names?
2. Is the ticker direction decision (right-to-left, slowed to 90s) explained in a code comment so it doesn't get re-flipped?
3. Is the horizontal-scroll root cause fixed, or is overflow-x: hidden papering over something that will cause clipping bugs later?
4. Does the navbar reorder break any existing tests, link styles, or active-route logic?
5. Does the prefers-reduced-motion fallback render correctly when no animation is playing?
6. Does the avatar dropdown close on click-outside and on Escape?
```

#### Sign-off

- [ ] Codex review section appended to PR
- [ ] Codex concerns addressed or surfaced to Ivan
- [ ] Merged to main
- [ ] Railway auto-deploy completed (confirm deploy ID in PR)
- [ ] Production smoke test completed (open the live site, do the 4 visual checks)
- [ ] Mark PR #13 as done in this playbook

---

### Phase 2: PR #14 — Backend Foundation

**Estimated time:** 2–3 days
**Branch:** `feat/pr-14-backend-foundation`
**Strategy spec reference:** PR #14 section
**CRITICAL:** Backups (step 1) must succeed before any subsequent user-facing PR can proceed.

#### Prompt to give Claude Code to start

```
Read .claude/specs/2026-05-13-phase-1-enterprise-rebuild.md section "PR #14".
Read .claude/playbooks/2026-05-13-build-playbook.md "Phase 2" in full.
This PR is the foundation. Backups are P0 — they ship first within this PR.
Create branch feat/pr-14-backend-foundation from main.
Execute steps in the order listed (1: backups, 2: PgBouncer, 3: rate limiting, 4: audit log, 5: Sentry+PostHog, 6: structlog).
After each step, verify with the included recipe.
Do NOT skip the restore drill in step 1 — an untested backup is no backup.
```

#### Step 1: Daily PostgreSQL backups to Cloudflare R2

**1a. Create R2 bucket**

In Cloudflare dashboard → R2 → Create bucket:
- Name: `flashcard-planet-backups`
- Location hint: closest to Railway region

Create an R2 API token with read/write on this bucket. Add credentials to Railway env vars (per section 2.3).

**1b. Write the backup script**

Create `scripts/backup_postgres.py`:

```python
"""Daily Postgres backup script. Uploads pg_dump output to Cloudflare R2."""
from __future__ import annotations

import gzip
import os
import subprocess
import sys
from datetime import datetime, UTC
from pathlib import Path

import boto3
import structlog

log = structlog.get_logger()


def main() -> int:
    database_url = os.environ["DATABASE_URL_DIRECT"]  # Bypass PgBouncer for pg_dump
    r2_bucket = os.environ["CLOUDFLARE_R2_BUCKET"]
    r2_account = os.environ["CLOUDFLARE_R2_ACCOUNT_ID"]
    r2_access_key = os.environ["CLOUDFLARE_R2_ACCESS_KEY_ID"]
    r2_secret_key = os.environ["CLOUDFLARE_R2_SECRET_ACCESS_KEY"]

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    local_path = Path(f"/tmp/flashcard-planet-{today}.dump")
    log.info("backup_start", date=today)

    # 1. pg_dump (custom format, compressed)
    try:
        subprocess.run(
            [
                "pg_dump",
                "--format=custom",
                "--compress=9",
                "--no-owner",
                "--no-privileges",
                f"--file={local_path}",
                database_url,
            ],
            check=True,
            capture_output=True,
        )
        size_mb = local_path.stat().st_size / 1024 / 1024
        log.info("pg_dump_complete", size_mb=round(size_mb, 2))
    except subprocess.CalledProcessError as e:
        log.error("pg_dump_failed", stderr=e.stderr.decode()[:500])
        return 1

    # 2. Upload to R2
    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{r2_account}.r2.cloudflarestorage.com",
            aws_access_key_id=r2_access_key,
            aws_secret_access_key=r2_secret_key,
            region_name="auto",
        )
        key = f"daily/{today}.dump"
        s3.upload_file(str(local_path), r2_bucket, key)
        log.info("r2_upload_complete", key=key, bucket=r2_bucket)
    except Exception as e:
        log.error("r2_upload_failed", error=str(e))
        return 1
    finally:
        local_path.unlink(missing_ok=True)

    log.info("backup_success", date=today)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Add `boto3` to `requirements.txt`.

**1c. Register the job in `scheduler.py`**

```python
# In backend/app/scheduler.py, add to the existing scheduler setup:
from backend.scripts.backup_postgres import main as run_backup

scheduler.add_job(
    func=run_backup_wrapped,  # see below
    trigger="cron",
    hour=3,
    minute=30,
    id="postgres_backup",
    name="Daily Postgres backup to R2",
    replace_existing=True,
    coalesce=True,
)

def run_backup_wrapped():
    """Wrapper that logs to scheduler_run_log and alerts on failure."""
    from backend.app.services.scheduler_audit import log_run_start, log_run_end
    run_id = log_run_start("postgres_backup")
    try:
        exit_code = run_backup()
        if exit_code != 0:
            send_discord_alert("⚠️ Postgres backup FAILED. Check logs.")
            log_run_end(run_id, status="failed")
        else:
            log_run_end(run_id, status="ok")
    except Exception as e:
        send_discord_alert(f"⚠️ Postgres backup CRASHED: {e}")
        log_run_end(run_id, status="failed")
        raise
```

**1d. THE RESTORE DRILL** — this is non-negotiable

Create `docs/runbooks/restore-from-backup.md`:

```markdown
# Restore from R2 Backup — Runbook

## When to use this
- Accidental DROP TABLE / DROP DATABASE
- Corrupted data (suspected or confirmed)
- Disaster recovery (Railway region failure, etc.)

## Procedure

### 1. Identify the backup to restore
List recent backups:
```bash
aws --endpoint-url=https://${CF_ACCOUNT}.r2.cloudflarestorage.com \
    s3 ls s3://flashcard-planet-backups/daily/ | tail -20
```

### 2. Download the chosen backup
```bash
aws --endpoint-url=https://${CF_ACCOUNT}.r2.cloudflarestorage.com \
    s3 cp s3://flashcard-planet-backups/daily/2026-05-13.dump /tmp/restore.dump
```

### 3. Create a scratch database (do NOT restore over production)
```bash
psql $DATABASE_URL_DIRECT -c "CREATE DATABASE flashcard_planet_restore_test;"
```

### 4. Restore to the scratch database
```bash
pg_restore \
    --dbname=postgresql://user:pass@host:5432/flashcard_planet_restore_test \
    --no-owner --no-privileges \
    /tmp/restore.dump
```

### 5. Verify the restore
```bash
psql postgresql://...restore_test -c "SELECT COUNT(*) FROM assets;"
psql postgresql://...restore_test -c "SELECT MAX(captured_at) FROM price_history;"
```

### 6. If production restore is needed
- STOP all production writes (pause scheduler)
- Coordinate with Ivan — this is a P0 decision
- pg_restore over the production database with --clean flag
- Resume scheduler only after verification

## DO NOT DO
- Never restore directly into production without confirming the backup with a test restore first.
- Never delete a backup. Use lifecycle policies to archive older ones to cold storage.
```

**RUN THE DRILL.** Before committing the PR, execute steps 1–5 of the runbook against a real backup. Document timing in the PR description: *"Backup restore drill: 1.2GB dump downloaded in 18s, restored to scratch DB in 4m12s, all row counts match production within expected delta."*

#### Step 2: PgBouncer connection pooling

Check Railway's plugin marketplace for PgBouncer. If available, install it and follow Railway's docs.

If not available as a managed plugin, deploy as a sidecar service:

1. Create a new Railway service from this Dockerfile:
```dockerfile
FROM edoburu/pgbouncer:latest
COPY pgbouncer.ini /etc/pgbouncer/pgbouncer.ini
COPY userlist.txt /etc/pgbouncer/userlist.txt
```

2. `pgbouncer.ini`:
```ini
[databases]
flashcard_planet = host=<railway-postgres-host> port=5432 dbname=flashcard_planet

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432
auth_type = scram-sha-256
auth_file = /etc/pgbouncer/userlist.txt
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 25
server_lifetime = 3600
server_idle_timeout = 600
```

3. After deploy, update `DATABASE_URL` (used by app) to point through PgBouncer. Keep `DATABASE_URL_DIRECT` (used by migrations and pg_dump) pointing direct.

4. In `backend/app/database.py` (or wherever SQLAlchemy is configured), set:
```python
engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,  # PgBouncer handles pooling; SQLAlchemy shouldn't double-pool
)
```

**Compatibility note:** transaction-mode pooling breaks `LISTEN/NOTIFY`, prepared statements, and some session features. Audit code for any of these. If found, use the direct URL for those specific operations.

#### Step 3: Rate limiting

Add `slowapi` to `requirements.txt`:

```
slowapi==0.1.9
```

In `backend/app/main.py`:

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

def get_user_or_ip(request):
    """Rate-limit key: authenticated user ID if available, else IP."""
    user = getattr(request.state, "user", None)
    if user:
        return f"user:{user.id}"
    return f"ip:{get_remote_address(request)}"

limiter = Limiter(key_func=get_user_or_ip)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

Decorate routes:

```python
# backend/app/api/routes/web.py
@router.get("/cards")
@limiter.limit("60/minute", per_method=True)  # Default; overridden per-user below
async def get_cards(request: Request, ...):
    user = getattr(request.state, "user", None)
    # Apply tiered limits in middleware or here
    ...
```

For tier-based limits, use a middleware that sets the limit dynamically based on `user.access_tier`. Example pattern:

```python
TIER_LIMITS = {
    "anonymous": "60/minute",
    "free": "120/minute",
    "pro": "600/minute",
    "trader": "1800/minute",
}
```

Exempt internal/health endpoints: `/health`, `/api/internal/*` (scheduler heartbeat).

#### Step 4: Audit log table

Create Alembic migration `0010_add_audit_log.py`:

```python
"""Add audit_log table

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-13
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0010'
down_revision = '0009'

def upgrade():
    op.create_table(
        'audit_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('event_type', sa.String(64), nullable=False),
        sa.Column('ip_address', postgresql.INET(), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('ix_audit_log_user_created', 'audit_log', ['user_id', sa.text('created_at DESC')])
    op.create_index('ix_audit_log_event_created', 'audit_log', ['event_type', sa.text('created_at DESC')])

def downgrade():
    op.drop_table('audit_log')
```

Create `backend/app/services/audit_service.py`:

```python
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from backend.app.models.audit_log import AuditLog


def log_audit_event(
    db: Session,
    event_type: str,
    request: Request | None = None,
    user_id: UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append a row to audit_log. Never raises; logs failures and moves on."""
    try:
        entry = AuditLog(
            event_type=event_type,
            user_id=user_id,
            ip_address=request.client.host if request and request.client else None,
            user_agent=request.headers.get("user-agent") if request else None,
            metadata=metadata,
        )
        db.add(entry)
        db.commit()
    except Exception as e:
        # Never let audit logging break the request
        import structlog
        structlog.get_logger().warning("audit_log_failed", event_type=event_type, error=str(e))
```

Call sites to add:
- Auth login success / failure
- Signal threshold changes
- Watchlist add / remove
- Rate limit hits (in the exception handler)

#### Step 5: Sentry + PostHog

**Backend Sentry:**

```bash
pip install 'sentry-sdk[fastapi]'
```

```python
# backend/app/main.py — at the top, before FastAPI app creation
import os
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

if os.getenv("SENTRY_DSN"):
    sentry_sdk.init(
        dsn=os.environ["SENTRY_DSN"],
        environment=os.getenv("ENVIRONMENT", "production"),
        traces_sample_rate=0.1,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
    )
```

**Frontend Sentry:**

```bash
cd frontend && npm install @sentry/react
```

```tsx
// frontend/src/main.tsx — at the top
import * as Sentry from "@sentry/react"

if (import.meta.env.VITE_SENTRY_DSN) {
  Sentry.init({
    dsn: import.meta.env.VITE_SENTRY_DSN,
    environment: import.meta.env.MODE,
    tracesSampleRate: 0.1,
  })
}
```

**PostHog:**

```bash
# Backend
pip install posthog

# Frontend
cd frontend && npm install posthog-js
```

Initialize PostHog in `main.tsx` after Sentry, and create a helper for typed event tracking:

```ts
// frontend/src/lib/analytics.ts
import posthog from 'posthog-js'

if (import.meta.env.VITE_POSTHOG_API_KEY) {
  posthog.init(import.meta.env.VITE_POSTHOG_API_KEY, {
    api_host: import.meta.env.VITE_POSTHOG_HOST,
    capture_pageview: true,
    autocapture: false,  // We track events explicitly
  })
}

type EventName =
  | 'page_view'
  | 'card_watched'
  | 'card_unwatched'
  | 'signal_alert_fired'
  | 'signup_started'
  | 'signup_completed'
  | 'upgrade_clicked'
  | 'language_changed'

export function track(event: EventName, properties?: Record<string, unknown>) {
  posthog.capture(event, properties)
}

export function identifyUser(userId: string, email: string) {
  // Hash email before sending to avoid PII leakage
  const hashedEmail = sha256(email)  // implement or import
  posthog.identify(userId, { email_hash: hashedEmail })
}
```

#### Step 6: structlog for backend

```bash
pip install structlog
```

Replace the existing `_log_json(level, event, **fields)` pattern:

```python
# backend/app/logging_config.py (new)
import logging
import structlog

def configure_logging():
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

Call `configure_logging()` early in `main.py`. Then replace ad-hoc `logger.warning(json.dumps(...))` calls with `log.warning(event_name, **fields)`.

Add request-scoped binding via middleware:

```python
@app.middleware("http")
async def bind_request_context(request: Request, call_next):
    structlog.contextvars.bind_contextvars(
        request_id=str(uuid4()),
        path=request.url.path,
        method=request.method,
    )
    response = await call_next(request)
    structlog.contextvars.clear_contextvars()
    return response
```

#### Verification recipe

```bash
# 1. Verify backup runs
# Wait until 03:30 UTC OR trigger manually:
python -c "from backend.scripts.backup_postgres import main; main()"
# Expected: outputs JSON with backup_success at the end

# Check R2:
aws --endpoint-url=https://${CF_ACCOUNT}.r2.cloudflarestorage.com \
    s3 ls s3://flashcard-planet-backups/daily/
# Expected: today's dump file listed

# Check scheduler_run_log:
psql $DATABASE_URL -c "SELECT job_name, status, started_at, finished_at FROM scheduler_run_log WHERE job_name='postgres_backup' ORDER BY started_at DESC LIMIT 5;"

# 2. PgBouncer
# Verify the app is connecting through PgBouncer (port 6432 or whatever):
psql -h $PGBOUNCER_HOST -p 6432 -U $USER -c "SHOW POOLS;" pgbouncer
# Expected: a pools listing showing your app

# 3. Rate limiting
for i in {1..200}; do curl -s -o /dev/null -w "%{http_code}\n" https://api.flashcardplanet.com/api/v1/web/cards; done | sort | uniq -c
# Expected: most 200s, then 429s once limit hit

# 4. Audit log
psql $DATABASE_URL -c "SELECT event_type, COUNT(*) FROM audit_log GROUP BY event_type;"
# Expected: at least 3 distinct event types after some activity

# 5. Sentry
# In Sentry dashboard, manually trigger an error from frontend:
# Open browser DevTools console on production, run:
Sentry.captureException(new Error("Test from production"))
# Expected: error appears in Sentry within 1 minute

# 6. PostHog
# Similar: trigger a page view, check PostHog Live Events tab
```

#### Acceptance criteria checklist

- [ ] pg_dump runs and uploads to R2 daily (verified 7 days running)
- [ ] Restore drill completed end-to-end against a test database, timing documented in PR
- [ ] PgBouncer is in front of Postgres; app connects through it
- [ ] No regression in `/api/v1/web/cards` p95 latency (measure before/after)
- [ ] Rate limits return 429 with Retry-After header (curl-verifiable)
- [ ] Internal/health endpoints are exempt from rate limiting
- [ ] `audit_log` table receives entries from at least 3 event types in production
- [ ] Sentry receives errors from both backend and frontend in production
- [ ] PostHog receives at least one event in production
- [ ] Discord alert fires if backup job fails (test by temporarily breaking R2 creds)
- [ ] No raw email addresses sent to PostHog (hashed only)
- [ ] structlog produces valid JSON in production logs

#### Common failures and recovery

- **pg_dump can't connect via DATABASE_URL_DIRECT** → confirm the env var is set in Railway and bypasses PgBouncer
- **R2 upload returns 403** → check R2 token scope; needs read+write on the specific bucket
- **PgBouncer breaks the app at startup** → likely a prepared-statement issue. Fall back to session mode pool temporarily and investigate
- **Rate limit firing on internal scheduler calls** → ensure scheduler uses direct internal endpoints, exempt them in the limiter
- **Sentry not receiving events** → check `VITE_` prefix on frontend env vars (Vite only exposes prefixed vars)

#### Codex review prompt

```
Review PR #14. This is the foundation PR — if anything is wrong here, every later PR inherits the bug.
Focus on:
1. Is the backup actually verified by a restore drill, or is it just "the script runs without erroring"? An untested backup is no backup.
2. Are R2 credentials stored as Railway env vars only (no secrets in repo or logs)?
3. Does PgBouncer's transaction pool mode break any code that assumes session-mode pooling? Check for: prepared statements, server-side cursors, LISTEN/NOTIFY, advisory locks.
4. Are rate limits applied to internal scheduler/health-check endpoints accidentally? They should be exempt.
5. Does the audit log capture enough for a future SOC2-style audit, or is it too narrow?
6. Is PII handling correct? Specifically: no raw emails or IP addresses going to PostHog without hashing.
7. Is structlog actually replacing the old _log_json pattern, or both running in parallel (which would double-log)?
```

#### Sign-off

- [ ] Restore drill completed and documented
- [ ] All 12 acceptance criteria pass
- [ ] Codex review section appended
- [ ] Merged to main
- [ ] Verified in production for 24 hours (backup ran, audit log has entries, no Sentry alerts about the foundation itself)

---

### Phase 3: PR #15 — Frontend Foundation

**Estimated time:** 3–4 days
**Branch:** `feat/pr-15-frontend-foundation`
**Strategy spec reference:** PR #15 section

This is the migration PR. It touches almost every component file. Visual output should be near-identical post-migration (within 5% diff per acceptance criteria), but the underlying stack is now Tailwind + shadcn + TanStack Query + Lucide + i18n.

#### Prompt to give Claude Code to start

```
Read .claude/specs/2026-05-13-phase-1-enterprise-rebuild.md section "PR #15" and section 1 (Design System).
Read .claude/playbooks/2026-05-13-build-playbook.md "Phase 3" in full.
This is a migration PR — visual output should remain ~95% identical. Do not redesign anything in this PR; just migrate the stack.
Create branch feat/pr-15-frontend-foundation from main.
Execute the steps in order. Do NOT proceed to next step until current step's verification passes.
Stop and surface to Ivan before adding any shadcn component that wasn't on the list.
```

#### Step 1: Install Tailwind and migrate tokens

```bash
cd frontend
npm install -D tailwindcss postcss autoprefixer @tailwindcss/typography
npx tailwindcss init -p
```

Create `tailwind.config.ts`:

```ts
import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        bg: {
          base: 'var(--bg-base)',
          surface: 'var(--bg-surface)',
          elevated: 'var(--bg-elevated)',
          floating: 'var(--bg-floating)',
        },
        text: {
          primary: 'var(--text-primary)',
          secondary: 'var(--text-secondary)',
          muted: 'var(--text-muted)',
          disabled: 'var(--text-disabled)',
          inverse: 'var(--text-inverse)',
        },
        border: {
          subtle: 'var(--border-subtle)',
          DEFAULT: 'var(--border-default)',
          strong: 'var(--border-strong)',
        },
        gold: {
          DEFAULT: 'var(--gold)',
          hover: 'var(--gold-hover)',
          dim: 'var(--gold-dim)',
          glow: 'var(--gold-glow)',
        },
        signal: {
          surge: 'var(--surge)',
          drift: 'var(--drift)',
          stir: 'var(--stir)',
          flat: 'var(--flat)',
          cooling: 'var(--cooling)',
          nodata: 'var(--nodata)',
        },
        price: {
          up: 'var(--price-up)',
          down: 'var(--price-down)',
        },
      },
      fontFamily: {
        display: ['Geist', 'system-ui', 'sans-serif'],
        body: ['Inter', 'Noto Sans SC', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        '2xs': ['10px', '14px'],
        xs: ['11px', '15px'],
        sm: ['12px', '16px'],
        base: ['13px', '18px'],
        md: ['14px', '20px'],
        lg: ['16px', '24px'],
        xl: ['20px', '28px'],
        '2xl': ['24px', '32px'],
        '3xl': ['32px', '40px'],
        display: ['48px', '56px'],
        hero: ['72px', '80px'],
      },
      borderRadius: {
        sm: 'var(--radius-sm)',
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)',
        xl: 'var(--radius-xl)',
        pill: 'var(--radius-pill)',
      },
      boxShadow: {
        sm: 'var(--shadow-sm)',
        md: 'var(--shadow-md)',
        lg: 'var(--shadow-lg)',
        gold: 'var(--shadow-gold)',
      },
      transitionDuration: {
        instant: '80ms',
        fast: '150ms',
        normal: '250ms',
        slow: '400ms',
        deliberate: '600ms',
      },
    },
  },
  plugins: [require('@tailwindcss/typography')],
} satisfies Config
```

Move CSS variables from `theme.css` into a new `frontend/src/styles/tokens.css` (per strategy spec section 1.2). Import order in `main.tsx`:

```ts
import './styles/tokens.css'
import './styles/motion.css'
import './styles/tailwind.css'  // Tailwind directives
import './styles/holo.css'      // Only after PR #18
```

Where `tailwind.css` is:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

#### Step 2: Install and configure shadcn/ui

```bash
npx shadcn-ui@latest init
```

Answer prompts:
- TypeScript: yes
- Style: New York (denser, more enterprise feel than Default)
- Base color: Zinc
- CSS variables: yes
- Import alias: `@/components`

Add initial primitives:

```bash
npx shadcn-ui@latest add button card dialog dropdown-menu popover tabs tooltip select switch input label separator badge skeleton sonner command
```

Verify these land in `src/components/ui/`.

Replace existing custom buttons / cards / dropdowns with shadcn equivalents.

#### Step 3: Install TanStack Query

```bash
npm install @tanstack/react-query @tanstack/react-query-devtools
```

Create `src/api/queryClient.ts`:

```ts
import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      retry: 1,
      refetchOnWindowFocus: true,
    },
  },
})
```

Create `src/api/queryKeys.ts`:

```ts
export const queryKeys = {
  stats: () => ['stats'] as const,
  ticker: () => ['ticker'] as const,
  cards: (params: { signal?: string; sort?: string; offset?: number }) =>
    ['cards', params] as const,
  card: (id: string) => ['card', id] as const,
  alerts: (filter?: string) => ['alerts', filter] as const,
  watchlist: (userId: string) => ['watchlist', userId] as const,
}
```

Wrap app in provider in `main.tsx`:

```tsx
import { QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { queryClient } from './api/queryClient'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>{/* ... */}</Routes>
      </BrowserRouter>
      {import.meta.env.DEV && <ReactQueryDevtools />}
    </QueryClientProvider>
  </StrictMode>
)
```

Migrate every `fetch` call. Example pattern — before:

```tsx
const [stats, setStats] = useState<MarketStats | null>(null)
useEffect(() => { fetchStats().then(setStats) }, [])
```

After:

```tsx
const { data: stats } = useQuery({
  queryKey: queryKeys.stats(),
  queryFn: fetchStats,
})
```

#### Step 4: Install Lucide React + audit emojis

```bash
npm install lucide-react
```

Create `src/components/icons/index.ts` as a re-export module:

```ts
export {
  Star, Bell, TrendingUp, TrendingDown, Activity, BarChart3,
  Search, Settings, User, LogOut, Menu, X, ChevronDown, ChevronRight,
  Eye, EyeOff, Sparkles, Zap, Info, AlertCircle, CheckCircle,
  Globe, ExternalLink, ArrowUpRight, ArrowDownRight,
  ChevronLeft, Plus, Minus, Filter, ArrowUpDown,
} from 'lucide-react'
```

Audit and replace:

```bash
cd frontend
grep -rn "📊\|⚡\|🔔\|📈\|⭐\|☆\|🎴\|🌐\|✓\|✗" src/ | grep -v "i18n/locales"
```

Every match in component files → replace with a Lucide icon. (Strings in i18n locale files are content, not chrome — leave them unless they're emoji-as-decoration; replace those too.)

#### Step 5: Install Motion library

```bash
npm install motion
```

Create `src/lib/motion-variants.ts`:

```ts
export const fadeInUp = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -8 },
  transition: { duration: 0.25, ease: [0.22, 1, 0.36, 1] },
}

export const fadeIn = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
  transition: { duration: 0.15 },
}

export const scaleIn = {
  initial: { opacity: 0, scale: 0.95 },
  animate: { opacity: 1, scale: 1 },
  transition: { duration: 0.25, ease: [0.22, 1, 0.36, 1] },
}

export const signalEntrance = {
  initial: { opacity: 0, scale: 0.8 },
  animate: { opacity: 1, scale: 1 },
  transition: { duration: 0.4, ease: [0.34, 1.56, 0.64, 1] },
}
```

#### Step 6: Wire react-i18next

```bash
npm install react-i18next i18next i18next-browser-languagedetector
```

Create `src/i18n/index.ts`:

```ts
import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

// Static imports keep things simple; switch to lazy loading later if bundle size demands
import enCommon from './locales/en/common.json'
import enMarket from './locales/en/market.json'
import enCardDetail from './locales/en/card-detail.json'
import enAlerts from './locales/en/alerts.json'
import enLanding from './locales/en/landing.json'
import enOnboarding from './locales/en/onboarding.json'
import enEmptyStates from './locales/en/empty-states.json'
import enErrors from './locales/en/errors.json'
import enSignals from './locales/en/signals.json'

import zhCommon from './locales/zh-CN/common.json'
import zhMarket from './locales/zh-CN/market.json'
// ... etc

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    fallbackLng: 'en',
    supportedLngs: ['en', 'zh-CN'],
    interpolation: { escapeValue: false },
    resources: {
      en: {
        common: enCommon,
        market: enMarket,
        'card-detail': enCardDetail,
        alerts: enAlerts,
        landing: enLanding,
        onboarding: enOnboarding,
        'empty-states': enEmptyStates,
        errors: enErrors,
        signals: enSignals,
      },
      'zh-CN': {
        common: zhCommon,
        // ... etc
      },
    },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
    },
  })

export default i18n
```

Sample locale file `src/i18n/locales/en/common.json`:

```json
{
  "nav": {
    "market": "Market",
    "watchlist": "Watchlist",
    "alerts": "Alerts",
    "settings": "Settings",
    "sign_out": "Sign out",
    "sign_in": "Sign in"
  },
  "actions": {
    "save": "Save",
    "cancel": "Cancel",
    "confirm": "Confirm",
    "close": "Close",
    "back": "Back",
    "next": "Next",
    "skip": "Skip"
  },
  "states": {
    "loading": "Loading…",
    "error": "Something went wrong.",
    "retry": "Try again"
  }
}
```

Chinese equivalent:

```json
{
  "nav": {
    "market": "市场",
    "watchlist": "关注列表",
    "alerts": "提醒",
    "settings": "设置",
    "sign_out": "退出登录",
    "sign_in": "登录"
  }
}
```

Replace hardcoded strings in components:

```tsx
// Before:
<Link to="/market">Market</Link>

// After:
import { useTranslation } from 'react-i18next'
// In component:
const { t } = useTranslation('common')
<Link to="/market">{t('nav.market')}</Link>
```

Add Alembic migration `0011_add_user_preferred_locale.py`:

```python
def upgrade():
    op.add_column('users', sa.Column('preferred_locale', sa.String(10), nullable=True))

def downgrade():
    op.drop_column('users', 'preferred_locale')
```

Add a `LanguageToggle` component in the NavBar (`EN / 中文` switcher).

#### Step 7: Fonts and Storybook

Update `frontend/index.html` `<head>`:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&family=Noto+Sans+SC:wght@400;500;700&display=swap" rel="stylesheet">
```

Storybook:

```bash
npx storybook@latest init
```

Create initial stories in `src/components/SignalBadge.stories.tsx`, etc. Six stories minimum (per acceptance criteria).

#### Step 8: Bundle size budget

```bash
npm install -D vite-bundle-visualizer
```

In `package.json`:

```json
"scripts": {
  "build:analyze": "vite-bundle-visualizer"
}
```

Create `BUNDLE_BUDGET.md` at repo root.

#### Verification recipe

```bash
# 1. TypeScript build
cd frontend && npx tsc --noEmit
# Expected: 0 errors

# 2. Production build
npm run build
# Expected: dist/ created without errors
# Note size of main bundle:
du -h dist/assets/*.js | sort -h | tail -3

# 3. Hardcoded strings audit
grep -rn ">[A-Z][a-z][a-z]" src/components/ src/pages/ | grep -v ".stories." | grep -v "//" | grep -v "/\*"
# Expected: only icon imports or component names, no UI strings

# 4. Emoji audit
grep -rn "📊\|⚡\|🔔\|📈\|⭐\|☆\|🎴" src/components/ src/pages/
# Expected: no matches

# 5. Storybook
npm run storybook
# Open http://localhost:6006
# Expected: all stories render

# 6. Language toggle
# Click EN/中文 in nav, confirm UI changes language, reload, confirm persists
```

#### Acceptance criteria checklist

- [ ] Visual diff vs. pre-migration ≤5% on every page (compare screenshots)
- [ ] Zero hardcoded English strings in `.tsx` component files (grep-verified)
- [ ] Zero emoji characters in component files (grep-verified)
- [ ] Bundle size under 200KB gzipped (main)
- [ ] TypeScript strict mode passes
- [ ] All Storybook stories render
- [ ] Language toggle works, persists across reload, persists across devices for auth users
- [ ] At least one shadcn primitive (DropdownMenu in NavBar) is wired

#### Codex review prompt

```
Review PR #15. This is the foundation. Specific concerns:
1. Is every existing component actually migrated, or are some still using raw CSS classes from theme.css?
2. Has any UX regressed? Particularly: keyboard navigation, focus states, dark theme contrast.
3. Is i18n applied consistently? Specifically: are number formats, date formats, and pluralization handled, or only string interpolation?
4. Does the TanStack Query migration introduce race conditions (e.g., a component that previously re-fetched on every mount now stays stale)?
5. Are shadcn components actually used, or just installed?
6. Bundle size: what are the three heaviest dependencies, and is any avoidable?
7. Does the locale toggle persist to the database for authenticated users, or only localStorage?
8. Are the Chinese strings reviewed by Ivan? (Required before merge.)
```

#### Sign-off

- [ ] Ivan has reviewed and approved all Chinese strings
- [ ] All acceptance criteria pass
- [ ] Codex review section appended
- [ ] Merged to main, Railway + Cloudflare deploys complete
- [ ] Production smoke test passed (all four routes load, language toggle works)

---

### Phases 4–12: PR #16 through PR #24

For Phases 4–12, the structure is identical:

1. **Prompt to give Claude Code** (referencing both spec and playbook sections)
2. **Step-by-step execution** (with code snippets and commands)
3. **Verification recipe** (curl, SQL, browser checks)
4. **Acceptance criteria checklist**
5. **Common failures and recovery**
6. **Codex review prompt** (per the strategy spec)
7. **Sign-off checklist**

For brevity in this playbook, refer to the strategy spec for the detailed scope of each phase. The patterns established in Phases 1–3 above apply identically to:

- **Phase 4 (PR #16): Real sparklines + TradingView charts** — see strategy spec PR #16; key gotcha is batched SQL not N+1, and cache column update in bulk-refresh job
- **Phase 5 (PR #17): Confidence + explainability + COOLING** — see strategy spec PR #17; key gotcha is COOLING precision must be backtested before shipping
- **Phase 6 (PR #18): Joy moments + sound + tilt + holo** — see strategy spec PR #18; key gotcha is the "idle is still" principle must be verified by observation
- **Phase 7 (PR #19): Landing page rebuild** — see strategy spec PR #19; founder voice copy is Ivan's, not Claude Code's
- **Phase 8 (PR #20): Onboarding + first-flip celebration** — see strategy spec PR #20; key gotcha is milestone persistence must be durable
- **Phase 9 (PR #21): Status page + methodology + changelog** — see strategy spec PR #21; methodology page content is Ivan's
- **Phase 10 (PR #22): SSE + virtualization + Cmd+K** — see strategy spec PR #22; key gotcha is SSE connection cleanup
- **Phase 11 (PR #23): Weekly digest email** — see strategy spec PR #23; key gotcha is unsubscribe link must be signed
- **Phase 12 (PR #24): Cloudflare Pages migration** — see strategy spec PR #24; this is the final cut-over

When you reach each phase, the prompt template to give Claude Code is:

```
Read .claude/specs/2026-05-13-phase-1-enterprise-rebuild.md section "PR #XX".
Read .claude/playbooks/2026-05-13-build-playbook.md "Phase Y" if a detailed playbook section exists.
For phases beyond #15, follow the pattern established in earlier phases — execute scope as defined in strategy spec, verify with the acceptance criteria listed there, and run Codex review prompt from the spec.
Create branch feat/pr-XX-name from main.
Surface to Ivan if any scope item is ambiguous.
```

---

## Part 5: Reference Appendices

### Appendix A: Bilingual content review process

For every PR that adds user-facing strings:

1. Claude Code writes English strings in `frontend/src/i18n/locales/en/`
2. Claude Code translates to Chinese in `frontend/src/i18n/locales/zh-CN/` using its bilingual capability
3. Ivan reviews the Chinese before merge — flagged in PR description as "Awaiting Ivan's Chinese review"
4. Ivan suggests edits inline or approves
5. Edits incorporated, then merge

Native quality standard: a Chinese speaker reading the UI should not be able to tell it was translated. If they can, it's a bug.

### Appendix B: Common SQL queries for verification

```sql
-- Scheduler health
SELECT job_name, status, started_at, finished_at
FROM scheduler_run_log
WHERE started_at > NOW() - INTERVAL '24 hours'
ORDER BY started_at DESC;

-- Active signals breakdown
SELECT label, COUNT(*)
FROM asset_signals
GROUP BY label
ORDER BY COUNT(*) DESC;

-- Insufficient data root cause (per Ivan's memory)
SELECT
  CASE
    WHEN baseline_price IS NULL THEN 'no_baseline'
    WHEN current_price IS NULL THEN 'no_current'
    WHEN baseline_price IS NOT NULL AND current_price IS NULL THEN 'has_baseline_no_current'
    ELSE 'other'
  END AS reason,
  COUNT(*)
FROM asset_signals
WHERE label = 'INSUFFICIENT_DATA'
GROUP BY reason;

-- Audit log activity (post PR #14)
SELECT event_type, COUNT(*) AS event_count, MAX(created_at) AS last_seen
FROM audit_log
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY event_type
ORDER BY event_count DESC;

-- Recent price data freshness per source
SELECT source, MAX(captured_at) AS most_recent, COUNT(*) AS rows_24h
FROM price_history
WHERE captured_at > NOW() - INTERVAL '24 hours'
GROUP BY source;

-- Backup verification (post PR #14)
SELECT started_at, finished_at, status, records_written
FROM scheduler_run_log
WHERE job_name = 'postgres_backup'
ORDER BY started_at DESC
LIMIT 7;
```

### Appendix C: Production smoke test

Run this after every deploy:

```bash
# 1. API health
curl -s https://api.flashcardplanet.com/api/v1/web/stats | jq .
# Expected: valid JSON

# 2. Web SPA loads
curl -sI https://flashcardplanet.com/ | head -5
# Expected: 200 OK

# 3. Spot-check a random card detail
ASSET_ID=$(curl -s https://api.flashcardplanet.com/api/v1/web/cards | jq -r '.cards[0].asset_id')
curl -s https://api.flashcardplanet.com/api/v1/web/cards/$ASSET_ID | jq .signal
# Expected: a signal label

# 4. Frontend visual check (manual)
# - Open https://flashcardplanet.com
# - Check landing page renders
# - Click "Market", confirm cards load
# - Click a card, confirm detail page loads with chart
# - Click language toggle, confirm switch

# 5. Sentry check
# - Open Sentry dashboard
# - No new errors in the last 15 minutes (or only known ones)
```

### Appendix D: Recovery procedures

**If a deploy breaks production:**

1. Find the previous good deploy ID in Railway/Cloudflare
2. Roll back via the platform UI (Railway: redeploy previous; Cloudflare Pages: rollback to deployment)
3. Open an incident in Discord
4. Verify rollback restored functionality
5. Then investigate the bug; do not try to forward-fix on a broken production

**If the database is corrupted:**

1. STOP scheduler immediately: in Railway, scale scheduler service to 0
2. Coordinate with Ivan (this is a P0)
3. Follow `docs/runbooks/restore-from-backup.md`
4. After restore, re-enable scheduler at 0 replicas, then 1
5. Watch for 30 minutes before declaring restored

**If you're unsure:** stop and ask Ivan via claude.ai. Do not improvise.

### Appendix E: Bundle size budget enforcement

In `frontend/package.json`:

```json
"scripts": {
  "build:check-size": "node scripts/check-bundle-size.js"
}
```

`frontend/scripts/check-bundle-size.js`:

```js
import { readdirSync, statSync } from 'fs'
import { join } from 'path'

const MAX_MAIN_GZIP = 200 * 1024  // 200KB
const distDir = './dist/assets'

const files = readdirSync(distDir)
const mainBundle = files.find(f => f.startsWith('index-') && f.endsWith('.js'))
const size = statSync(join(distDir, mainBundle)).size

console.log(`Main bundle: ${(size / 1024).toFixed(1)}KB raw`)
if (size > MAX_MAIN_GZIP * 1.5) {
  console.error(`Bundle too large! Limit: ${MAX_MAIN_GZIP / 1024}KB gzipped (~${MAX_MAIN_GZIP * 1.5 / 1024}KB raw)`)
  process.exit(1)
}
```

Add to CI: `npm run build && npm run build:check-size`.

---

## Part 6: Daily Operations (Post-Phase-1)

Once Phase 1 ships, here's the day-to-day operational rhythm:

### Daily checks (5 minutes)

- [ ] Status page green
- [ ] No new Sentry errors above noise threshold
- [ ] Scheduler heartbeat ran in last hour
- [ ] Backup ran overnight

### Weekly checks (30 minutes)

- [ ] Review PostHog: signups, conversions, retention
- [ ] Review audit log for unusual activity
- [ ] Backup retention: anything older than 30 days archived?
- [ ] Bundle size hasn't regressed
- [ ] Lighthouse score still ≥90 on landing

### Monthly checks (2 hours)

- [ ] Restore drill: pick a random backup, restore to scratch DB, verify
- [ ] Sentry sample rate review: are we capturing enough? too much?
- [ ] Dependency updates: `npm audit`, `pip list --outdated`
- [ ] Cloudflare R2 spend check
- [ ] Railway resource utilization — is it time to scale up?

### Quarterly (half day)

- [ ] Full disaster recovery drill: restore to a parallel staging environment, run smoke test
- [ ] Re-read this playbook and update for anything that changed
- [ ] Postmortem any production incidents from the quarter

---

## Part 7: Closing Notes

This playbook is meant to live alongside the strategy spec. Update both when reality diverges from the plan. The spec covers WHY; this playbook covers HOW.

If you are a fresh Claude session executing this:
- You are not alone. Ivan is available. claude.ai is available for strategy questions. Codex is your reviewer.
- Slow is fast. The cost of a careful PR is much less than the cost of a fast-but-broken one.
- Evidence over confidence. Every claim about production must be backed by SQL, curl, or screenshot.
- When in doubt, ask. The cost of a 5-minute clarification is less than the cost of a wrong implementation.

You are building the founder-led, signal-first, multi-TCG intelligence platform that makes serious card investing legible — and feels like the cards themselves. Hold that sentence close. Every decision flows from it.

Now go build.

---

*End of playbook. ~13,000 words. Live document — update as Phase 1 progresses.*
*Next review: after Phase 3 ships, update Phases 4–12 with full detail based on what was learned in Phases 1–3.*
