# Portfolio Private Photos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an authenticated user attach one private front and one private back photo to each portfolio lot, with durable S3-compatible storage, safe image normalization, ownership-checked reads, and retryable cleanup.

**Architecture:** PostgreSQL stores photo metadata and a durable object-deletion outbox while a private S3-compatible adapter stores normalized full and thumbnail WebP objects. Authenticated FastAPI endpoints process uploads through Pillow, scope every operation through the owning lot, and expose only application content paths that resolve to short-lived signed reads. Focused React photo controls integrate with lot creation and editing; failed uploads never roll back a saved lot.

**Tech Stack:** Python 3.12, FastAPI multipart uploads, Pillow 11.3.0, boto3 1.43.6, S3-compatible private storage/Cloudflare R2, SQLAlchemy 2, Alembic, PostgreSQL, APScheduler, Pytest, React 19, TypeScript 6, Vitest, Testing Library.

---

## Prerequisite and Contract

Do not execute this plan until
`docs/superpowers/plans/2026-07-26-portfolio-raw-psa.md` is complete.

Source of truth:

`docs/superpowers/specs/2026-07-26-portfolio-raw-psa-private-photos-design.md`

Invariants:

- A lot has at most one `front` and one `back` photo.
- Both photos are optional and private.
- Accepted inputs are JPEG, PNG, and WebP, at most 8 MB each.
- The server sniffs bytes, rejects animation, corrects orientation, strips
  metadata, caps the longest edge at 2000 pixels, and stores full plus thumbnail
  WebP objects.
- Railway local storage is never durable storage.
- The private bucket has no public-read policy.
- API responses never expose credentials, object keys, or permanent URLs.
- Every read and mutation scopes through `PortfolioLot.user_id`.
- Cross-user access returns `404`.
- Photo upload failure does not remove or roll back an already saved lot.
- Replacement preserves the old photo unless the new upload and metadata flush
  succeed.
- Replaced/deleted objects enter a durable cleanup outbox in the same database
  transaction as metadata removal.
- Photos can remain disabled while Raw/PSA portfolio tracking works normally.

## File Map

### Persistence

- Create `migrations/versions/0046_add_portfolio_photos.py`: photo metadata and
  deletion outbox.
- Create `backend/app/models/portfolio_lot_photo.py`: one row per lot side.
- Create `backend/app/models/storage_object_deletion_job.py`: cleanup outbox.
- Modify `backend/app/models/portfolio_lot.py`: photo relationship.
- Modify `backend/app/models/__init__.py`: model registration.
- Create `tests/test_portfolio_photo_migration.py`: model/revision contract.

### Storage and processing

- Modify `requirements.txt`: pin Pillow 11.3.0 explicitly.
- Modify `.env.example`: private storage settings with photos disabled.
- Modify `backend/app/core/config.py`: validated photo/storage settings.
- Create `backend/app/storage/__init__.py`.
- Create `backend/app/storage/object_store.py`: protocol, boto3 adapter, factory.
- Create `backend/app/services/portfolio_photo_processing.py`: validation and
  normalization.
- Create `tests/test_object_store.py`.
- Create `tests/test_portfolio_photo_processing.py`.
- Modify `tests/test_config_auth_v2.py`: settings regression.

### Photo domain and API

- Create `backend/app/schemas/portfolio_photo.py`: photo response and side type.
- Create `backend/app/services/portfolio_photo_service.py`: owner-scoped photo
  lifecycle and metadata.
- Create `backend/app/api/routes/portfolio_photos.py`: multipart upload, private
  content, and delete routes.
- Modify `backend/app/api/router.py`: register photo routes.
- Modify `backend/app/schemas/portfolio.py`: lot photo metadata.
- Modify `backend/app/services/portfolio_service.py`: eager-load photos and
  build lot responses.
- Modify `backend/app/services/portfolio_service.py`: enqueue photo objects
  before lot deletion.
- Create `tests/test_portfolio_photo_service.py`.
- Create `tests/test_portfolio_photo_api.py`.
- Modify `tests/test_portfolio_service.py`: photo serialization and lot delete.

### Cleanup

- Create `backend/app/services/storage_cleanup_service.py`: due-job claiming,
  idempotent deletion, backoff, and completion.
- Modify `backend/app/services/scheduler_run_log_service.py`: storage-cleanup job
  constant.
- Modify `backend/app/backstage/scheduler.py`: hourly cleanup registration and
  runner.
- Create `tests/test_storage_cleanup_service.py`.
- Modify `tests/test_scheduler_startup.py`: registration and disabled behavior.

### Frontend

- Modify `frontend/src/types/portfolio.ts`: photo metadata on lots.
- Modify `frontend/src/api/portfolio.ts`: upload, delete, and content helpers.
- Modify `frontend/src/api/portfolio.test.ts`: multipart and delete contracts.
- Create `frontend/src/components/PortfolioPhotoFields.tsx`: two private photo
  slots and local previews.
