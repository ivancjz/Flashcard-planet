# Graded Shadow Admission Design

## Summary

PR title:

> Graded Shadow Admission: let graded eBay listings be seen by the parser and audit layer, but do not give them authority to affect market prices or signals.

This PR opens an observation path for graded eBay listings without letting those listings write to `price_history` or enter signal computation. It is the first step toward graded market segments, not the cleanup/final enablement step.

The engineering rule is deliberately narrow: graded listings may become visible to humans and diagnostics, but they do not gain market authority until a later PR is designed from the review results.

## Audit Findings

Current eBay ingest is asset-first, not title-first:

1. `ingest_ebay_sold_cards()` loops over known `Asset` rows.
2. `_build_search_query(asset)` searches eBay for that asset.
3. Listing titles are filtered against that current asset with `_title_contains_card_name()` and `_card_number_matches()`.
4. `parse_listing_title()` classifies the market segment only after a listing survives earlier gates.

`observation_match_logs` is not usable as-is for graded shadow review:

- It has useful columns: `raw_title`, `matched_asset_id`, `market_segment`, `grade_company`, `grade_score`.
- But graded titles are stopped before this table is written.
- The earliest graded stop is usually `preflight_observation(title)` returning `ObservationSkipReason.GRADED_CARD`.
- `_is_grade_compatible()` is a second grade gate later in the path, but many graded listings never reach it.

Existing segment parsing is already present:

- `parse_listing_title()` returns `market_segment`, `grade_company`, `grade_score`, `confidence`, `parser_notes`, and `excluded`.
- `build_market_segment()` already canonicalizes segments such as `psa_10`, `bgs_9_5`, `cgc_10`, and `sgc_9`.

Therefore Phase 0 is not a new parser project. It is a shadow admission path that lets existing parser decisions be audited before they can affect prices.

## Approach

Use a dedicated temporary table: `graded_observation_audit`.

This table is a short-term review instrument, not a permanent product table. It is shaped around 100-sample human review, progress tracking, and aggregate precision checks. It should be easy to drop after the graded rollout decision is made.

Rejected alternative: reuse `observation_match_logs`.

That table records ingest match decisions for observations that reach the normal matched path. Since graded listings are currently filtered before an observation log is created, reuse would require changing the semantics of a broad production audit table for a temporary manual-review workflow.

Rejected alternative: CSV/file samples.

Files are too weak for a 7-day live observation window: they are harder to query, harder to deduplicate, and harder to aggregate into precision metrics.

## Scope

In scope:

- Add `graded_observation_audit` model and migration.
- Add an audit-only write path for graded eBay listings.
- Add an audit-only config flag, `graded_shadow_audit_enabled`.
- Add read-only admin diagnostics/sample endpoint or helper for Phase 1 review.
- Add tests proving graded listings are audited but not written to `price_history`.
- Add SQL gates for deployment and Phase 1 monitoring.

Out of scope:

- Do not write graded eBay listings to `price_history`.
- Do not alter signal computation to include graded segments.
- Do not add a dormant "enable graded prices" flag.
- Do not remove `_is_grade_compatible()` as a production safety gate.
- Do not implement Phase 3 cleanup/final enablement code.

## Shadow Write Point

The implementation must not simply remove a filter. It must add a new branch at the graded preflight gate.

Current simplified flow:

```text
listing
  -> preflight_observation(title)
       if GRADED_CARD: continue
  -> _title_contains_card_name(title, asset)
       if false: continue
  -> _card_number_matches(asset, title)
       if false: continue
  -> _is_grade_compatible(title, asset)
       if false: unmatched_grade_mismatch++; continue
  -> parse_listing_title(title)
  -> write price_history + observation_match_logs
```

Phase 0 flow:

```text
listing
  -> preflight_observation(title)
       if GRADED_CARD:
         if graded_shadow_audit_enabled:
           -> run existing single-card, name, and card-number compatibility gates
           -> if compatible, parse_listing_title(title)
           -> write graded_observation_audit
           -> continue
         else:
           -> continue
  -> existing raw production flow unchanged
```

`_is_grade_compatible()` remains in place. Phase 0 does not remove it or route shadow-audited graded listings through it. After this PR it may be logically redundant for many graded cases, but it stays as defense in depth until a later Phase 3 design decides what to do with it.

The audit sample must represent graded listings that would have reached ingest if the graded preflight gate did not stop them, after normal asset compatibility gates. Placing the shadow write after `_is_grade_compatible()` is incorrect because it would only audit the subset that survived a filter we are trying to evaluate.

## Audit Table

Proposed columns:

