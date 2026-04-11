# Human Review UI Design

**Date:** 2026-04-11
**Status:** Approved
**Scope:** Operator-facing queue review page + resolution API endpoints for low-confidence ingestion matches

---

## 1. Overview

Add a `/backstage/review` page and supporting REST endpoints that allow an operator to resolve listings queued for human review. The `HumanReviewQueue` table is already populated by the ingestion pipeline when AI confidence falls below threshold; this feature adds the missing resolution layer — Accept, Override, or Dismiss — with full downstream writes.

---

## 2. Access & Auth

- All endpoints and the page itself are protected by the existing `require_admin_key` dependency (`X-Admin-Key` header, from `settings.admin_api_key`).
- The HTML page loads with an inline key prompt. The operator enters the admin key once; it is stored in `sessionStorage`. Every JS `fetch()` call sends it via the `X-Admin-Key` header.
- If authentication fails, `sessionStorage` is cleared and the prompt is re-shown with an error message.
- `resolved_by` is set to `"operator"` for MVP — no per-user attribution, as admin auth uses a single shared key.

---

## 3. Model Addition

### `HumanReviewQueue.resolution_type`

Add one column to the existing `human_review_queue` table:

| Column | Type | Notes |
|---|---|---|
| `resolution_type` | `VARCHAR(16)` nullable | `"accepted"`, `"overridden"`, `"dismissed"` — null until resolved |

**Migration:** `alembic/versions/0008_add_review_resolution_type.py`

The existing `resolved_at` and `resolved_by` columns are not changed.

---

## 4. API Endpoints