- Create `frontend/src/components/PortfolioPhotoFields.test.tsx`.
- Create `frontend/src/components/PortfolioPhotoViewer.tsx`: authenticated full
  image dialog.
- Create `frontend/src/components/PortfolioPhotoViewer.test.tsx`.
- Modify `frontend/src/components/PortfolioLotDialog.tsx`: pending and existing
  photos.
- Modify `frontend/src/components/PortfolioLotDialog.test.tsx`.
- Modify `frontend/src/components/PortfolioPositionTable.tsx`: lot thumbnails
  and viewer action.
- Modify `frontend/src/components/PortfolioReadView.test.tsx`.
- Modify `frontend/src/pages/PortfolioPage.tsx`: create-then-upload orchestration
  and retry state.
- Modify `frontend/src/pages/PortfolioPage.test.tsx`.
- Modify `frontend/src/styles/theme.css`: fixed slots, thumbnails, viewer, and
  mobile behavior.

### Delivery

- Modify `docs/flashcard-planet-v2/CODEX_EXECUTION_PLAN.md`: verified delivery
  evidence.

---

### Task 1: Persist Photo Metadata and Cleanup Jobs

**Files:**
- Create: `tests/test_portfolio_photo_migration.py`
- Create: `migrations/versions/0046_add_portfolio_photos.py`
- Create: `backend/app/models/portfolio_lot_photo.py`
- Create: `backend/app/models/storage_object_deletion_job.py`
- Modify: `backend/app/models/portfolio_lot.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Write the failing persistence contract**

Create `tests/test_portfolio_photo_migration.py` and assert exact table columns:

```python
PHOTO_COLUMNS = [
    "id",
    "lot_id",
    "side",
    "full_storage_key",
    "thumbnail_storage_key",
    "content_type",
    "full_byte_size",
    "thumbnail_byte_size",
    "width_px",
    "height_px",
    "sha256",
    "created_at",
    "updated_at",
]

JOB_COLUMNS = [
    "id",
    "storage_key",
    "reason",
    "attempt_count",
    "next_attempt_at",
    "last_error",
    "created_at",
    "completed_at",
]
```

Assert:

```python
assert next(iter(photo.__table__.c.lot_id.foreign_keys)).ondelete == "CASCADE"
assert {
    tuple(column.name for column in constraint.columns)
    for constraint in photo.__table__.constraints
    if isinstance(constraint, sa.UniqueConstraint)
} == {("lot_id", "side")}
assert checks["ck_portfolio_lot_photos_side"] == "side IN ('front', 'back')"
assert checks["ck_portfolio_lot_photos_sizes"] == (
    "full_byte_size > 0 AND thumbnail_byte_size > 0"
)
assert checks["ck_portfolio_lot_photos_dimensions"] == (
    "width_px > 0 AND height_px > 0"
)
```

Assert the outbox indexes due incomplete jobs by
`(completed_at, next_attempt_at)` and has non-negative attempts.

- [ ] **Step 2: Write the failing revision contract**

Load `0046_add_portfolio_photos.py` through the existing isolated migration
pattern and assert:

```python
assert migration.revision == "0046"
assert migration.down_revision == "0045"
```

Upgrade creates both tables and indexes. Downgrade drops the outbox first and
photo metadata second.

- [ ] **Step 3: Run the migration test and confirm failure**

Run:

```powershell
python -m pytest tests/test_portfolio_photo_migration.py -q
```

Expected: models and revision `0046` do not exist.

- [ ] **Step 4: Implement the photo model**

Create `backend/app/models/portfolio_lot_photo.py` with named constraints and:

```python
lot: Mapped["PortfolioLot"] = relationship(back_populates="photos")
```

Use `String(8)` for side, `String(64)` for content type, `String(64)` for
SHA-256, `Text` for object keys, and timezone-aware timestamps.

Add to `PortfolioLot`:

```python
photos: Mapped[list["PortfolioLotPhoto"]] = relationship(
    back_populates="lot",
    cascade="all, delete-orphan",
    passive_deletes=True,
)
```

- [ ] **Step 5: Implement the deletion-job model**

Create `backend/app/models/storage_object_deletion_job.py` with:

```python
attempt_count: Mapped[int] = mapped_column(
    Integer,
    nullable=False,
    default=0,
    server_default="0",
)
next_attempt_at: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    nullable=False,
    server_default=func.now(),
)
completed_at: Mapped[datetime | None] = mapped_column(
    DateTime(timezone=True),
)
```

Import and export both models from `backend/app/models/__init__.py`.

- [ ] **Step 6: Add revision 0046**

Create both tables with the exact model contract. Use:

```python
sa.UniqueConstraint(
    "lot_id",
    "side",
    name="uq_portfolio_lot_photos_lot_side",
)
```

Create:

```text
ix_portfolio_lot_photos_lot_id
ix_storage_object_deletion_jobs_due
```

- [ ] **Step 7: Run persistence tests**

Run:

```powershell
python -m pytest tests/test_portfolio_photo_migration.py tests/test_init_db.py -q
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit persistence**