- `id uuid primary key`
- `provider text not null`, initially `ebay_sold`
- `external_item_id text not null`
- `candidate_asset_id uuid not null references assets(id)`
- `raw_title text not null`
- `price numeric(12,2) null`
- `currency text not null default 'USD'`
- `captured_at timestamptz null`
- `parser_market_segment text null`
- `parser_grade_company text null`
- `parser_grade_score text null`
- `parser_confidence text null`, values from `parse_listing_title()` (`high`, `medium`, `low`)
- `parser_notes jsonb not null default '[]'`
- `preflight_grade_info jsonb null`
- `shadow_decision text not null`
- `human_label text null`
- `human_reviewed_at timestamptz null`
- `reviewer_notes text null`
- `created_at timestamptz not null default now()`

Indexes:

- unique `(provider, external_item_id, candidate_asset_id)` to avoid repeated audit rows.
- `(shadow_decision, human_reviewed_at, created_at)` for review queues.
- `(parser_market_segment, created_at)` for stratified sampling.
- `(candidate_asset_id, created_at)` for asset-level debugging.

## Design Decisions

### 1. Asset Matching

The audit table records `candidate_asset_id`, not a parser-derived asset id.

Reason: the current eBay path already runs per asset. A listing is considered a candidate for the current asset only after existing hard gates:

- It is a single-card listing.
- It passes the preflight path far enough to identify a graded-card skip.
- The title contains the current asset name.
- The title's explicit card number, when present, is compatible with the current asset.

For graded shadow rows, the write point should be after name and card-number compatibility checks, even if the current production path would have continued earlier because of `GRADED_CARD`.

This means Phase 0 does not need a new title-to-asset matcher. If review shows too many candidate-asset mistakes, that becomes Phase 2 evidence for a stronger matcher before any price writes are allowed.

### 2. Parser Evidence

Store `parser_confidence` and `parser_notes`.

`parse_listing_title()` already exposes a string confidence and notes such as graded matches, multiple distinct grades, and exclusion reasons. Phase 0 should not expand parser internals just to expose regex names. If review disagreements show that notes are insufficient, a later parser-quality PR can add richer evidence.

### 3. Shadow Decisions

Allowed `shadow_decision` values:

- `audit_only`: candidate asset gates passed, parser produced a canonical graded segment, row withheld from `price_history`.
- `parser_unknown`: candidate asset gates passed, parser returned `unknown`, row withheld.
- `parser_excluded`: candidate asset gates passed, parser marked the title excluded, row withheld.
- `parser_raw`: candidate asset gates passed, preflight said graded, but parser defaulted to `raw`; this is an important false-negative bucket for review.

Rows that fail single-card, name, or card-number gates should not be written to `graded_observation_audit`; those remain normal ingest rejects.

`parser_raw` has a narrow meaning in Phase 0: preflight identified the listing as graded, but `parse_listing_title()` returned `raw`. It does not measure every possible graded-to-raw false negative.

### 4. Sample Window

Default Phase 1 observation window: 7 days.

Minimum useful review target:

- At least 100 total audit rows.
- At least 50 rows where `shadow_decision = 'audit_only'`.

Day-3 sanity check:

- If total audit rows are under 30 by day 3, extend Phase 1 to 2-3 weeks or adjust eBay query strategy in a separate PR.
- Do not lower the precision bar just because traffic is thin.

Sampling target for the 100-row review:

- 50 canonical graded rows (`audit_only`)
- 30 parser disagreement/risk rows (`parser_raw`, `parser_unknown`)
- 20 parser excluded rows (`parser_excluded`)

If a bucket has fewer rows than the target, take all available rows and reallocate the remaining sample to `audit_only`.

## Admin Diagnostics

Add a temporary read-only endpoint, for example:

`GET /admin/diag/graded-shadow-admission`

It should return:

- Total audit rows by `shadow_decision`.
- Rows by `parser_market_segment`.
- Reviewed/unreviewed counts.
- Human labels by parser segment, when labels exist.
- Precision summary once reviewed labels are present.
- A sample payload for unreviewed rows, optionally stratified by decision.

Removal condition:

- Remove after Phase 2 manual review is complete and the Phase 3 graded enablement decision is made.

This endpoint is part of Phase 0 because without it Phase 1 data is harder to use.

## Human Review Workflow

Minimum viable review workflow:

1. Use the diagnostic endpoint to fetch unreviewed sample rows.
2. Label rows through a small authenticated admin POST endpoint:

`POST /admin/diag/graded-shadow-admission/label`

Request body:

```json
{
  "id": "audit-row-uuid",
  "human_label": "graded_correct",
  "reviewer_notes": "optional note"
}
```

Allowed `human_label` values:

