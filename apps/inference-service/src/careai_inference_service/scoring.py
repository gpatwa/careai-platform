from datetime import UTC, datetime
from math import exp

from careai_inference_service.schemas import ClaimsRiskFeatures, RiskBand


def risk_band(score: float) -> RiskBand:
    if score >= 0.66:
        return "high"
    if score >= 0.33:
        return "medium"
    return "low"


def fallback_score(features: ClaimsRiskFeatures) -> float:
    age_factor = {"18-34": 0.0, "35-49": 0.35, "50-64": 0.75, "65+": 1.1}[features.age_bucket]
    plan_factor = {
        "bronze": 0.35,
        "silver": 0.15,
        "gold": 0.0,
        "platinum": -0.10,
        "medicare_advantage": 0.45,
    }[features.plan_type]
    logit = (
        -3.1
        + age_factor * 0.55
        + plan_factor
        + features.prior_claim_count * 0.08
        + features.recent_visit_count * 0.16
        + features.medication_count * 0.07
        + features.chronic_condition_count * 0.48
    )
    return round(1 / (1 + exp(-logit)), 6)


def reason_codes(features: ClaimsRiskFeatures, score: float) -> list[str]:
    reasons: list[str] = []
    if features.chronic_condition_count >= 3:
        reasons.append("CHRONIC_CONDITION_BURDEN")
    if features.prior_claim_count >= 6:
        reasons.append("ELEVATED_PRIOR_CLAIMS")
    if features.recent_visit_count >= 4:
        reasons.append("RECENT_UTILIZATION")
    if features.medication_count >= 6:
        reasons.append("MEDICATION_COMPLEXITY")
    if features.age_bucket in {"50-64", "65+"}:
        reasons.append("AGE_BUCKET_RISK")
    if features.plan_type in {"bronze", "medicare_advantage"}:
        reasons.append("PLAN_SEGMENT_RISK")
    if score >= 0.66:
        reasons.insert(0, "HIGH_SCORE_THRESHOLD")
    if not reasons:
        reasons.append("BASELINE_SYNTHETIC_RISK")
    return reasons[:5]


def feature_warnings(features: ClaimsRiskFeatures, max_feature_age_minutes: int) -> list[str]:
    if features.feature_timestamp is None:
        return ["feature_timestamp_missing"]

    timestamp = features.feature_timestamp
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)

    age_seconds = (datetime.now(UTC) - timestamp).total_seconds()
    if age_seconds < -300:
        return ["feature_timestamp_in_future"]
    if age_seconds > max_feature_age_minutes * 60:
        return ["features_stale"]
    return []