```powershell
git add migrations/versions/0046_add_portfolio_photos.py backend/app/models tests/test_portfolio_photo_migration.py
git commit -m "feat: add private portfolio photo persistence"
```

---

### Task 2: Normalize Images Safely

**Files:**
- Modify: `requirements.txt`
- Create: `backend/app/services/portfolio_photo_processing.py`
- Create: `tests/test_portfolio_photo_processing.py`

- [ ] **Step 1: Pin the direct dependency**

Add:

```text
Pillow==11.3.0
```

Pillow is already present transitively in the current workspace; pinning makes
the production dependency explicit.

- [ ] **Step 2: Write failing processing tests**

Generate in-memory JPEG, PNG, and WebP fixtures with Pillow. Assert:

```python
processed = process_portfolio_photo(source_bytes)
assert processed.content_type == "image/webp"
assert processed.width_px <= 2000
assert processed.height_px <= 2000
assert processed.full_bytes.startswith(b"RIFF")
assert processed.thumbnail_bytes.startswith(b"RIFF")
assert len(processed.sha256) == 64
```

Add tests for:

- 8 MB accepted and 8 MB plus one byte rejected before Pillow decode
- invalid bytes
- GIF and animated WebP rejection
- EXIF orientation correction
- metadata absence in saved WebP
- longest edge capped at 2000
- thumbnail longest edge capped at 320
- decompression-bomb error mapping

- [ ] **Step 3: Run tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_portfolio_photo_processing.py -q
```

Expected: processing module does not exist.

- [ ] **Step 4: Implement processing types and errors**

Create:

```python
MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_LONG_EDGE = 2000
THUMBNAIL_LONG_EDGE = 320
ACCEPTED_FORMATS = {"JPEG", "PNG", "WEBP"}

@dataclass(frozen=True)
class ProcessedPortfolioPhoto:
    full_bytes: bytes
    thumbnail_bytes: bytes
    content_type: str
    width_px: int
    height_px: int
    sha256: str

class PortfolioPhotoInvalidError(ValueError):
    pass

class PortfolioPhotoTooLargeError(PortfolioPhotoInvalidError):
    pass
```

- [ ] **Step 5: Implement byte sniffing and normalization**

Use:

```python
with Image.open(BytesIO(source)) as image:
    if image.format not in ACCEPTED_FORMATS:
        raise PortfolioPhotoInvalidError("Unsupported image format.")
    if getattr(image, "is_animated", False):
        raise PortfolioPhotoInvalidError("Animated images are not supported.")
    image = ImageOps.exif_transpose(image)
    image.load()
    normalized = image.convert("RGB")
    normalized.thumbnail((MAX_LONG_EDGE, MAX_LONG_EDGE), Image.Resampling.LANCZOS)
```

Save full and thumbnail to new `BytesIO` buffers with `format="WEBP"` and no
copied metadata. Calculate SHA-256 from the normalized full bytes.

Catch `UnidentifiedImageError`, `DecompressionBombError`, truncated-image
errors, and encoder errors as `PortfolioPhotoInvalidError` without returning
Pillow internals to the API.

- [ ] **Step 6: Run processing tests**

Run:

```powershell
python -m pytest tests/test_portfolio_photo_processing.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit processing**

```powershell
git add requirements.txt backend/app/services/portfolio_photo_processing.py tests/test_portfolio_photo_processing.py
git commit -m "feat: normalize private portfolio photos"
```

---

### Task 3: Add the Private Object-Storage Adapter

**Files:**
- Modify: `.env.example`
- Modify: `backend/app/core/config.py`
- Create: `backend/app/storage/__init__.py`
- Create: `backend/app/storage/object_store.py`
- Create: `tests/test_object_store.py`
- Modify: `tests/test_config_auth_v2.py`

- [ ] **Step 1: Write failing configuration tests**

Assert defaults:

```python
settings = Settings(_env_file=None)
assert settings.portfolio_photos_enabled is False
assert settings.object_storage_signed_url_ttl_seconds == 60
assert settings.portfolio_photo_cleanup_batch_size == 100
```

Assert `photos_enabled` requires endpoint, bucket, access key, and secret:

```python
with pytest.raises(ValidationError):
    Settings(_env_file=None, portfolio_photos_enabled=True)
```

- [ ] **Step 2: Write failing adapter tests**

Mock `boto3.client` and assert:

```python
store.put_bytes(
    "portfolio/random/full.webp",
    b"image",
    content_type="image/webp",
)
client.put_object.assert_called_once_with(
    Bucket="private-bucket",
    Key="portfolio/random/full.webp",
    Body=b"image",
    ContentType="image/webp",
)
```

Test delete idempotency and:

```python
client.generate_presigned_url.assert_called_once_with(
    "get_object",
    Params={"Bucket": "private-bucket", "Key": key},
    ExpiresIn=60,
)
```

