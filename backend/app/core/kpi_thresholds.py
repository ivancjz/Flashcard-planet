from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Threshold:
    green: float
    yellow: float
    higher_is_better: bool = True


THRESHOLDS: dict[str, Threshold] = {
    "observations_per_day":  Threshold(green=500,  yellow=200),
    "match_rate_pct":        Threshold(green=80.0, yellow=60.0),
    "missing_image_pct":     Threshold(green=15.0, yellow=30.0, higher_is_better=False),
    "review_backlog":        Threshold(green=50,   yellow=100,  higher_is_better=False),
    "high_conf_signal_pct":  Threshold(green=60.0, yellow=40.0),
    "retry_queue_pending":   Threshold(green=50,   yellow=100,  higher_is_better=False),
    "retry_queue_permanent": Threshold(green=10,   yellow=20,   higher_is_better=False),
    "missing_price_pct":     Threshold(green=10.0, yellow=25.0, higher_is_better=False),
}


def kpi_status(key: str, value: float) -> str:
    """Return 'green', 'yellow', 'red', or 'unknown' for the given KPI value."""
    t = THRESHOLDS.get(key)
    if t is None:
        return "unknown"
    if t.higher_is_better:
        return "green" if value >= t.green else ("yellow" if value >= t.yellow else "red")
    else:
        return "green" if value <= t.green else ("yellow" if value <= t.yellow else "red")
