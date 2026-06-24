import json

import pandas as pd
import pytest
from train_claims_risk.features import FEATURE_COLUMNS, LABEL_COLUMN
from train_claims_risk.generate_data import write_synthetic_claims
from train_claims_risk.train import load_training_data, train_claims_risk_model


def test_load_training_data_validates_feature_schema(tmp_path) -> None:
    data_path = tmp_path / "bad.csv"
    pd.DataFrame({"age_bucket": ["18-34"], LABEL_COLUMN: [0]}).to_csv(data_path, index=False)

    with pytest.raises(ValueError, match="missing required columns"):
        load_training_data(data_path)


def test_train_claims_risk_model_outputs_metrics_and_metadata(tmp_path) -> None:
    data_path = write_synthetic_claims(tmp_path / "synthetic_claims.csv", rows=750, seed=2026)
    output_dir = tmp_path / "artifacts"
    tracking_uri = (tmp_path / "mlruns").as_uri()

    result = train_claims_risk_model(
        data_path=data_path,
        output_dir=output_dir,
        tracking_uri=tracking_uri,
        experiment_name="test-claims-risk",
        seed=2026,
        test_size=0.25,
        model_version="test",
    )

    assert result.run_id
    assert result.model_path.exists()
    assert result.model_metadata_path.exists()
    assert result.metrics_path.exists()
    assert result.feature_list_path.exists()
    assert set(result.model_metadata) >= {
        "name",
        "version",
        "framework",
        "artifact_uri",
        "training_dataset_id",
        "metrics_json",
        "lineage_json",
        "stage",
    }
    assert result.model_metadata["stage"] == "candidate"
    assert result.model_metadata["framework"] == "scikit-learn"
    assert result.model_metadata["lineage_json"]["feature_list"] == FEATURE_COLUMNS
    assert result.model_metadata["lineage_json"]["training_data_hash"]
    assert result.model_metadata["lineage_json"]["baseline_feature_count"] == 750
    assert "age_bucket" in result.model_metadata["lineage_json"]["baseline_feature_distribution"]

    overall = result.metrics["overall"]
    assert 0 <= overall["auc"] <= 1
    assert 0 <= overall["precision"] <= 1
    assert 0 <= overall["recall"] <= 1
    assert 0 <= overall["f1"] <= 1
    assert result.metrics["calibration"]
    assert result.metrics["segments"]["age_bucket"]
    assert result.metrics["segments"]["plan_type"]

    saved_metadata = json.loads(result.model_metadata_path.read_text())
    assert saved_metadata["artifact_uri"]
