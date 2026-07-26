# Portfolio Raw, PSA, and Private Photos Design

**Date:** 2026-07-26

**Status:** Approved

**Phase:** Flashcard Planet v2, Phase 6 Portfolio Intelligence

**Depends on:** Portfolio Foundation

---

## 1. Context

Portfolio Foundation records raw-card purchase lots and values each position
against the latest accepted raw market observation. Collectors also need to
record PSA-graded cards as distinct holdings and retain private photographs of
the exact copy they own.

The existing market model already stores canonical segments such as `raw`,
`psa_9`, and `psa_10` on `price_history`. The portfolio extension must use that
source of truth. It must not create ten duplicate catalog assets for every card
or allow a raw price to stand in for a PSA price.

Official catalog art and user-owned photos serve different purposes:

- Official art identifies the catalog card and may be shown throughout the
  product.
- User photos document the physical copy in a specific purchase lot and remain
  private to the owning account.

## 2. Goals

1. Support Raw and PSA portfolio lots.
2. Support integer PSA grades 1 through 10.
3. Treat Raw and every PSA grade as independent portfolio positions.
4. Value every position only from its exact accepted market segment.
5. Keep unmatched PSA positions explicitly unpriced.
6. Show official catalog art in portfolio search and position views.
7. Let a user optionally attach one front and one back photo to each lot.
8. Keep all user-owned photos private and durable across Railway deployments.
9. Preserve every existing portfolio lot as Raw during migration.
10. Keep older clients compatible while the backend and frontend roll out.

## 3. Non-Goals

- BGS, CGC, SGC, or other grading companies
- Half grades, qualifier grades, altered labels, or cross-grades
- Sealed products
- PSA certification-number tracking or PSA API verification
- Automatic grade recognition from a photo
- AI analysis of user-owned photos
- Groq or any other AI-provider work
- Public galleries, photo sharing, or social profiles
- More than two user photos per lot
- Video, PDF, SVG, GIF, HEIC, or RAW-camera uploads
- Manual portfolio valuation
- Substituting another grade, grading company, or Raw price
- Changing graded observations from audit-only to price-authoritative
- Direct browser uploads to object storage in the initial release

## 4. Product Decisions

### 4.1 Card Selection

The add-lot flow searches and selects one canonical catalog card. It does not
show eleven search results for the Raw and PSA 1-10 variants.

After card selection:

1. The user chooses `Raw` or `PSA`.
2. Selecting PSA reveals a grade selector with integer values 1 through 10.
3. Quantity, unit cost, purchase date, and optional photos apply to that lot.

This keeps search concise while preserving exact holding identity.

### 4.2 Holding Identity

Condition and PSA grade belong to the portfolio lot and position identity, not
to a cloned catalog `Asset`.

A position is identified by:

```text
(asset_id, condition, psa_grade)
```

Examples:

```text
(moonbreon_asset_id, raw, null)
(moonbreon_asset_id, psa, 9)
(moonbreon_asset_id, psa, 10)
```

These are three independent positions. Lots with the same tuple group into one
position; lots with different tuples never group together.

### 4.3 Position Limits

Free-tier position limits count distinct holding identities, not only distinct
catalog assets.

Adding PSA 10 for a card already held as Raw consumes a new position. Adding a
second PSA 10 lot for the same card does not.

Changing a lot from one identity to another must run the same locked
position-limit check as creating a new lot. A change that would create a new
position at the Free limit is rejected.

### 4.4 Exact Valuation

The required market segment is derived through the existing
`build_market_segment()` source of truth:

| Holding | Required segment |
|---|---|
| Raw | `raw` |
| PSA 1 | `psa_1` |
| PSA 9 | `psa_9` |
| PSA 10 | `psa_10` |

For PSA positions, an eligible observation must also have:

```text
grade_company = 'PSA'
grade_score = the exact integer grade
```

This structured-field check is defense in depth against a mislabeled segment.

The service must not:

- Use Raw when a PSA price is unavailable.
- Use PSA 10 for PSA 9 or any other neighboring grade.
- Use a BGS, CGC, or SGC observation.
- Interpolate between grades.
- Use the lot's purchase cost as current market value.
- Bypass active-source or graded-data admission rules.

