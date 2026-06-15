from collections import Counter
from math import ceil, log
from typing import Any, Literal

FEATURE_COLUMNS = [
    "age_bucket",
    "plan_type",
    "prior_claim_count",
    "recent_visit_count",
    "medication_count",
    "chronic_condition_count",
    "region_code",
]

NUMERIC_FEATURE_BINS: dict[str, list[tuple[int, int | None]]] = {
    "prior_claim_count": [(0, 0), (1, 2), (3, 5), (6, 10), (11, 25), (26, None)],
    "recent_visit_count": [(0, 0), (1, 1), (2, 3), (4, 6), (7, 12), (13, None)],
    "medication_count": [(0, 0), (1, 2), (3, 5), (6, 10), (11, 20), (21, None)],
    "chronic_condition_count": [(0, 0), (1, 1), (2, 2), (3, 4), (5, 7), (8, None)],
}

DriftStatus = Literal["green", "yellow", "red"]
SloStatus = Literal["healthy", "breached", "unknown"]


def numeric_bin_label(lower: int, upper: int | None) -> str:
    if upper is None:
        return f">={lower}"
    if lower == upper:
        return str(lower)
    return f"{lower}-{upper}"


def bucket_numeric_value(value: Any, bins: list[tuple[int, int | None]]) -> str:
    if value is None:
        return "__missing__"

    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return "__invalid__"

    for lower, upper in bins:
        if upper is None and numeric_value >= lower:
            return numeric_bin_label(lower, upper)
        if upper is not None and lower <= numeric_value <= upper:
            return numeric_bin_label(lower, upper)
    return "__out_of_range__"


def feature_distribution(
    records: list[dict[str, Any]],
    feature_columns: list[str] | None = None,
) -> dict[str, dict[str, float]]:
    columns = feature_columns or FEATURE_COLUMNS
    distributions: dict[str, dict[str, float]] = {}
    for column in columns:
        counts: Counter[str] = Counter()
        for record in records:
            if column in NUMERIC_FEATURE_BINS:
                bucket = bucket_numeric_value(record.get(column), NUMERIC_FEATURE_BINS[column])
            else:
                value = record.get(column, "__missing__")
                bucket = "__missing__" if value is None else str(value)
            counts[bucket] += 1

        total = sum(counts.values())
        if total == 0:
            distributions[column] = {}
            continue
        distributions[column] = {
            value: count / total for value, count in sorted(counts.items())
        }
    return distributions


def population_stability_index(
    baseline_distribution: dict[str, float],
    recent_distribution: dict[str, float],
    epsilon: float = 1e-6,
) -> float:
    values = set(baseline_distribution) | set(recent_distribution)
    if not values:
        return 0.0

    psi = 0.0
    for value in values:
        baseline_value = max(baseline_distribution.get(value, 0.0), epsilon)
        recent_value = max(recent_distribution.get(value, 0.0), epsilon)
        psi += (recent_value - baseline_value) * log(recent_value / baseline_value)
    return round(float(psi), 6)


def drift_status(value: float, yellow_threshold: float, red_threshold: float) -> DriftStatus:
    if value >= red_threshold:
        return "red"
    if value >= yellow_threshold:
        return "yellow"
    return "green"


def combine_status(statuses: list[DriftStatus]) -> DriftStatus:
    if "red" in statuses:
        return "red"
    if "yellow" in statuses:
        return "yellow"
    return "green"


def calculate_drift(
    *,
    baseline_distribution: dict[str, dict[str, float]],
    recent_distribution: dict[str, dict[str, float]],
    yellow_threshold: float = 0.10,
    red_threshold: float = 0.25,
) -> tuple[DriftStatus, list[dict[str, Any]]]:
    feature_metrics: list[dict[str, Any]] = []
    for feature_name in sorted(set(baseline_distribution) | set(recent_distribution)):
        baseline_feature = baseline_distribution.get(feature_name, {})
        recent_feature = recent_distribution.get(feature_name, {})
        psi = population_stability_index(baseline_feature, recent_feature)
        status = drift_status(psi, yellow_threshold, red_threshold)
        feature_metrics.append(
            {
                "feature_name": feature_name,
                "metric_name": "psi",
                "value": psi,
                "status": status,
                "baseline_distribution": baseline_feature,
                "recent_distribution": recent_feature,
            }
        )
    return combine_status([metric["status"] for metric in feature_metrics]), feature_metrics


def percentile(values: list[int], percentile_value: float) -> int | None:
    if not values:
        return None
    sorted_values = sorted(values)
    index = max(ceil(len(sorted_values) * percentile_value) - 1, 0)
    return sorted_values[min(index, len(sorted_values) - 1)]


def slo_status(
    *,
    event_count: int,
    error_rate: float,
    p95_latency_ms: int | None,
    error_rate_slo: float,
    latency_slo_ms: int,
) -> SloStatus:
    if event_count == 0:
        return "unknown"
    if error_rate > error_rate_slo:
        return "breached"
    if p95_latency_ms is not None and p95_latency_ms > latency_slo_ms:
        return "breached"
    return "healthy"