- `graded_correct`: parser segment and candidate asset look correct.
- `wrong_segment`: asset looks right, graded segment is wrong.
- `wrong_asset`: listing is for a different card/asset.
- `not_single_card`: listing is lot/sealed/multi-card despite earlier gates.
- `non_english`: listing should not be admitted for the current English raw/graded path.
- `unclear`: reviewer cannot confidently decide from the title.

Direct SQL updates are acceptable as a fallback, but they are not the primary workflow. A full UI is out of Phase 0 scope.

The diagnostic endpoint should report label counts and precision using the above labels. `graded_correct` counts as correct; all other labels count as incorrect or excluded from precision only if explicitly documented in the endpoint response.

## Feature Flag

Use an environment-backed setting:

- Env var: `GRADED_SHADOW_AUDIT_ENABLED`
- Settings attribute: `graded_shadow_audit_enabled`
- Code default: `False`
- Production Phase 0 deployment value: `true`

Default false keeps new/forked environments from silently collecting shadow audit data. Production turns it on through Railway env and can turn it off with an env change plus restart. Tests should set the flag explicitly for both enabled and disabled behavior.

This flag only controls audit-row collection. It must not control writing graded rows to `price_history`, and it must not become a dormant Phase 3 activation switch.

## Verification Gates

Pre-deploy/local tests:

- A PSA/BGS/CGC title for an ungraded asset creates one `graded_observation_audit` row when `graded_shadow_audit_enabled` is true.
- The same graded title creates zero `price_history` rows.
- Raw listings continue to write `price_history` and `observation_match_logs` as before.
- Duplicate `(provider, external_item_id, candidate_asset_id)` audit events do not create duplicate rows.
- Parser buckets are assigned correctly for canonical graded, raw fallback, unknown, and excluded titles.
- When `graded_shadow_audit_enabled` is false, current behavior is unchanged.

Post-deploy SQL gates:

```sql
-- Audit rows are accumulating
SELECT shadow_decision, COUNT(*)
FROM graded_observation_audit
WHERE created_at >= NOW() - INTERVAL '24 hours'
GROUP BY 1
ORDER BY 1;

-- Shadow rows have candidate assets and titles
SELECT COUNT(*) AS bad_rows
FROM graded_observation_audit
WHERE candidate_asset_id IS NULL OR raw_title IS NULL OR raw_title = '';

-- Graded audit does not write graded price rows
SELECT COUNT(*) AS graded_price_rows_last_24h
FROM price_history
WHERE source = 'ebay_sold'
  AND market_segment IS NOT NULL
  AND market_segment <> 'raw'
  AND captured_at >= NOW() - INTERVAL '24 hours';

-- Review sample queue
SELECT id, raw_title, parser_market_segment, parser_confidence, parser_notes
FROM graded_observation_audit
WHERE human_label IS NULL
ORDER BY random()
LIMIT 100;
```

Expected immediately after deploy:

- Audit rows may be zero until the next eBay ingestion cycle.
- `bad_rows` must always be zero.
- `graded_price_rows_last_24h` must be zero during Phase 0.

## Phase Roadmap

Phase 0: Shadow admission PR.

- Add audit table, audit-only write path, diagnostics, tests.
- Deploy with `graded_shadow_audit_enabled=true`.

Phase 1: Observation window.

- Run for 7 days by default.
- Perform day-3 volume sanity check.
- Review 100 samples when enough rows exist.

Phase 2: Manual review decision.

- Compute precision by segment and decision bucket.
- Required threshold for Phase 3 design: at least 95% precision on canonical graded parser output.

Phase 3: Separate design and implementation PR.

- Designed from Phase 2 evidence.
- May remove or replace `_is_grade_compatible()`.
- May allow selected graded segments into `price_history` and signal computation.
- Must not be pre-implemented in Phase 0.

## Open Risks

- Current asset matching is candidate-based from per-asset eBay searches. It may over-admit listings with common names if title/card-number gates are insufficient.
- `preflight_observation()` checks graded before language. Phase 0 will audit some titles that may also be non-English; review labels should capture this rather than hiding it.
- Traffic may be too thin for 100 samples in 7 days.
- Parser notes may be too coarse for diagnosing disagreements; if so, richer parser evidence is Phase 2 follow-up, not Phase 0 scope creep.
- Preflight + parser dual miss is invisible to this PR. If both `preflight_observation()` and `parse_listing_title()` classify a graded listing as raw, the row can enter `price_history` directly and never appear in `graded_observation_audit`. Phase 1 precision applies only to listings that at least one current gate flagged as graded. Estimating the dual-miss rate requires a separate audit of raw eBay rows for hidden graded titles, outside Phase 0 and outside the Phase 1 review.