Until a PSA segment has an accepted, active price source, the position is
`unpriced`. Adding PSA holdings does not grant graded observations price
authority.

### 4.5 Official and Private Images

The position's official image comes from the catalog asset metadata, currently
`metadata_json["images"]["small"]`. It is used in search, selected-card
confirmation, and position display. A missing official image uses the existing
card-art fallback.

Private photos belong to an individual lot:

- Maximum one `front` photo
- Maximum one `back` photo
- Both are optional
- Either can be replaced or deleted independently

Private photos never replace the official catalog image in general card search
or public market surfaces.

## 5. Data Model

### 5.1 Portfolio Lot Extension

Add these columns to `portfolio_lots`:

| Column | Type | Null | Default | Rule |
|---|---|---:|---|---|
| `condition` | String(8) | No | `raw` | `raw` or `psa` |
| `psa_grade` | SmallInteger | Yes | null | Integer 1-10 for PSA only |

Database constraints:

```text
condition IN ('raw', 'psa')

(condition = 'raw' AND psa_grade IS NULL)
OR
(condition = 'psa' AND psa_grade BETWEEN 1 AND 10)
```

Replace or supplement the grouping index with:

```text
(user_id, asset_id, condition, psa_grade)
```

All existing rows are backfilled to `condition = 'raw'` and
`psa_grade = null` before the non-null condition and cross-field constraints
are installed.

### 5.2 Portfolio Lot Photos

Create `portfolio_lot_photos`:

| Column | Type | Null | Rule |
|---|---|---:|---|
| `id` | UUID | No | Primary key |
| `lot_id` | UUID | No | FK to `portfolio_lots.id`, delete cascade |
| `side` | String(8) | No | `front` or `back` |
| `full_storage_key` | Text | No | Opaque, server-generated full-image key |
| `thumbnail_storage_key` | Text | No | Opaque, server-generated thumbnail key |
| `content_type` | String(64) | No | Stored normalized type |
| `full_byte_size` | Integer | No | Positive |
| `thumbnail_byte_size` | Integer | No | Positive |
| `width_px` | Integer | No | Positive |
| `height_px` | Integer | No | Positive |
| `sha256` | String(64) | No | Normalized-object digest |
| `created_at` | Timestamptz | No | Server timestamp |
| `updated_at` | Timestamptz | No | Server timestamp |

Constraints and indexes:

- Unique `(lot_id, side)`
- Check `side IN ('front', 'back')`
- Check positive byte sizes and dimensions
- Index `lot_id`

The table must not store original client filenames, public URLs, signed URLs,
or object-store credentials.

### 5.3 Deletion Outbox

Object storage and PostgreSQL cannot participate in one transaction. Create a
small durable deletion outbox for replaced or deleted objects.

`storage_object_deletion_jobs` contains:

- `id`
- `storage_key`
- `reason`
- `attempt_count`
- `next_attempt_at`
- `last_error`
- `created_at`
- `completed_at`

When a photo is replaced or a lot is deleted:

1. Commit the new database state and enqueue the old object key in the same
   database transaction.
2. Attempt deletion after commit.
3. Mark the job complete on success.
4. Retry with bounded backoff through the existing scheduler on failure.

This prevents orphaned private objects from being forgotten after transient
storage failures.

## 6. Object Storage and Image Processing

### 6.1 Storage Adapter

Use a private S3-compatible storage adapter. Cloudflare R2 is the recommended
deployment provider, but business logic depends only on the adapter.

Required server-only configuration:

```text
PORTFOLIO_PHOTOS_ENABLED
OBJECT_STORAGE_ENDPOINT_URL
OBJECT_STORAGE_REGION
OBJECT_STORAGE_BUCKET
OBJECT_STORAGE_ACCESS_KEY_ID
OBJECT_STORAGE_SECRET_ACCESS_KEY
OBJECT_STORAGE_SIGNED_URL_TTL_SECONDS
```

Defaults:

- `PORTFOLIO_PHOTOS_ENABLED=false`
- Signed URL TTL: 60 seconds

The application must start normally when photo storage is not configured.
Raw/PSA portfolio tracking remains available and photo controls are hidden or
disabled with a neutral unavailable state.

No photo may be persisted to Railway's local filesystem except as a
request-scoped temporary file that is removed before the request completes.

### 6.2 Upload Path