- [ ] **Step 3: Run tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_object_store.py tests/test_config_auth_v2.py -q
```

Expected: storage settings and adapter are missing.

- [ ] **Step 4: Add validated settings**

Add to `Settings`:

```python
portfolio_photos_enabled: bool = False
object_storage_endpoint_url: str = ""
object_storage_region: str = "auto"
object_storage_bucket: str = ""
object_storage_access_key_id: str = ""
object_storage_secret_access_key: str = ""
object_storage_signed_url_ttl_seconds: int = Field(default=60, ge=30, le=300)
portfolio_photo_cleanup_batch_size: int = Field(default=100, ge=1, le=500)
```

Add a model validator that rejects enabled configuration when any required
storage value is blank. Do not print the missing secret value.

- [ ] **Step 5: Implement the adapter**

Create a protocol:

```python
class ObjectStore(Protocol):
    def put_bytes(self, key: str, data: bytes, *, content_type: str) -> None:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def signed_get_url(self, key: str, *, expires_in: int) -> str:
        raise NotImplementedError
```

Implement `S3ObjectStore` with the configured endpoint and credentials. Add:

```python
def build_object_store(settings: Settings) -> ObjectStore:
    if not settings.portfolio_photos_enabled:
        raise ObjectStorageUnavailableError("Portfolio photos are disabled.")
    return S3ObjectStore.from_settings(settings)
```

Never log credentials, signed URLs, or keys.

- [ ] **Step 6: Document environment variables**

Append to `.env.example`:

```text
# Private portfolio photos. Enable only after a private R2/S3 bucket is verified.
PORTFOLIO_PHOTOS_ENABLED=false
OBJECT_STORAGE_ENDPOINT_URL=
OBJECT_STORAGE_REGION=auto
OBJECT_STORAGE_BUCKET=
OBJECT_STORAGE_ACCESS_KEY_ID=
OBJECT_STORAGE_SECRET_ACCESS_KEY=
OBJECT_STORAGE_SIGNED_URL_TTL_SECONDS=60
PORTFOLIO_PHOTO_CLEANUP_BATCH_SIZE=100
```

- [ ] **Step 7: Run adapter and config tests**

Run:

```powershell
python -m pytest tests/test_object_store.py tests/test_config_auth_v2.py -q
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit storage boundary**

```powershell
git add .env.example backend/app/core/config.py backend/app/storage tests/test_object_store.py tests/test_config_auth_v2.py
git commit -m "feat: add private object storage adapter"
```

---

### Task 4: Implement Owner-Scoped Photo Lifecycle

**Files:**
- Create: `backend/app/schemas/portfolio_photo.py`
- Create: `backend/app/services/portfolio_photo_service.py`
- Modify: `backend/app/schemas/portfolio.py`
- Modify: `backend/app/services/portfolio_service.py`
- Create: `tests/test_portfolio_photo_service.py`
- Modify: `tests/test_portfolio_service.py`

- [ ] **Step 1: Write failing service tests**

Cover:

```python
result = replace_photo(
    db,
    current_user=user,
    lot_id=lot.id,
    side="front",
    source_bytes=jpeg_bytes,
    object_store=store,
)
assert result.photo.side == "front"
assert result.photo.lot_id == lot.id
assert len(result.new_storage_keys) == 2
assert store.put_bytes.call_count == 2
```

Add tests for:

- Back creates a second row.
- A third side is rejected.
- Replacing Front keeps one row and enqueues both old keys.
- A storage failure leaves prior metadata unchanged.
- A flush failure deletes newly uploaded objects best-effort.
- Cross-user replace, read, and delete raise the typed not-found error.
- Delete removes metadata and enqueues full plus thumbnail keys.
- Lot deletion enqueues every owned photo key before cascade.

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_portfolio_photo_service.py tests/test_portfolio_service.py -k "photo" -q
```

Expected: photo schemas and service are missing.

- [ ] **Step 3: Define schemas**

Create:

```python
PhotoSide = Literal["front", "back"]
PhotoVariant = Literal["thumbnail", "full"]

class PortfolioPhotoResponse(BaseModel):
    id: UUID
    side: PhotoSide
    thumbnail_path: str
    content_path: str
```

Add `photos: list[PortfolioPhotoResponse] = []` to
`PortfolioLotResponse`. Add `photo_uploads_enabled: bool` to
`PortfolioResponse` and populate it from the validated server setting so the
frontend can hide unavailable controls. Build paths from lot ID and side; never
serialize storage keys.

- [ ] **Step 4: Implement private ownership and keys**

In `portfolio_photo_service.py`, every load begins with:

```python
select(PortfolioLot).where(
    PortfolioLot.id == lot_id,
    PortfolioLot.user_id == current_user.id,
)
```

Generate keys with UUIDs:

```python
prefix = f"portfolio-photos/{uuid4()}"
full_key = f"{prefix}/full.webp"
thumbnail_key = f"{prefix}/thumbnail.webp"
```

The key contains no user email, filename, card name, or lot ID.

- [ ] **Step 5: Implement replace and delete**

Replace order:

1. Validate ownership and side.
2. Process source bytes.
3. Upload full and thumbnail under new keys.
4. Insert/update metadata.
5. Enqueue each prior key.
6. Flush.

Return a `PhotoMutationResult` containing the photo row and both
`new_storage_keys`. On any failure before flush succeeds, best-effort delete
both new objects and leave the old row unchanged through transaction rollback.
The API route uses `new_storage_keys` to remove newly uploaded objects if the
subsequent database commit fails.

Delete metadata and enqueue two jobs in one transaction:

```python
def enqueue_object_deletion(
    db: Session,
    storage_key: str,
    reason: str,
) -> None:
    db.add(StorageObjectDeletionJob(
        storage_key=storage_key,
        reason=reason,
    ))
