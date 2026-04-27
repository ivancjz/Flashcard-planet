# Graded Shadow Admission — Phase 1 Verification Runbook

This document is the operator's runbook for Phase 1 observation.
All SQL gates use the production admin endpoints or direct Postgres.

---

## T+0 Gates (immediately after deploy, ~3 minutes after merge)

### Gate 1 — Migration applied

```sql
SELECT version_num FROM alembic_version;
```
**Expected**: `0027`

### Gate 2 — Audit table exists with correct shape

```sql
\d graded_observation_audit
```
**Expected**: all columns listed in the spec are present.
Alternatively:
```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'graded_observation_audit'
ORDER BY ordinal_position;
```

### Gate 3 — Flag active in production

Check Railway env vars panel: `GRADED_SHADOW_AUDIT_ENABLED=true`

Or hit the diag endpoint and verify it returns 200 (endpoint only exists
when code is deployed):
```bash
curl -s -H "X-Admin-Key: $ADMIN_API_KEY" \
  https://<railway-domain>/admin/diag/graded-shadow-admission | python -m json.tool
```
**Expected**: JSON response with `total_by_decision`, `removal_condition`, etc.

### Gate 4 — No graded rows leaked to price_history

```sql
SELECT COUNT(*) AS graded_price_rows_last_24h
FROM price_history
WHERE source = 'ebay_sold'
  AND market_segment IS NOT NULL
  AND market_segment <> 'raw'
  AND captured_at >= NOW() - INTERVAL '24 hours';
```
**Expected**: 0 — graded MUST NOT enter price_history during Phase 0.

### Gate 5 — No malformed audit rows

```sql
SELECT COUNT(*) AS bad_rows
FROM graded_observation_audit
WHERE candidate_asset_id IS NULL
   OR raw_title IS NULL
   OR raw_title = ''
   OR shadow_decision NOT IN ('audit_only','parser_raw','parser_unknown','parser_excluded');
```
**Expected**: 0 at all times.

---

## T+24h Gates (after first eBay ingest cycle)

eBay ingestion runs daily (24h interval, startup +660s). Run these after
the first cycle completes post-deploy.

### Gate 6 — Audit rows are accumulating

```sql
SELECT shadow_decision, COUNT(*)
FROM graded_observation_audit
WHERE created_at >= NOW() - INTERVAL '24 hours'
GROUP BY 1
ORDER BY 1;
```
**Expected**: non-zero rows. Ideally distributed across ≥2 decision buckets.

### Gate 7 — Graded price rows still zero (regression check)

Re-run Gate 4. **Expected**: still 0.

---

## Day-3 Sanity Check

```sql
SELECT COUNT(*) AS total_audit_rows
FROM graded_observation_audit;

SELECT shadow_decision, COUNT(*) AS n
FROM graded_observation_audit
GROUP BY 1 ORDER BY n DESC;
```

**Decision rule**:
- Total ≥ 30 AND at least one bucket > 0 → Phase 1 proceeding normally, continue
- Total < 30 → extend Phase 1 to 2–3 weeks, document reason

Note: `parser_raw` rows (preflight detected graded, parser returned raw) are
the most important false-negative bucket. If `parser_raw` count is 0, it may
mean the parser captures all graded titles correctly, or that the bucket is
too rare to measure. Document the observation either way.

---

## Day-7 Sample Readiness Check

```sql
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE shadow_decision = 'audit_only') AS audit_only,
  COUNT(*) FILTER (WHERE shadow_decision = 'parser_raw') AS parser_raw,
  COUNT(*) FILTER (WHERE shadow_decision = 'parser_unknown') AS parser_unknown,
  COUNT(*) FILTER (WHERE shadow_decision = 'parser_excluded') AS parser_excluded,
  COUNT(*) FILTER (WHERE human_label IS NULL) AS unreviewed
FROM graded_observation_audit;
```

**Phase 1 readiness thresholds**:
- total ≥ 100 AND audit_only ≥ 50 → begin manual review
- total < 100 OR audit_only < 50 → extend Phase 1, document reason

---

## Manual Review Workflow (Phase 1)

Fetch unreviewed samples via the diag endpoint:
```bash
curl -s -H "X-Admin-Key: $ADMIN_API_KEY" \
  https://<railway-domain>/admin/diag/graded-shadow-admission | python -m json.tool
```

Label rows via the label endpoint:
```bash
curl -s -X POST \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"id": "<audit-row-uuid>", "human_label": "graded_correct", "reviewer_notes": "optional"}' \
  https://<railway-domain>/admin/diag/graded-shadow-admission/label
```

**Valid `human_label` values**:
- `graded_correct` — parser segment and candidate asset look correct
- `wrong_segment` — asset looks right, graded segment is wrong
- `wrong_asset` — listing is for a different card/asset
- `not_single_card` — lot/sealed/multi-card despite earlier gates
- `non_english` — should not be admitted for the English path
- `unclear` — reviewer cannot confidently decide

**Target sample**: 50 `audit_only`, 30 `parser_raw`/`parser_unknown`, 20 `parser_excluded`.
If a bucket is short, take all available and reallocate to `audit_only`.

**Phase 2 readiness threshold**: ≥95% precision on `audit_only` rows
(`graded_correct` / (`graded_correct` + all other labels)).

---

## Notes for Phase 1 Reviewers

**Why some graded listings may not appear in the audit table:**

The shadow write point is after the name compatibility gate
(`_title_contains_card_name`). For graded listings, this gate uses the
raw title as the "normalised title" (the graded preflight returns early
before variant extraction runs). Titles where variant words interfere with
the name match may be rejected by the name gate and never reach the audit
table. This is expected conservative behavior — the audit table represents
graded listings that are positively compatible with a known asset, not
every graded listing that eBay returns.

**What `parser_raw` means in Phase 0:**

`parser_raw` means `preflight_observation()` identified the listing as
graded (triggering `GRADED_CARD`), but `parse_listing_title()` returned
`market_segment='raw'`. This is the main false-negative bucket: graded
listings the parser failed to classify. Phase 2 review of these rows
informs whether the parser needs improvement before Phase 3.

---

## Cleanup

Remove after Phase 2 review is complete and Phase 3 decision is made:

1. `GET /admin/diag/graded-shadow-admission` endpoint  
2. `POST /admin/diag/graded-shadow-admission/label` endpoint  
3. `graded_shadow_audit_enabled` setting (once decision on permanent
   graded ingest path is made)  
4. Migration `0027` downgrade drops the table when cleanup is scheduled
