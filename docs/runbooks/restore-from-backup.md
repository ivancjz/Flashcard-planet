# Restore from Backup — Runbook

**Last drill:** 2026-05-13 — backup-14, ~115s RTO, row counts match within expected drift
**Backup location:** GitHub Releases → `ivancjz/flashcard-planet-backups` → asset `backup.sql.gz`
**Format:** Plain SQL dump (gzip compressed)
**Schedule:** GitHub Actions daily at 04:00 UTC

---

## When to use this

- Accidental `DROP TABLE` or data corruption
- Disaster recovery (Railway region failure)
- Routine restore drill (run quarterly)

---

## Prerequisites

```bash
# Tools needed:
gh --version   # GitHub CLI, authenticated as ivancjz
psql --version # Postgres client (brew install postgresql or apt-get postgresql-client)
docker --version  # Docker (for scratch DB) — or use Railway scratch service if unavailable
```

The `gh` CLI must be authenticated with read access to `ivancjz/flashcard-planet-backups`.

---

## Step 1 — List recent backups

```bash
gh release list --repo ivancjz/flashcard-planet-backups --limit 30
```

Output shows: tag name, release name, date. Pick the backup you want to restore (usually the latest).
Note the tag (e.g., `backup-14`).

---

## Step 2 — Download chosen backup

```bash
BACKUP_TAG="backup-14"   # replace with actual tag
mkdir -p /tmp/restore-drill

gh release download "$BACKUP_TAG" \
  --repo ivancjz/flashcard-planet-backups \
  --pattern "backup.sql.gz" \
  --dir /tmp/restore-drill/
```

Verify the download:
```bash
ls -lh /tmp/restore-drill/backup.sql.gz
# Expected: ~450 MB for a recent backup
```

---

## Step 3 — Decompress

```bash
cd /tmp/restore-drill
time gunzip backup.sql.gz
ls -lh backup.sql
# Expected: ~3-4 GB uncompressed
```

---

## Step 4 — Stand up scratch Postgres 18

**NEVER restore directly into production.** Always verify in a scratch DB first.

Option A — Local Docker (preferred):
```bash
docker run -d \
  --name fp-restore-drill \
  -e POSTGRES_PASSWORD=test \
  -e POSTGRES_DB=flashcard_planet_restore \
  -p 5433:5432 \
  postgres:18

sleep 5  # wait for postgres to be ready
SCRATCH_URL="postgresql://postgres:test@localhost:5433/flashcard_planet_restore"
```

Option B — Railway scratch service (if Docker unavailable):
- Create a new Postgres service in Railway
- Grab the public connection URL
- Set `SCRATCH_URL` to that connection string

Verify the scratch DB is up:
```bash
psql "$SCRATCH_URL" -c "SELECT 1;"
```

---

## Step 5 — Restore

```bash
time psql "$SCRATCH_URL" -f /tmp/restore-drill/backup.sql
```

Expected: many `SET`, `CREATE TABLE`, `INSERT`, `CREATE INDEX` lines. Some `ERROR: role "..." does not exist` warnings are safe to ignore (they come from the `--no-owner` flag in the dump).

---

## Step 6 — Verify row counts

Run these against the scratch DB and compare to production (run the same queries against `DATABASE_PUBLIC_URL`):

```bash
psql "$SCRATCH_URL" -c "SELECT COUNT(*) AS assets FROM assets;"
psql "$SCRATCH_URL" -c "SELECT COUNT(*) AS price_rows FROM price_history;"
psql "$SCRATCH_URL" -c "SELECT MAX(captured_at) AS latest_price FROM price_history;"
psql "$SCRATCH_URL" -c "SELECT COUNT(*) AS signals FROM asset_signals;"
psql "$SCRATCH_URL" -c "SELECT COUNT(*) AS sealed_products FROM sealed_products;"
psql "$SCRATCH_URL" -c "SELECT COUNT(*) AS users FROM users;"
```

Counts should match the backup's point-in-time snapshot (expect minor drift for any tables written to after the backup ran at 04:00 UTC).

---

## Step 7 — Tear down scratch DB

```bash
docker stop fp-restore-drill && docker rm fp-restore-drill
rm -f /tmp/restore-drill/backup.sql
```

---

## Step 8 — Production restore (ONLY if disaster confirmed)

This is irreversible. Coordinate with Ivan before proceeding.

```bash
# 1. Pause all writes — Railway dashboard → backend service → redeploy with:
#    SCHEDULER_POLL_SECONDS=999999  (or stop the service)

# 2. Verify the backup is good: Steps 1-6 must pass first.

# 3. Restore over production
#    DATABASE_PUBLIC_URL is the public TCP proxy URL (junction.proxy.rlwy.net:19115)
psql "$DATABASE_PUBLIC_URL" -f /tmp/restore-drill/backup.sql

# 4. Verify row counts against your pre-disaster snapshot

# 5. Re-enable writes: redeploy with normal env vars
```

---

## What NOT to do

- Never restore directly into production without completing Steps 1–6 first
- Never delete a backup release manually — the 30-day prune policy handles retention
- Never commit credentials to the repo

---

## Drill log

Run quarterly. Record results here.

| Date | Author | Tag | Download + gunzip (s) | psql restore (s) | Total RTO (s) | Row counts match? | Notes |
|---|---|---|---|---|---|---|---|
| 2026-05-13 | ivancjz / Claude Code | backup-14 | 53.9 + 11.3 = 65.2 | 49.3 | ~115s (~1.9 min) | Yes (within expected drift) | assets 4371 (prod: 4391, +20 drift since 04:00 UTC); price_history 2,343,894 (prod: 2,452,969, +109k drift = ~1 day ingest); asset_signals 4,033 (exact match); users 1 (exact match). sealed_products table absent from backup — migration added after 2026-05-12. Drill done on Windows with Docker Desktop; gunzip ran inside container via docker cp. |

---

## References

- Live backup workflow: `.github/workflows/daily-backup.yml`
- APScheduler watchdog: `backup-freshness-check` job in `backend/app/backstage/scheduler.py`
- Watchdog script: `scripts/check_backup_freshness.py`
- Quarterly local download: `backend/scripts/backup_to_local.sh`