```

- [ ] **Step 6: Integrate portfolio reads and lot deletion**

Eager-load:

```python
selectinload(PortfolioLot.photos)
```

Sort photos Front then Back. Build response paths in `_lot_response()`.

Before `db.delete(lot)`, enqueue both keys for every photo. Cascading metadata
deletion remains immediate; object deletion is asynchronous.

- [ ] **Step 7: Run photo service and portfolio tests**

Run:

```powershell
python -m pytest tests/test_portfolio_photo_service.py tests/test_portfolio_service.py tests/test_portfolio_schemas.py -q
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit the photo domain**

```powershell
git add backend/app/schemas/portfolio_photo.py backend/app/schemas/portfolio.py backend/app/services/portfolio_photo_service.py backend/app/services/portfolio_service.py tests/test_portfolio_photo_service.py tests/test_portfolio_service.py
git commit -m "feat: add private portfolio photo lifecycle"
```

---

### Task 5: Expose Authenticated Photo Endpoints

**Files:**
- Create: `tests/test_portfolio_photo_api.py`
- Create: `backend/app/api/routes/portfolio_photos.py`
- Modify: `backend/app/api/router.py`

- [ ] **Step 1: Write failing API tests**

Test all routes require authentication:

```text
PUT /api/v1/portfolio/lots/{lot_id}/photos/front
GET /api/v1/portfolio/lots/{lot_id}/photos/front/content?variant=thumbnail
DELETE /api/v1/portfolio/lots/{lot_id}/photos/front
```

Assert upload:

```python
response = client.put(
    f"/api/v1/portfolio/lots/{lot.id}/photos/front",
    files={"file": ("front.jpg", jpeg_bytes, "image/jpeg")},
)
assert response.status_code == 201
```

Add replacement `200`, delete `204`, invalid side `422`, over-size `413`,
invalid media `415`, foreign resource `404`, disabled storage `503`, and storage
failure `503`. Force `db.commit()` to fail after a successful upload and assert
both `new_storage_keys` are deleted best-effort before rollback while the prior
photo remains authoritative.

- [ ] **Step 2: Write private content tests**

Mock the adapter and assert:

```python
response = client.get(
    f"/api/v1/portfolio/lots/{lot.id}/photos/front/content",
    params={"variant": "full"},
    follow_redirects=False,
)
assert response.status_code == 307
assert response.headers["location"] == "https://signed.example/private"
assert response.headers["cache-control"] == "private, no-store"
```

Assert another user receives `404` and no signed URL is generated.

- [ ] **Step 3: Run API tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_portfolio_photo_api.py -q
```

Expected: photo router does not exist.

- [ ] **Step 4: Implement the upload route**

Before constructing or calling the object-store adapter, load the lot with the
current user's ID. This preserves `404` for foreign lots even when storage is
disabled or unavailable.

Use `UploadFile` and read with a hard cap:

```python
source = await file.read(MAX_SOURCE_BYTES + 1)
if len(source) > MAX_SOURCE_BYTES:
    raise HTTPException(status_code=413, detail="Photo exceeds 8 MB.")
```

Map typed errors:

```text
PortfolioPhotoNotFoundError -> 404
PortfolioPhotoTooLargeError -> 413
PortfolioPhotoInvalidError -> 415
ObjectStorageUnavailableError -> 503
```

Commit only after service success. If commit fails after `replace_photo()`
returns, best-effort delete every key in `result.new_storage_keys`, roll back,
and re-raise. This closes the object leak between successful upload and failed
PostgreSQL commit.

- [ ] **Step 5: Implement private read and delete**

For content, load the owned photo and choose the full or thumbnail key. Generate
a signed URL with configured TTL and return:

```python
RedirectResponse(
    url=signed_url,
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    headers={"Cache-Control": "private, no-store"},
)
```

Delete commits metadata removal plus outbox insertion and returns 204.

- [ ] **Step 6: Register the router**

Include `portfolio_photos.router` under `settings.api_prefix`. Add a route-map
assertion containing exact methods and paths.

- [ ] **Step 7: Run API tests**

Run:

```powershell
python -m pytest tests/test_portfolio_photo_api.py tests/test_portfolio_api.py tests/test_main.py -q
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit endpoints**