The initial release sends a multipart upload through the authenticated backend.
This gives the server one enforcement point for content inspection, EXIF
removal, resizing, and ownership.

Direct presigned browser uploads are deferred. They add a finalize protocol and
allow unprocessed private source files to reach storage before server
validation.

### 6.3 Validation and Normalization

Accepted source formats:

- JPEG
- PNG
- WebP

Rules:

- Maximum source payload: 8 MB per photo
- Detect media type from bytes; do not trust the filename or request header
- Reject animated images
- Apply decompression-bomb protection
- Correct orientation
- Remove EXIF and other embedded metadata
- Resize so the longest side is at most 2000 pixels
- Encode the full image as a normalized WebP
- Generate a separate thumbnail WebP
- Calculate dimensions, sizes, and SHA-256 after normalization

Object keys are random and non-enumerable. They must not contain the original
filename, card name, user email, or other personal data.

### 6.4 Private Reads

Portfolio responses return photo metadata and authenticated application content
paths, never permanent object-store URLs.

When the browser requests full or thumbnail content:

1. Authenticate the current user.
2. Load the photo through a join to the user-owned lot.
3. Return `404` when the lot/photo does not belong to the user.
4. Generate a short-lived signed GET URL and redirect, or stream the object
   through the backend.
5. Send private/no-store cache policy from the application endpoint.

The bucket has no public-read policy.

## 7. API Design

All endpoints use `get_current_user`. No request accepts `user_id`.

### 7.1 Lot Create

```http
POST /api/v1/portfolio/lots
```

New request:

```json
{
  "asset_id": "uuid",
  "condition": "psa",
  "psa_grade": 10,
  "quantity": 1,
  "unit_cost_usd": "650.00",
  "purchased_on": "2026-07-01"
}
```

For backward compatibility, omitted `condition` means `raw` and omitted
`psa_grade` means null.

### 7.2 Lot Patch

```http
PATCH /api/v1/portfolio/lots/{lot_id}
```

The patch accepts `condition` and `psa_grade` in addition to existing editable
fields. Validation runs against the merged persisted state, not only fields
present in the request.

Examples:

- Changing PSA 9 to Raw requires `condition = raw` and `psa_grade = null`.
- Changing Raw to PSA requires `condition = psa` and an integer grade.
- A resulting invalid combination returns `422`.
- A resulting new Free-tier position beyond the limit returns the existing
  typed `403` upgrade response.

### 7.3 Portfolio Read

Each position adds:

```json
{
  "position_key": "asset-uuid:psa:10",
  "condition": "psa",
  "psa_grade": 10,
  "market_segment": "psa_10",
  "image_url": "https://catalog.example/card.png",
  "latest_price_usd": "700.00"
}
```

Each lot adds:

```json
{
  "condition": "psa",
  "psa_grade": 10,
  "photos": [
    {
      "id": "uuid",
      "side": "front",
      "thumbnail_path": "/api/v1/portfolio/lots/lot-uuid/photos/front/content?variant=thumbnail",
      "content_path": "/api/v1/portfolio/lots/lot-uuid/photos/front/content?variant=full"
    }
  ]
}
```

`position_key` is a deterministic read-model key and is not a new database
entity.

For staged frontend deployment, retain `latest_raw_price_usd` temporarily:

- Raw position: contains the exact Raw price.
- PSA position: null.

New clients use `latest_price_usd`. The compatibility field is removed only
after deployed clients no longer depend on it.

### 7.4 Photo Upload or Replace

```http
PUT /api/v1/portfolio/lots/{lot_id}/photos/{side}
Content-Type: multipart/form-data
```

`side` is `front` or `back`. Uploading an existing side atomically replaces its
database metadata and enqueues deletion of the previous stored objects.

Response: HTTP 200 for replacement or HTTP 201 for first creation.

### 7.5 Photo Content

```http
GET /api/v1/portfolio/lots/{lot_id}/photos/{side}/content?variant=thumbnail
GET /api/v1/portfolio/lots/{lot_id}/photos/{side}/content?variant=full
```

Both require authentication and lot ownership.

### 7.6 Photo Delete

```http
DELETE /api/v1/portfolio/lots/{lot_id}/photos/{side}
```

Returns HTTP 204 after database removal and deletion-job enqueue.

