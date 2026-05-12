# Restore from R2 Backup — Runbook

**Last drill:** see Drill log below
**Backup location:** Cloudflare R2 → `flashcard-planet-backups` bucket → `daily/YYYY-MM-DD.dump`
**Format:** pg_dump custom format (--format=custom --compress=9)
**Schedule:** Daily at startup+30min offset (interval/24h via APScheduler)

---

## When to use this

- Accidental `DROP TABLE` / `DROP DATABASE`
- Corrupted data (suspected or confirmed)
- Disaster recovery (Railway region failure, data centre incident)
- Routine drill (run quarterly per policy)

---

## Prerequisites

```bash
# Set these in your shell before running commands:
export CF_ACCOUNT="<your Cloudflare account ID>"
export R2_ACCESS_KEY="<R2 API key>"
export R2_SECRET_KEY="<R2 API secret>"
export BUCKET="flashcard-planet-backups"

# AWS CLI must be installed and configured to use the R2 endpoint.
# No region-based AWS creds needed — Cloudflare uses its own auth.
```

---

## Procedure

### Step 1 — Identify the backup to restore

List the last 20 daily backups:

```bash
aws --endpoint-url="https://${CF_ACCOUNT}.r2.cloudflarestorage.com" \
    s3 ls "s3://${BUCKET}/daily/" \
    --no-sign-request \
    2>&1 | tail -20
```

> Note: `--no-sign-request` does NOT work for private R2 buckets.
> Use these env vars for auth instead:

```bash
AWS_ACCESS_KEY_ID=$R2_ACCESS_KEY \
AWS_SECRET_ACCESS_KEY=$R2_SECRET_KEY \
aws --endpoint-url="https://${CF_ACCOUNT}.r2.cloudflarestorage.com" \
    s3 ls "s3://${BUCKET}/daily/" | tail -20
```

Pick the desired date (usually today's or yesterday's). Record the key, e.g. `daily/2026-05-13.dump`.

---

### Step 2 — Download the chosen backup

```bash
BACKUP_DATE="2026-05-13"  # replace with actual date
RESTORE_FILE="/tmp/restore-${BACKUP_DATE}.dump"

AWS_ACCESS_KEY_ID=$R2_ACCESS_KEY \
AWS_SECRET_ACCESS_KEY=$R2_SECRET_KEY \
aws --endpoint-url="https://${CF_ACCOUNT}.r2.cloudflarestorage.com" \
    s3 cp "s3://${BUCKET}/daily/${BACKUP_DATE}.dump" \
    "$RESTORE_FILE"

ls -lh "$RESTORE_FILE"
```

---

### Step 3 — Stand up a scratch database

**NEVER restore directly into production.** Always verify in a scratch DB first.

Option A — Local Docker (preferred for drills):
```bash
docker run -d \
    --name fp-restore-test \
    -e POSTGRES_PASSWORD=test \
    -e POSTGRES_DB=flashcard_planet_restore_test \
    -p 5433:5432 \
    postgres:18

# Wait ~5s for Postgres to start
sleep 5
SCRATCH_URL="postgresql://postgres:test@localhost:5433/flashcard_planet_restore_test"
```

Option B — Railway scratch service (use if Docker unavailable):
- Create a temporary Postgres service in Railway
- Set `SCRATCH_URL` to the connection string

---

### Step 4 — Restore to scratch database

```bash
pg_restore \
    --dbname="$SCRATCH_URL" \
    --no-owner \
    --no-privileges \
    --jobs=4 \
    "$RESTORE_FILE"
```

Expected: no errors, possibly some warnings about extensions (safe to ignore).

---

### Step 5 — Verify the restore

```bash
psql "$SCRATCH_URL" -c "SELECT COUNT(*) AS assets FROM assets;"
psql "$SCRATCH_URL" -c "SELECT COUNT(*) AS signals FROM asset_signals;"
psql "$SCRATCH_URL" -c "SELECT MAX(captured_at) AS latest_price FROM price_history;"
psql "$SCRATCH_URL" -c "SELECT COUNT(*) AS price_rows FROM price_history;"
```

Compare against production (ask Ivan or run against `DATABASE_URL_DIRECT`):
```bash
psql "$DATABASE_URL_DIRECT" -c "SELECT COUNT(*) FROM assets;"
psql "$DATABASE_URL_DIRECT" -c "SELECT COUNT(*) FROM asset_signals;"
```

Counts must match within expected point-in-time delta (a few rows of drift is fine — the dump is a snapshot before the restore was initiated).

---

### Step 6 — Tear down the scratch database

```bash
docker stop fp-restore-test && docker rm fp-restore-test
rm -f "$RESTORE_FILE"
```

---

### Step 7 — If production restore is needed (ONLY if disaster confirmed)

This step is irreversible. Coordinate with Ivan before proceeding.

```bash
# 1. Pause all writes — stop the scheduler to prevent further writes
#    (Railway → backend service → disable or redeploy with INGEST_SCHEDULE_ENABLED=false)

# 2. Verify the backup is good (Steps 1–5 above must pass first)

# 3. Restore over production — the --clean flag drops and recreates objects
pg_restore \
    --dbname="$DATABASE_URL_DIRECT" \
    --clean \
    --no-owner \
    --no-privileges \
    "$RESTORE_FILE"

# 4. Verify row counts against expected

# 5. Re-enable writes (redeploy with normal env vars)
```

---

## What NOT to do

- Never restore directly into production without a scratch verification first (Step 5 row counts must pass)
- Never delete a backup — if R2 lifecycle policies archive to cold storage, that's intentional
- Never commit `CLOUDFLARE_R2_*` credentials to the repo; they live in Railway env vars only

---

## Drill log

Run a drill quarterly and record results here.

| Date | Author | Backup key | Download time | pg_restore time | Row count match | Notes |
|---|---|---|---|---|---|---|
| _(first drill — fill in after Phase 4 of PR #14a)_ | | | | | | |

---

## Backup script reference

Script: `scripts/backup_postgres.py`
Scheduler job: `postgres-backup` (interval/24h, registered in `backend/app/backstage/scheduler.py`)
Scheduler run log: query `SELECT * FROM scheduler_run_log WHERE job_name='postgres-backup' ORDER BY started_at DESC LIMIT 10;`
