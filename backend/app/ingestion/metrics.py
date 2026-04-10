from __future__ import annotations

from typing import Any

try:
    from prometheus_client import Counter, Histogram
except ImportError:  # pragma: no cover - exercised by local environment fallback
    class _NullMetric:
        def labels(self, *args: Any, **kwargs: Any) -> "_NullMetric":
            return self

        def inc(self, amount: float = 1.0) -> None:
            return None

        def observe(self, amount: float) -> None:
            return None

    def Counter(*args: Any, **kwargs: Any) -> _NullMetric:  # type: ignore[misc]
        return _NullMetric()

    def Histogram(*args: Any, **kwargs: Any) -> _NullMetric:  # type: ignore[misc]
        return _NullMetric()


INGESTION_LISTINGS_FETCHED_TOTAL = Counter(
    "ingestion_listings_fetched_total",
    "Listings fetched from source.",
    ["source"],
)
INGESTION_LISTINGS_STAGED_TOTAL = Counter(
    "ingestion_listings_staged_total",
    "Listings staged after dedupe.",
    ["source", "deduped"],
)
INGESTION_NOISE_FILTERED_TOTAL = Counter(
    "ingestion_noise_filtered_total",
    "Listings filtered as noise by AI pre-filter.",
)
INGESTION_CACHE_HITS_TOTAL = Counter(
    "ingestion_cache_hits_total",
    "Mapping cache hits.",
)
INGESTION_RULE_MATCHES_TOTAL = Counter(
    "ingestion_rule_matches_total",
    "Rule-engine matches.",
    ["confidence_bucket"],
)
INGESTION_AI_CALLS_TOTAL = Counter(
    "ingestion_ai_calls_total",
    "AI mapper calls.",
)
INGESTION_AI_LISTINGS_MAPPED_TOTAL = Counter(
    "ingestion_ai_listings_mapped_total",
    "AI mapped listings.",
    ["confidence_bucket"],
)
INGESTION_HUMAN_REVIEW_QUEUE_TOTAL = Counter(
    "ingestion_human_review_queue_total",
    "Listings queued for human review.",
)
INGESTION_ASSETS_WRITTEN_TOTAL = Counter(
    "ingestion_assets_written_total",
    "Assets written or reused for prices.",
    ["method"],
)
INGESTION_BATCH_DURATION_SECONDS = Histogram(
    "ingestion_batch_duration_seconds",
    "Batch stage duration.",
    ["stage"],
)
INGESTION_ERRORS_TOTAL = Counter(
    "ingestion_errors_total",
    "Ingestion errors by stage and type.",
    ["stage", "error_type"],
)