```powershell
git add backend/app/api/routes/portfolio_photos.py backend/app/api/router.py tests/test_portfolio_photo_api.py
git commit -m "feat: add authenticated portfolio photo api"
```

---

### Task 6: Process the Durable Deletion Outbox

**Files:**
- Create: `backend/app/services/storage_cleanup_service.py`
- Modify: `backend/app/services/scheduler_run_log_service.py`
- Modify: `backend/app/backstage/scheduler.py`
- Create: `tests/test_storage_cleanup_service.py`
- Modify: `tests/test_scheduler_startup.py`

- [ ] **Step 1: Write failing cleanup tests**

Assert due jobs are processed in bounded batches:

```python
result = run_storage_object_cleanup(
    db,
    object_store=store,
    now=NOW,
    batch_size=100,
)
assert result.claimed == 2
assert result.deleted == 2
assert result.failed == 0
assert all(job.completed_at == NOW for job in jobs)
```

Add:

- Completed and future jobs are skipped.
- Missing objects count as successful idempotent deletion.
- Failure increments attempts, stores a bounded error string, and sets
  `next_attempt_at` using 5m, 30m, 2h, 12h, then 24h maximum backoff.
- Batch size is enforced.

- [ ] **Step 2: Write failing scheduler tests**

When photos are enabled, assert one hourly job:

```text
id=storage-object-cleanup
max_instances=1
coalesce=True
```

When photos are disabled, assert the job is not registered.

- [ ] **Step 3: Run tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_storage_cleanup_service.py tests/test_scheduler_startup.py -q
```

Expected: cleanup service and job do not exist.

- [ ] **Step 4: Implement cleanup service**

Select due rows:

```python
select(StorageObjectDeletionJob)
.where(
    StorageObjectDeletionJob.completed_at.is_(None),
    StorageObjectDeletionJob.next_attempt_at <= now,
)
.order_by(
    StorageObjectDeletionJob.next_attempt_at,
    StorageObjectDeletionJob.created_at,
    StorageObjectDeletionJob.id,
)
.limit(batch_size)
.with_for_update(skip_locked=True)
```

Delete each key. Mark success with `completed_at=now`. On failure, update
attempts, backoff, and `last_error=str(exc)[:500]`. Do not log the key.

- [ ] **Step 5: Register the scheduler runner**

Add `JOB_STORAGE_OBJECT_CLEANUP = "storage-object-cleanup"` to run-log constants.
Register only when `portfolio_photos_enabled`.

The wrapper opens its own session, records start/finish, commits the cleanup
result, and prunes old run logs. Use a distinct startup delay of 1680 seconds.

- [ ] **Step 6: Run cleanup and scheduler tests**

Run:

```powershell
python -m pytest tests/test_storage_cleanup_service.py tests/test_scheduler_startup.py tests/test_scheduler_run_log_cleanup.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit cleanup**

```powershell
git add backend/app/services/storage_cleanup_service.py backend/app/services/scheduler_run_log_service.py backend/app/backstage/scheduler.py tests/test_storage_cleanup_service.py tests/test_scheduler_startup.py
git commit -m "feat: retry private object cleanup"
```

---

### Task 7: Add Front and Back Photo Workflows

**Files:**
- Modify: `frontend/src/types/portfolio.ts`
- Modify: `frontend/src/api/portfolio.ts`
- Modify: `frontend/src/api/portfolio.test.ts`
- Create: `frontend/src/components/PortfolioPhotoFields.tsx`
- Create: `frontend/src/components/PortfolioPhotoFields.test.tsx`
- Create: `frontend/src/components/PortfolioPhotoViewer.tsx`
- Create: `frontend/src/components/PortfolioPhotoViewer.test.tsx`
- Modify: `frontend/src/components/PortfolioLotDialog.tsx`
- Modify: `frontend/src/components/PortfolioLotDialog.test.tsx`
- Modify: `frontend/src/components/PortfolioPositionTable.tsx`
- Modify: `frontend/src/components/PortfolioReadView.test.tsx`
- Modify: `frontend/src/pages/PortfolioPage.tsx`
- Modify: `frontend/src/pages/PortfolioPage.test.tsx`
- Modify: `frontend/src/styles/theme.css`

- [ ] **Step 1: Write failing API client tests**

Assert multipart upload:

```typescript
await putPortfolioPhoto('lot/1', 'front', file)
const [url, init] = fetchMock.mock.calls[0]
expect(url).toBe('/api/v1/portfolio/lots/lot%2F1/photos/front')
expect(init.method).toBe('PUT')
expect(init.credentials).toBe('same-origin')
expect(init.body).toBeInstanceOf(FormData)
expect(init.headers).toBeUndefined()
```

Assert delete uses the encoded lot and side path and accepts 204. Do not set a
multipart `Content-Type` header manually.

- [ ] **Step 2: Write failing photo-field tests**

For two labeled slots, assert:

