import pandas as pd
import pytest
from train_claims_risk.features import (
    AGE_BUCKETS,
    FEATURE_COLUMNS,
    LABEL_COLUMN,
    PLAN_TYPES,
    REGION_CODES,
)
from train_claims_risk.generate_data import generate_synthetic_claims


def test_generate_synthetic_claims_has_expected_schema_and_values() -> None:
    data = generate_synthetic_claims(rows=250, seed=123)

    assert list(data.columns) == FEATURE_COLUMNS + [LABEL_COLUMN]
    assert len(data) == 250
    assert set(data["age_bucket"]).issubset(set(AGE_BUCKETS))
    assert set(data["plan_type"]).issubset(set(PLAN_TYPES))
    assert set(data["region_code"]).issubset(set(REGION_CODES))
    assert set(data[LABEL_COLUMN]).issubset({0, 1})
    assert data[LABEL_COLUMN].nunique() == 2


def test_generate_synthetic_claims_is_deterministic() -> None:
    first = generate_synthetic_claims(rows=50, seed=42)
    second = generate_synthetic_claims(rows=50, seed=42)

    pd.testing.assert_frame_equal(first, second)


def test_generate_synthetic_claims_rejects_non_positive_rows() -> None:
    with pytest.raises(ValueError, match="rows must be greater than zero"):
        generate_synthetic_claims(rows=0)

