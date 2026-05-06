# Quarterly Local Backup Runbook

**Purpose:** Air-gapped third layer of defence. Downloads the latest automated backup to the operator's local machine. Provides recovery capability if both GitHub Actions and GitHub itself are unavailable.

**This is belt-and-suspenders.** Primary defence is `daily-backup.yml` (TASK-102a). This is a quarterly health check, not the main recovery path.

---

## Schedule

Run on the first Monday of each quarter:

| Quarter | Date 2026 | Date 2027 |
|---|---|---|
| Q2 | 2026-04-06 | 2027-04-05 |
| Q3 | 2026-07-06 | 2027-07-05 |
| Q4 | 2026-10-05 | 2027-10-04 |
| Q1 | 2027-01-04 | 2028-01-03 |

**Add to Google Calendar** with a recurring reminder. If a quarter goes by without running this, it is a signal that `daily-backup.yml` may also be silently broken.

---

## Prerequisites

```bash
gh auth status          # GitHub CLI must be authenticated
```

---

## How to run

```bash
bash backend/scripts/backup_to_local.sh
```

Default output directory: `~/Flashcard-planet-backups/<date>/backup.sql.gz`

To use a different directory:
```bash
BACKUP_DIR=/Volumes/ExternalDrive/backups bash backend/scripts/backup_to_local.sh
```

---

## What the script does

1. Creates `~/Flashcard-planet-backups/<today>/`
2. Downloads the latest `*.sql.gz` from `ivancjz/flashcard-planet-backups` releases
3. Verifies the file is at least 50 KB (catches corrupt/empty downloads)
4. Removes local directories older than 365 days (keeps last ~4 quarters)

---

## If the script fails

| Error | Meaning | Action |
|---|---|---|
| `gh: not found` | GitHub CLI not installed | `brew install gh && gh auth login` |
| `no releases found` | Backup repo is empty | Check `daily-backup.yml` workflow run history |
| File < 50 KB | Download or backup corrupt | Check latest release manually at github.com/ivancjz/flashcard-planet-backups |
| `gh auth` error | Token expired | `gh auth login` |

If the script fails, that almost certainly means `daily-backup.yml` has also been silently failing. Investigate the Actions tab before anything else.

---

## Drill log

| Date | Operator | File size | Restore verified? | RTO | Notes |
|---|---|---|---|---|---|
| *(first run after 102a ships)* | | | No (download only) | n/a | |

Full restore verification: follow `docs/runbooks/disaster-recovery.md`.

---

## This laptop is not a reliable backup medium

- SSDs die without warning. HDDs too.
- The laptop can be lost, stolen, or doused in tea.
- This layer is useful only if GitHub AND Railway both fail simultaneously.
- Do not rely on this as the primary recovery path.
