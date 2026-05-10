# Disaster Recovery Runbook

**Backup system:** GitHub Actions daily pg_dump → private releases at `ivancjz/flashcard-planet-backups`
**RPO:** < 24 hours (daily backup at 04:00 UTC)
**RTO target:** < 2 hours (download + restore + Railway redeploy)

---

## Backup verification (daily)

Check that the latest backup exists:

```bash
gh release list --repo ivancjz/flashcard-planet-backups --limit 5
```

Expected: a release tagged `backup-<N>` created today or yesterday. If the most recent is > 25 hours old, investigate the workflow.

---

## Restore procedure

### Prerequisites

```bash
# Install tools if not present
brew install postgresql  # macOS
# or: apt-get install postgresql-client-18

gh auth login            # GitHub CLI authenticated
docker ps                # Docker running
```

### Step 1 — Download the latest backup

```bash
mkdir -p ~/flashcard-restore && cd ~/flashcard-restore

# List available backups
gh release list --repo ivancjz/flashcard-planet-backups --limit 10

# Download the latest (or a specific date)
gh release download --repo ivancjz/flashcard-planet-backups \
  --pattern '*.sql.gz' \
  --dir . \
  --clobber

ls -lh *.sql.gz
```

### Step 2 — Spin up a test PostgreSQL instance

```bash
docker run -d \
  --name pg-restore-test \
  -e POSTGRES_PASSWORD=testpass \
  -e POSTGRES_DB=railway \
  -p 5433:5432 \
  postgres:18

# Wait for it to be ready
sleep 3
docker exec pg-restore-test pg_isready -U postgres
```

### Step 3 — Restore the dump

```bash
gunzip -c backup-*.sql.gz | \
  psql -h localhost -p 5433 -U postgres -d railway
```

### Step 4 — Verify the restore

```bash
psql -h localhost -p 5433 -U postgres -d railway <<'SQL'
SELECT COUNT(*) AS assets       FROM assets;
SELECT COUNT(*) AS price_rows   FROM price_history;
SELECT COUNT(*) AS users        FROM users;
SELECT COUNT(*) AS signals      FROM asset_signals;
SELECT MAX(captured_at) AS latest_price FROM price_history;
SQL
```

**Compare against production** (run the same queries on the live DB via Railway CLI):

```bash
railway run psql "$DATABASE_URL" <<'SQL'
SELECT COUNT(*) AS assets FROM assets;
SQL
```

Expected: restore counts within 24h of production counts (one day's delta is acceptable).

### Step 5 — Point Railway to restored data (if production DB is lost)

1. Create a new Railway PostgreSQL service
2. Get the new `DATABASE_URL`
3. Restore into it:
   ```bash
   gunzip -c backup-*.sql.gz | psql "$NEW_DATABASE_URL"
   ```
4. Update the `DATABASE_URL` env var in Railway backend service
5. Redeploy the backend service

### Step 6 — Clean up test instance

```bash
docker stop pg-restore-test && docker rm pg-restore-test
```

---

## Drill log

| Date | Run by | Backup used | RTO observed | Asset count match | Notes |
|---|---|---|---|---|---|
| 2026-05-02 | ivancjz | backup-4 (297 MB) | Yes | 47s restore + ~3min download = **~4 min total** | assets=4371, price_rows=1,342,611, signals=4033 — exact match with production. postgres:18 container. |

**DoD for TASK-102a:** Fill in the first row of this table. RTO must be documented before TASK-102a is considered complete.

---

## Failure scenarios

| Scenario | Detection | Response |
|---|---|---|
| Backup workflow failed | Discord alert + GitHub Actions email | Check workflow logs; re-run manually via `workflow_dispatch` |
| Backup file corrupted | `gunzip` error during restore test | Download previous day's backup |
| Backup repo deleted | Manual check | Re-create repo; next scheduled run restores it |
| Railway DB lost | Railway dashboard alert | Follow restore procedure above |
| GitHub Actions unavailable | Backup not created; no alert | Use quarterly local backup (TASK-102b) |

---

## Re-evaluation trigger

When Pro users ≥ 10, evaluate whether to upgrade to Railway Pro plan ($15/mo) for automated managed snapshots. The free-tier approach here has sufficient RPO/RTO for zero-to-ten paying users.