```typescript
expect(screen.getByLabelText('Front photo')).toBeTruthy()
expect(screen.getByLabelText('Back photo')).toBeTruthy()
```

Select a JPEG and assert local preview URLs, replace, remove, 8 MB client-side
rejection, and URL revocation on replacement/unmount. Client validation is
advisory; server validation remains authoritative.

- [ ] **Step 3: Write failing orchestration tests**

Create a lot with two selected photos. Assert:

```typescript
expect(createPortfolioLotMock).toHaveBeenCalledBefore(
  putPortfolioPhotoMock,
)
expect(putPortfolioPhotoMock).toHaveBeenCalledWith(
  createdLot.id,
  'front',
  frontFile,
)
expect(putPortfolioPhotoMock).toHaveBeenCalledWith(
  createdLot.id,
  'back',
  backFile,
)
```

When Back upload fails:

- The created lot remains in refreshed portfolio data.
- The page identifies `Back photo could not be uploaded`.
- A Retry button reuses the retained Back `File`.
- Front is not uploaded again.

- [ ] **Step 4: Run frontend photo tests and confirm failure**

Run:

```powershell
cd frontend
npm test -- --run src/api/portfolio.test.ts src/components/PortfolioPhotoFields.test.tsx src/components/PortfolioPhotoViewer.test.tsx src/components/PortfolioLotDialog.test.tsx src/components/PortfolioReadView.test.tsx src/pages/PortfolioPage.test.tsx
```

Expected: photo API and components are missing.

- [ ] **Step 5: Add client contracts**

Add `photo_uploads_enabled: boolean` to `Portfolio`. Add these contracts and
`photos: PortfolioPhotoMetadata[]` to `PortfolioLot`:

```typescript
export type PortfolioPhotoSide = 'front' | 'back'

export interface PortfolioPhotoMetadata {
  id: string
  side: PortfolioPhotoSide
  thumbnail_path: string
  content_path: string
}

export type PendingPortfolioPhotos = Partial<
  Record<PortfolioPhotoSide, File>
>
```

Implement `putPortfolioPhoto()` and `deletePortfolioPhoto()` through the
existing typed error handling.

- [ ] **Step 6: Implement focused photo components**

Render `PortfolioPhotoFields` only when `portfolio.photo_uploads_enabled` is
true. When false, show no empty upload slots and retain existing Raw/PSA lot
controls.

`PortfolioPhotoFields` receives:

```typescript
interface PortfolioPhotoFieldsProps {
  existing: PortfolioPhotoMetadata[]
  pending: PendingPortfolioPhotos
  disabled: boolean
  onPendingChange: (photos: PendingPortfolioPhotos) => void
  onDeleteExisting: (side: PortfolioPhotoSide) => Promise<void>
  onOpenExisting: (photo: PortfolioPhotoMetadata) => void
}
```

Render two fixed aspect-ratio slots. Use `Image`, `Trash2`, and `RefreshCw`
Lucide icons with tooltips. Include concise private-account text near the slots.

`PortfolioPhotoViewer` uses the existing focus-trap and scroll-lock hooks,
Escape close, and the authenticated `content_path`.

- [ ] **Step 7: Implement create-then-upload with retry**

Define:

```typescript
interface PhotoRetryState {
  lotId: string
  failed: PendingPortfolioPhotos
}
```

Page sequence:

1. Create or patch the lot.
2. Upload only pending sides with `Promise.allSettled`.
3. Refresh portfolio regardless of photo outcome.
4. Close the lot dialog after the lot mutation succeeds.
5. Store failed sides in `PhotoRetryState`.
6. Retry only failed sides; clear each side after success.

The page alert must say the lot was saved. It must not report the whole mutation
as failed.

- [ ] **Step 8: Render lot thumbnails**

Within expanded lot rows, sort Front then Back and render fixed thumbnails.
Opening a thumbnail launches `PortfolioPhotoViewer`. Missing photos leave no
empty decorative card.

- [ ] **Step 9: Add responsive styles**

Use fixed slot and thumbnail dimensions, 8px-or-less radii, visible keyboard
focus, and mobile wrapping. Verify long file-error text wraps within the dialog.
Do not use public background-image URLs.

- [ ] **Step 10: Run frontend tests and build**

Run:

```powershell
cd frontend
npm test -- --run src/api/portfolio.test.ts src/components/PortfolioPhotoFields.test.tsx src/components/PortfolioPhotoViewer.test.tsx src/components/PortfolioLotDialog.test.tsx src/components/PortfolioReadView.test.tsx src/pages/PortfolioPage.test.tsx
npm run build
```

Expected: all selected tests pass and build succeeds.

- [ ] **Step 11: Commit the frontend workflow**