All endpoints live in a new file: `backend/app/backstage/review_routes.py`.
All are mounted under `/api/v1/admin/review` and protected by `require_admin_key`.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/admin/review/` | List unresolved items, paginated, newest first |
| `POST` | `/api/v1/admin/review/{id}/accept` | Accept the AI's best guess |
| `POST` | `/api/v1/admin/review/{id}/override` | Override with a specified `asset_id` in request body |
| `POST` | `/api/v1/admin/review/{id}/dismiss` | Dismiss as unresolvable |
| `GET` | `/api/v1/admin/review/assets/search?q=...` | Asset name search for override picker |

### List endpoint

`GET /api/v1/admin/review/`

Query params: `limit` (default 50, max 200), `offset` (default 0).

Returns items where `resolved_at IS NULL`, ordered by `created_at DESC`. Response shape:

```json
{
  "items": [...],
  "total_pending": 42,
  "limit": 50,
  "offset": 0
}
```

Each item includes: `id`, `raw_title`, `best_guess_asset_id`, `best_guess_asset_name` (joined from assets), `best_guess_confidence`, `reason`, `created_at`.

### Asset search endpoint

`GET /api/v1/admin/review/assets/search?q=charizard`

Returns up to 20 assets matching the query by `name ILIKE '%q%'`. Fields: `id`, `name`, `set_name`, `variant`. Returns empty list (200) if no matches.

---

## 5. Resolution Write Contract

All three resolution endpoints run inside a **single DB transaction**. Any failure rolls back the entire operation — nothing is partially written.

Every successful resolution sets on the `human_review_queue` row:
- `resolved_at = now() UTC`
- `resolved_by = "operator"`
- `resolution_type = <"accepted" | "overridden" | "dismissed">`

### Accept

1. Load `HumanReviewQueue` row → 404 if not found
2. Check `resolved_at IS NULL` → 409 if already resolved (conditional unresolved-state check)
3. Verify `best_guess_asset_id` is not null → 422 "No best guess to accept"
4. Load linked `RawListing` by `raw_listing_id` → 404 if not found
5. Verify `raw_listing.status == PENDING` → 409 "Listing already processed by another workflow"
6. Validate `raw_listing.price_usd` and `sold_at` are non-null → 422 "Listing missing required price data"
7. Write `PriceHistory` row (`asset_id = best_guess_asset_id`, `price = price_usd`, `captured_at = sold_at`, `source = "ebay"`)
8. Update `RawListing`: `status = PROCESSED`, `mapped_asset_id = best_guess_asset_id`, `match_method = "human_review_accept"`, `processed_at = now()`
9. Write/update `AssetMappingCache` entry: normalized title → `best_guess_asset_id`, `method = "human_review"`
10. Stamp review row: `resolved_at`, `resolved_by`, `resolution_type = "accepted"`
11. Commit → 200

### Override

Request body: `{"asset_id": "<uuid>"}`

1. Load `HumanReviewQueue` row → 404 if not found
2. Check `resolved_at IS NULL` → 409 if already resolved
3. Load `Asset` by request `asset_id` → 422 "Asset not found" if not found
4. Load linked `RawListing` → 404 if not found
5. Verify `raw_listing.status == PENDING` → 409 "Listing already processed by another workflow"
6. Validate `price_usd` and `sold_at` → 422 "Listing missing required price data"
7. Write `PriceHistory` row (`asset_id = request asset_id`)
8. Update `RawListing`: `status = PROCESSED`, `mapped_asset_id = request asset_id`, `match_method = "human_review_override"`, `processed_at = now()`
9. Write/update `AssetMappingCache` entry: normalized title → request `asset_id`, `method = "human_review"`
10. Stamp review row: `resolved_at`, `resolved_by`, `resolution_type = "overridden"`
11. Commit → 200

### Dismiss

1. Load `HumanReviewQueue` row → 404 if not found
2. Check `resolved_at IS NULL` → 409 if already resolved
3. Load linked `RawListing` → 404 if not found
4. Verify `raw_listing.status == PENDING` → 409 "Listing already processed by another workflow" if not (prevents dirty state where queue row is unresolved but the listing was already touched by another process)
5. Update `RawListing`: `status = FAILED`, `error_reason = "review_dismissed"`, `processed_at = now()`
5. No price event written. No mapping cache entry written.
6. Stamp review row: `resolved_at`, `resolved_by`, `resolution_type = "dismissed"`
7. Commit → 200

---

## 6. Error Handling

| Condition | Response |
|---|---|
| Review row not found | 404 |
| Row already resolved | 409 Conflict — detected via conditional unresolved-state check, not row locking |
| `best_guess_asset_id` is null on Accept | 422 "No best guess to accept" |
| `asset_id` in Override body not found in assets | 422 "Asset not found" |
| Linked `raw_listing` cannot be loaded | 404 — referenced source record is missing, resolution cannot proceed |
| `raw_listing.status` is not `PENDING` | 409 "Listing already processed by another workflow" — prevents dirty state |
| `raw_listing.price_usd` or `sold_at` null | 422 "Listing missing required price data" |
| DB write fails mid-transaction | 500 — full rollback, nothing partially written |
| Admin key missing | 401 |
| Admin key wrong | 403 |
| Admin key not configured on server | 403 "Admin key not configured" |
| Asset search returns zero results | 200 with empty list |

**Browser-side error states:**
- Key prompt auth failure → clear `sessionStorage`, re-show prompt with inline error
- Queue loads empty → "No pending reviews" empty state
- Resolution action fails → error shown inline in the modal; modal stays open for retry

---

## 7. Page Layout (`/backstage/review`)

Served from `backend/app/site.py` as a new `GET /backstage/review` route. Server renders a minimal HTML shell; all dynamic content is loaded by JS.

### Key prompt (first load)

If `sessionStorage` has no `adminKey`, render a centered key entry form. On submit, attempt `GET /api/v1/admin/review/` with the entered key. On 200, store in `sessionStorage` and load the queue. On 401/403, show error and clear the field.

### Queue view

Compact table/list of unresolved items. Columns: raw title, AI best guess name (or "—"), confidence score, reason, queued time. Clicking any row opens the resolution modal. Shows total pending count in the header. "No pending reviews" empty state when queue is empty.

### Resolution modal

Opened when operator clicks a queue row. Contains:
- **Raw title** — full text, monospace
- **AI best guess** — asset name + confidence score (or "No guess" if null)
- **Reason** — human-readable label (e.g. "AI confidence below threshold")
- **Queued** — relative time
- **Three action buttons:** Accept · Override · Dismiss
- **Override search** — shown only when Override is clicked: text input + live search results list (calls `GET /assets/search?q=...` debounced 300ms, minimum 3 characters before firing to avoid empty/high-frequency requests). Operator selects an asset from results to confirm the override.
- **Accept button disabled** — when `best_guess_asset_id` is null, the Accept button is disabled client-side. Backend still returns 422 if called directly.
- **Loading state** — buttons disabled while request in flight
- **Error display** — inline error below buttons on failure; modal stays open
- **Close button** — dismisses modal without resolving

On successful resolution: modal closes, resolved row removed from queue list, pending count decremented.

---

## 8. Files Changed

| File | Action | Responsibility |
|---|---|---|
| `backend/app/models/human_review.py` | Modify | Add `resolution_type` column |
| `alembic/versions/0008_add_review_resolution_type.py` | Create | Migration |
| `backend/app/backstage/review_routes.py` | Create | All 5 API endpoints |
| `backend/app/api/router.py` | Modify | Register `review_router` from `review_routes.py` under `settings.api_prefix` |
| `backend/app/site.py` | Modify | Add `GET /backstage/review` route |
| `backend/app/static/site.css` | Modify | Review page, modal, key prompt styles |
| `tests/test_human_review_api.py` | Create | Unit tests for all 5 endpoints |

---

## 9. Out of Scope (this iteration)

- Per-reviewer attribution (resolved_by will always be "operator" until per-user admin accounts exist)
- Resolved item history view (resolved rows not shown in the queue)
- Bulk resolution (resolve multiple rows at once)
- Filtering/sorting the queue beyond newest-first
- Admin session cookie / remember-me (key re-entered on each browser session)
