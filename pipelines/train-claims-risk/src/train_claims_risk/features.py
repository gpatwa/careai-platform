LABEL_COLUMN = "high_risk_claim_next_30d"

CATEGORICAL_FEATURES = [
    "age_bucket",
    "plan_type",
    "region_code",
]

NUMERIC_FEATURES = [
    "prior_claim_count",
    "recent_visit_count",
    "medication_count",
    "chronic_condition_count",
]

FEATURE_COLUMNS = [
    "age_bucket",
    "plan_type",
    "prior_claim_count",
    "recent_visit_count",
    "medication_count",
    "chronic_condition_count",
    "region_code",
]

AGE_BUCKETS = ["18-34", "35-49", "50-64", "65+"]
PLAN_TYPES = ["bronze", "silver", "gold", "platinum", "medicare_advantage"]
REGION_CODES = [f"R{i:02d}" for i in range(1, 9)]