```powershell
git add frontend/src/types/portfolio.ts frontend/src/api/portfolio.ts frontend/src/api/portfolio.test.ts frontend/src/components/PortfolioPhotoFields.tsx frontend/src/components/PortfolioPhotoFields.test.tsx frontend/src/components/PortfolioPhotoViewer.tsx frontend/src/components/PortfolioPhotoViewer.test.tsx frontend/src/components/PortfolioLotDialog.tsx frontend/src/components/PortfolioLotDialog.test.tsx frontend/src/components/PortfolioPositionTable.tsx frontend/src/components/PortfolioReadView.test.tsx frontend/src/pages/PortfolioPage.tsx frontend/src/pages/PortfolioPage.test.tsx frontend/src/styles/theme.css
git commit -m "feat: add private portfolio photo workflow"
```

---

### Task 8: Verify Privacy, Durability, and Deployment

**Files:**
- Modify: `docs/flashcard-planet-v2/CODEX_EXECUTION_PLAN.md`

- [ ] **Step 1: Run real PostgreSQL migration verification**

From revision `0045`:

```powershell
python -m alembic upgrade 0046
python -m alembic downgrade 0045
python -m alembic upgrade 0046
```

Expected: photo/outbox tables and indexes appear, disappear, and reappear
cleanly.

- [ ] **Step 2: Verify a private R2/S3 bucket**

With a dedicated non-production private bucket:

1. Confirm anonymous GET for a test object returns access denied.
2. Upload through the application.
3. Confirm full and thumbnail objects survive an application restart.
4. Confirm a signed URL expires after the configured TTL.
5. Replace and delete the photo.
6. Run cleanup and confirm both obsolete objects are removed.

Never print credentials or signed URLs in captured verification output.

- [ ] **Step 3: Run backend verification**

Run:

```powershell
python -m pytest tests/test_portfolio_photo_migration.py tests/test_portfolio_photo_processing.py tests/test_object_store.py tests/test_portfolio_photo_service.py tests/test_portfolio_photo_api.py tests/test_storage_cleanup_service.py tests/test_portfolio_service.py tests/test_scheduler_startup.py -q
python -m pytest -q
```

Expected: scoped and full backend suites pass.

- [ ] **Step 4: Run frontend verification**

Run:

```powershell
cd frontend
npm test -- --run
npm run build
npx eslint src/types/portfolio.ts src/api/portfolio.ts src/api/portfolio.test.ts src/components/PortfolioPhotoFields.tsx src/components/PortfolioPhotoFields.test.tsx src/components/PortfolioPhotoViewer.tsx src/components/PortfolioPhotoViewer.test.tsx src/components/PortfolioLotDialog.tsx src/components/PortfolioLotDialog.test.tsx src/components/PortfolioPositionTable.tsx src/components/PortfolioReadView.test.tsx src/pages/PortfolioPage.tsx src/pages/PortfolioPage.test.tsx
```

Expected: all frontend tests pass, build succeeds, and scoped lint has no
errors.

- [ ] **Step 5: Run browser acceptance**

Test 1440x900, 1024x768, 390x844, and 320x568:

- Official image remains separate from private photos.
- Front and Back accept, preview, replace, and remove independently.
- A failed Back upload leaves the saved lot and successful Front photo intact.
- Retry uploads only Back.
- Private full-image dialog traps focus, closes with Escape, and locks scroll.
- Long validation errors wrap.
- Image loading does not shift controls.
- No page-level horizontal overflow exists.

- [ ] **Step 6: Run cross-account security verification**

Create User A and User B. As User B, call all three operations against User A's
lot:

```text
PUT photo
GET photo content
DELETE photo
```

Expected: all return `404`; the object adapter receives no signed-read,
overwrite, or delete call.

Scan changed files:

```powershell
rg -n "storage_key|secret_access_key|signed_get_url|user_id" backend/app/api/routes/portfolio_photos.py backend/app/schemas/portfolio.py backend/app/schemas/portfolio_photo.py frontend/src
```

Expected: response schemas/frontend contain no storage key, secret, or signed
URL persistence; API identity comes from the authenticated user.

- [ ] **Step 7: Verify disabled operation**

Set:

```text
PORTFOLIO_PHOTOS_ENABLED=false
```

Expected:

- Backend starts.
- Raw/PSA portfolio reads and lot CRUD work.
- Upload/read/delete return the documented unavailable response.
- Cleanup job is not registered.
- Frontend hides or disables upload controls with a neutral unavailable state.

- [ ] **Step 8: Record delivery**

Update `docs/flashcard-planet-v2/CODEX_EXECUTION_PLAN.md` with actual:

- Test counts
- Migration verification
- Private-bucket and restart durability evidence
- Cross-account 404 evidence
- Cleanup retry evidence
- Browser screenshot paths
- Production environment variable names, without values

- [ ] **Step 9: Commit verification records**

```powershell
git add docs/flashcard-planet-v2/CODEX_EXECUTION_PLAN.md
git commit -m "docs: record private portfolio photo delivery"
```

---

## Release Gate

Keep `PORTFOLIO_PHOTOS_ENABLED=false` until migration, private-bucket,
cross-account, cleanup, full test, build, lint, and browser checks all pass in
the deployed environment. Enabling photos is an operational configuration
change, not a code change.