### 7.7 Errors

- `401`: not authenticated
- `403`: portfolio position limit reached
- `404`: asset, lot, or photo not owned by the current user
- `413`: photo exceeds 8 MB
- `415`: unsupported or invalid image content
- `422`: invalid condition, grade, side, or image dimensions
- `503`: photo feature disabled, misconfigured, or temporarily unavailable

Photo upload failure never rolls back a lot that was already created by a
separate successful request.

## 8. Valuation and Summary Changes

Load prices in bounded queries keyed by the complete position identity. Do not
issue one query per position.

For every position:

```text
market_segment = raw or psa_{grade}
quantity = sum(matching lot.quantity)
cost_basis = sum(matching lot.quantity * lot.unit_cost_usd)
market_value = quantity * latest exact eligible price, when present
```

Portfolio summary adds:

```text
unpriced_cost_basis = total_cost_basis - priced_cost_basis
```

The UI shows:

- Priced position count
- Unpriced position count
- Unpriced cost basis

Total market value continues to include priced positions only. Unpriced
positions never contribute zero-dollar market value.

Game allocation remains based only on priced market value and may combine Raw
and PSA positions within the same game.

## 9. Frontend Experience

### 9.1 Card Search and Selection

Search results show:

- Official catalog image
- Card name
- Set
- Card number
- Existing holding status for the selected condition when known

After selection, the dialog keeps the official image visible beside the card
identity.

### 9.2 Condition Controls

Use a compact segmented control for `Raw` and `PSA`.

When PSA is active, show a labeled grade menu with integer values 1 through 10.
The grade control is absent for Raw.

Condition and grade are editable. The dialog explains a position-limit failure
without discarding entered values.

### 9.3 Photo Controls

Show two fixed photo slots:

- Front
- Back

Each slot supports:

- Choose
- Preview
- Replace
- Delete
- Upload progress
- Retry after failure

Photo controls communicate that images are private to the account. File
requirements appear only beside the upload control or after validation, not as
general page instructions.

The create workflow is:

1. Create the lot.
2. Upload selected front/back photos.
3. Refresh the portfolio.

If a photo upload fails, the lot remains saved. The interface identifies the
failed side and offers retry without making the user recreate the lot.

### 9.4 Positions and Lots

Raw, PSA 9, and PSA 10 appear as separate rows or mobile position cards.

Each position shows:

- Official catalog image
- `Raw` or `PSA {grade}` label
- Exact latest price or `Unpriced`
- Existing quantity, cost, value, and P&L metrics

Expanded lot details show private front/back thumbnails when available.
Opening a thumbnail displays the full private image in an accessible dialog.

### 9.5 Filters and Responsive Behavior

Add a condition filter:

- All
- Raw
- PSA

When PSA is selected, an optional grade filter supports 1 through 10.

Desktop retains the sortable table. Mobile uses stable position cards. Official
and private images have fixed aspect-ratio containers so loading and errors do
not shift the layout. Internal tables may scroll horizontally; the page itself
must not overflow.

## 10. Security and Privacy

- Every portfolio and photo route requires authentication.
- Every lot/photo query includes or joins through
  `PortfolioLot.user_id = current_user.id`.
- Cross-user resource access returns `404`.
- Object storage is private.
- Credentials remain server-side and are never serialized to the frontend.
- Signed URLs are short-lived and never persisted.
- Application logs exclude photo bytes, storage credentials, signed URLs,
  object keys, purchase costs, and full portfolio payloads.
- Original filenames are discarded.
- Embedded image metadata is removed.
- Mutating endpoints use existing application request protections and upload
  rate limits.
- Production backups and retention rules must cover database metadata and the
  private bucket.

## 11. Failure and Consistency Rules

- A missing official image does not block lot creation.
- A missing exact market price produces `unpriced`.
- A disabled photo feature does not block Raw/PSA lot CRUD.
- A failed photo upload leaves the existing photo unchanged.
- A replacement becomes visible only after the new object upload succeeds.
- A failed old-object deletion is retried from the durable outbox.
- A failed portfolio refresh after mutation keeps the successful mutation and
  offers retry.
- Deleting a lot removes it from portfolio reads immediately; object cleanup
  may finish asynchronously.

## 12. Migration and Rollout

### 12.1 Database Migration

