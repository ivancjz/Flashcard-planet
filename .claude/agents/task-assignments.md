# Agent Task Assignments — 2026-05-17

## Active worktrees

| Worktree | Role | Branch | Assigned task |
|----------|------|--------|---------------|
| `.worktrees/agent-frontend` | Frontend | `feat/agent-frontend` | TASK-305 + TASK-T05 |
| `.worktrees/agent-backend` | Backend | `feat/agent-backend` | TASK-301 backend test suite |
| `.worktrees/agent-devops` | DevOps | `feat/agent-devops` | Node.js 24 + TASK-T08 cleanup |

## WIP branches (do not delete)

| Worktree | Branch | Status |
|----------|--------|--------|
| `.worktrees/feat-signal-timeline` | `feat/signal-timeline` | 3 commits, needs Ivan review |
| `.worktrees/fix-watch-gate` | `fix/watch-prediction-gate` | 2 commits, needs Ivan review |

---

## Frontend agent tasks

### TASK-305 — /pricing page Chinese localisation (S)

File scope: `frontend/src/pages/PricingPage.tsx`, `frontend/src/i18n/`

- Check if i18n framework exists (`frontend/src/i18n/`)
- If yes: add zh translations for all strings in PricingPage.tsx
- If no: implement minimal i18n — detect `navigator.language`, swap strings
- Currency display: show ¥ when locale is zh
- Test: manually switch locale in browser

### TASK-T05 — Migrate tierBadge() to CSS classes (S)

File scope: `frontend/src/styles/theme.css`, `frontend/src/components/NavBar.tsx`, `frontend/src/utils/tier.ts`

- Add `.badge-pro` (gold) and `.badge-plus` (violet) to `theme.css`
- Update `tierBadge()` to return `{ className, label }` instead of inline styles
- Update `NavBar.tsx` to use `className={badge.className}`
- Precondition: pattern-promotion Task 1 (`.badge-gold`) must be in theme.css already

---

## Backend agent tasks

### TASK-301 backend test suite

File scope: `tests/test_webhooks.py`, `tests/test_account.py`, `tests/test_trial.py`

Without LemonSqueezy credentials, test the contracts:
- `POST /webhooks/lemonsqueezy` with valid/invalid HMAC signatures
- `GET /api/v1/account/checkout-url` with missing credentials → correct error code
- Trial expiry email flow unit tests (mock Resend)
- Idempotency: same `event_id` webhook processed twice → returns `duplicate`

---

## DevOps agent tasks

### Node.js 24 upgrade for GitHub Actions

File scope: `.github/workflows/`

- Update all workflows using `actions/checkout@v4` and `actions/setup-python@v5`
  to add `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true` env var OR upgrade to v5 of checkout
- Per Codex review warning: "Node.js 20 actions are deprecated. Forced to Node.js 24 by June 2, 2026"
- Check: `gh api repos/ivancjz/Flashcard-planet/actions/workflows` for all workflow files

### TASK-T08 — Operational quick reference in DEV_NOTES.md

File scope: `docs/DEV_NOTES.md`

- Already done (commit 2176d0f) — verify it's still accurate
- If not: update the railway curl health-check commands to reflect new endpoints

---

## How to launch an agent session

Open a new Claude Code terminal in each worktree directory:

```bash
# Terminal 1 — Frontend
cd C:\Flashcard-planet\.worktrees\agent-frontend
claude  # opens Claude Code in this worktree

# Terminal 2 — Backend
cd C:\Flashcard-planet\.worktrees\agent-backend
claude

# Terminal 3 — DevOps
cd C:\Flashcard-planet\.worktrees\agent-devops
claude
```

Each agent reads its role automatically:
```bash
cat .claude/agents/$(cat .claude/agents/.current-role).md
```