1. Add nullable `condition` and `psa_grade`.
2. Backfill every existing lot to Raw.
3. Make `condition` non-null with default `raw`.
4. Install condition/grade check constraints and grouping index.
5. Create photo and deletion-outbox tables.
6. Verify downgrade removes only the new structures and preserves the previous
   portfolio contract.

### 12.2 Deployment Sequence

1. Deploy database and backward-compatible backend fields.
2. Deploy condition-aware grouping, limits, and exact valuation.
3. Deploy Raw/PSA frontend controls and display.
4. Configure private object storage with photos still disabled.
5. Deploy photo backend and frontend.
6. Run storage, ownership, and browser acceptance checks.
7. Enable `PORTFOLIO_PHOTOS_ENABLED`.

Older clients that omit `condition` continue to create Raw lots.

## 13. Testing Strategy

### 13.1 Backend

- Migration upgrade, downgrade, and existing-lot Raw backfill
- Condition and grade database constraints
- Request validation for every Raw/PSA combination
- PSA grades 1 through 10
- Grouping by `(asset_id, condition, psa_grade)`
- Raw and multiple PSA grades for one catalog asset
- Free position counting by complete identity
- Additional lot for an existing complete identity at the limit
- Edit that merges into an existing identity
- Edit that creates a new identity at the limit
- Exact active-source Raw valuation
- Exact active-source PSA valuation
- Structured PSA company and score validation
- Rejection of neighboring grades and other grading companies
- Unpriced PSA behavior while graded observations lack authority
- Summary unpriced cost basis
- Official image extraction and missing-image fallback
- Photo create, replace, read, and delete
- One-photo-per-side uniqueness
- Byte-size, media-sniffing, animation, and decompression protections
- Orientation, resize, EXIF removal, and WebP output
- Private object keys and signed URL TTL
- User ownership isolation on every photo route
- Storage-disabled behavior
- Storage failure without lot loss
- Deletion-outbox retry and idempotency
- Lot-delete photo cascade and asynchronous object cleanup

### 13.2 Frontend

- Official images in search, selection, and positions
- Raw/PSA segmented control
- Grade selector visibility and values 1-10
- Create and edit payloads
- Independent Raw and PSA position rows
- Exact-price and `Unpriced` labels
- Condition and grade filtering
- Front/back choose, preview, replace, delete, and retry
- Lot remains visible after partial photo-upload failure
- Photo-feature-disabled state
- Accessible dialog focus, escape handling, labels, and keyboard controls
- Stable image containers
- 320 px, 390 px, tablet, and desktop layouts
- No page-level horizontal overflow

### 13.3 Integration and Deployment

- Real PostgreSQL migration from the current portfolio revision
- Private R2/S3-compatible bucket smoke test
- Cross-account photo access test
- Railway restart durability test
- Scheduler cleanup retry test
- Full backend, frontend, build, and scoped lint suites

## 14. Acceptance Criteria

The feature is complete when:

1. Existing lots remain present and appear as Raw.
2. A user can add Raw and PSA 1-10 lots from one canonical card search result.
3. Raw and every PSA grade aggregate independently.
4. Free-tier limits count independent holding identities correctly.
5. Each position uses only an exact, accepted price segment.
6. Unavailable exact prices show `Unpriced`, never `$0` or a substitute price.
7. Official catalog art appears where available.
8. Each lot accepts at most one private front and one private back photo.
9. User photos survive Railway restarts and are never publicly readable.
10. A user cannot discover or access another user's lot or photo.
11. Photo failures do not destroy successfully saved lot data.
12. Replaced and deleted objects are removed through a durable retry path.
13. Desktop and mobile experiences pass visual and accessibility checks.
14. Full test and build verification passes without introducing unrelated
    regressions.

## 15. Implementation Boundary

Implementation must extend the existing Portfolio Foundation and existing
market-segment parser. It must not redesign card search, duplicate global
assets, rewrite grade parsing, or admit new graded price sources.

The implementation plan should be split into reviewable slices:

1. Condition/grade schema, migration, API, grouping, limits, and valuation
2. Raw/PSA frontend experience and official images
3. Private storage adapter, photo metadata, processing, and cleanup outbox
4. Private photo API and frontend workflow
5. Full migration, security, browser, and deployment verification
