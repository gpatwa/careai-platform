import argparse
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import joblib
import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from train_claims_risk.features import (
    CATEGORICAL_FEATURES,
    FEATURE_COLUMNS,
    LABEL_COLUMN,
    NUMERIC_FEATURES,
)

DEFAULT_EXPERIMENT_NAME = "claims-risk-synthetic"
DEFAULT_OUTPUT_DIR = "artifacts/train-claims-risk"
DEFAULT_CODE_VERSION = "local-demo"


@dataclass(frozen=True)
class TrainResult:
    run_id: str
    model_path: Path
    model_metadata_path: Path
    metrics_path: Path
    feature_list_path: Path
    model_metadata: dict[str, Any]
    metrics: dict[str, Any]
    registered_model_id: str | None


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_training_data(data_path: str | Path) -> pd.DataFrame:
    data = pd.read_csv(data_path)
    missing_columns = sorted(set(FEATURE_COLUMNS + [LABEL_COLUMN]) - set(data.columns))
    if missing_columns:
        raise ValueError(f"Training data is missing required columns: {missing_columns}")
    return data


def build_model(random_state: int) -> Pipeline:
    preprocessor = ColumnTransformer(
        transformers=[
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                CATEGORICAL_FEATURES,
            ),
            ("numeric", StandardScaler(), NUMERIC_FEATURES),
        ]
    )
    classifier = GradientBoostingClassifier(random_state=random_state)
    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("classifier", classifier),
        ]
    )


def binary_metrics(
    y_true: pd.Series | np.ndarray,
    probabilities: np.ndarray,
) -> dict[str, float | None]:
    predictions = (probabilities >= 0.5).astype(int)
    auc = None
    if len(set(y_true)) == 2:
        auc = float(roc_auc_score(y_true, probabilities))
    return {
        "auc": auc,
        "precision": float(precision_score(y_true, predictions, zero_division=0)),
        "recall": float(recall_score(y_true, predictions, zero_division=0)),
        "f1": float(f1_score(y_true, predictions, zero_division=0)),
    }


def calibration_summary(
    y_true: pd.Series,
    probabilities: np.ndarray,
    bins: int = 5,
) -> list[dict[str, Any]]:
    frame = pd.DataFrame({"label": y_true.to_numpy(), "probability": probabilities})
    frame["bucket"] = pd.cut(
        frame["probability"],
        bins=np.linspace(0, 1, bins + 1),
        include_lowest=True,
    )
    summary = (
        frame.groupby("bucket", observed=False)
        .agg(
            count=("label", "size"),
            avg_prediction=("probability", "mean"),
            observed_rate=("label", "mean"),
        )
        .reset_index()
    )
    return [
        {
            "bucket": str(row.bucket),
            "count": int(row.count),
            "avg_prediction": None if pd.isna(row.avg_prediction) else float(row.avg_prediction),
            "observed_rate": None if pd.isna(row.observed_rate) else float(row.observed_rate),
        }
        for row in summary.itertuples(index=False)
    ]


def segment_metrics(
    test_data: pd.DataFrame,
    y_true: pd.Series,
    probabilities: np.ndarray,
    segment_column: str,
) -> dict[str, dict[str, float | int | None]]:
    result: dict[str, dict[str, float | int | None]] = {}
    for segment_value in sorted(test_data[segment_column].astype(str).unique()):
        mask = test_data[segment_column].astype(str) == segment_value
        metrics = binary_metrics(y_true[mask], probabilities[mask])
        result[segment_value] = {
            "count": int(mask.sum()),
            "positive_rate": float(y_true[mask].mean()),
            **metrics,
        }
    return result


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


NUMERIC_FEATURE_BINS: dict[str, list[tuple[int, int | None]]] = {
    "prior_claim_count": [(0, 0), (1, 2), (3, 5), (6, 10), (11, 25), (26, None)],
    "recent_visit_count": [(0, 0), (1, 1), (2, 3), (4, 6), (7, 12), (13, None)],
    "medication_count": [(0, 0), (1, 2), (3, 5), (6, 10), (11, 20), (21, None)],
    "chronic_condition_count": [(0, 0), (1, 1), (2, 2), (3, 4), (5, 7), (8, None)],
}


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


def feature_distribution(data: pd.DataFrame) -> dict[str, dict[str, float]]:
    distributions: dict[str, dict[str, float]] = {}
    for column in FEATURE_COLUMNS:
        if column in NUMERIC_FEATURE_BINS:
            bins = NUMERIC_FEATURE_BINS[column]
            values = data[column].map(lambda value, bins=bins: bucket_numeric_value(value, bins))
        else:
            values = data[column].astype(str)
        counts = values.value_counts(normalize=True).sort_index()
        distributions[column] = {
            str(value): float(frequency) for value, frequency in counts.items()
        }
    return distributions


def write_json(path: str | Path, payload: dict[str, Any] | list[Any]) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(json_safe(payload), indent=2, sort_keys=True) + "\n")
    return output_path


def resolve_tracking_uri(tracking_uri: str | None) -> str:
    if tracking_uri:
        if tracking_uri.startswith("file:") or "://" not in tracking_uri:
            os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
        return tracking_uri
    if os.getenv("MLFLOW_TRACKING_URI"):
        return os.environ["MLFLOW_TRACKING_URI"]
    os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
    return Path("mlruns").resolve().as_uri()


def register_model_with_control_plane(
    control_plane_url: str | None,
    model_metadata: dict[str, Any],
) -> str | None:
    if not control_plane_url:
        return None

    endpoint = control_plane_url.rstrip("/") + "/models"
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.post(
                endpoint,
                json=model_metadata,
                headers={"x-actor": "train-claims-risk-pipeline"},
            )
            response.raise_for_status()
            return str(response.json().get("id"))
    except httpx.HTTPError as exc:
        print(f"Control-plane registration skipped: {exc}")
        return None


def train_claims_risk_model(
    *,
    data_path: str | Path,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    register_control_plane_url: str | None = None,
    tracking_uri: str | None = None,
    experiment_name: str = DEFAULT_EXPERIMENT_NAME,
    seed: int = 20260614,
    test_size: float = 0.2,
    model_version: str = "0.1.0",
    code_version: str = DEFAULT_CODE_VERSION,
) -> TrainResult:
    data = load_training_data(data_path)
    training_data_hash = file_sha256(data_path)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    x_train, x_test, y_train, y_test = train_test_split(
        data[FEATURE_COLUMNS],
        data[LABEL_COLUMN],
        test_size=test_size,
        random_state=seed,
        stratify=data[LABEL_COLUMN],
    )

    model = build_model(random_state=seed)
    model.fit(x_train, y_train)
    probabilities = model.predict_proba(x_test)[:, 1]

    overall_metrics = binary_metrics(y_test, probabilities)
    metrics: dict[str, Any] = {
        "overall": overall_metrics,
        "calibration": calibration_summary(y_test, probabilities),
        "segments": {
            "age_bucket": segment_metrics(x_test, y_test, probabilities, "age_bucket"),
            "plan_type": segment_metrics(x_test, y_test, probabilities, "plan_type"),
        },
    }

    mlflow.set_tracking_uri(resolve_tracking_uri(tracking_uri))
    mlflow.set_experiment(experiment_name)

    with mlflow.start_run(run_name="claims-risk-gradient-boosting") as run:
        run_id = run.info.run_id
        mlflow.log_params(
            {
                "model_type": "GradientBoostingClassifier",
                "seed": seed,
                "test_size": test_size,
                "rows": len(data),
                "positive_rate": float(data[LABEL_COLUMN].mean()),
                "code_version": code_version,
                "training_data_hash": training_data_hash,
            }
        )
        for metric_name, metric_value in overall_metrics.items():
            if metric_value is not None:
                mlflow.log_metric(metric_name, metric_value)

        feature_payload = {
            "label": LABEL_COLUMN,
            "features": FEATURE_COLUMNS,
            "categorical_features": CATEGORICAL_FEATURES,
            "numeric_features": NUMERIC_FEATURES,
        }
        feature_list_path = write_json(output_path / "feature-list.json", feature_payload)
        metrics_path = write_json(output_path / "metrics.json", metrics)
        model_path = output_path / "model.joblib"
        joblib.dump(model, model_path)
        model_info = mlflow.sklearn.log_model(model, name="model")
        model_artifact_uri = model_info.model_uri
        mlflow.log_artifact(str(model_path), artifact_path="model-export")

        model_metadata = {
            "name": "claims-risk",
            "version": model_version,
            "framework": "scikit-learn",
            "artifact_uri": model_artifact_uri,
            "training_dataset_id": f"synthetic-claims-{training_data_hash[:12]}",
            "metrics_json": metrics,
            "lineage_json": {
                "training_data_hash": training_data_hash,
                "feature_list": FEATURE_COLUMNS,
                "baseline_feature_distribution": feature_distribution(data[FEATURE_COLUMNS]),
                "baseline_feature_count": len(data),
                "row_count": len(data),
                "test_size": test_size,
                "seed": seed,
                "code_version": code_version,
                "mlflow_run_id": run_id,
                "mlflow_experiment_name": experiment_name,
            },
            "stage": "candidate",
        }
        model_metadata_path = write_json(output_path / "model-metadata.json", model_metadata)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            temp_feature_path = write_json(tmpdir_path / "feature-list.json", feature_payload)
            temp_metadata_path = write_json(tmpdir_path / "model-metadata.json", model_metadata)
            temp_metrics_path = write_json(tmpdir_path / "metrics.json", metrics)
            mlflow.log_artifact(str(temp_feature_path), artifact_path="metadata")
            mlflow.log_artifact(str(temp_metadata_path), artifact_path="metadata")
            mlflow.log_artifact(str(temp_metrics_path), artifact_path="metadata")

    registered_model_id = register_model_with_control_plane(
        register_control_plane_url,
        model_metadata,
    )

    return TrainResult(
        run_id=run_id,
        model_path=model_path,
        model_metadata_path=model_metadata_path,
        metrics_path=metrics_path,
        feature_list_path=feature_list_path,
        model_metadata=model_metadata,
        metrics=metrics,
        registered_model_id=registered_model_id,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train the synthetic claims-risk model.")
    parser.add_argument("--data", required=True, help="Synthetic claims CSV.")
    parser.add_argument(
        "--register-control-plane-url",
        default=None,
        help="Optional control-plane API base URL, for example http://localhost:8000.",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="Output artifact directory.",
    )
    parser.add_argument("--tracking-uri", default=None, help="Optional MLflow tracking URI.")
    parser.add_argument("--experiment-name", default=DEFAULT_EXPERIMENT_NAME)
    parser.add_argument("--seed", type=int, default=20260614)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--model-version", default="0.1.0")
    parser.add_argument("--code-version", default=DEFAULT_CODE_VERSION)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = train_claims_risk_model(
        data_path=args.data,
        output_dir=args.output_dir,
        register_control_plane_url=args.register_control_plane_url,
        tracking_uri=args.tracking_uri,
        experiment_name=args.experiment_name,
        seed=args.seed,
        test_size=args.test_size,
        model_version=args.model_version,
        code_version=args.code_version,
    )
    print(f"MLflow run: {result.run_id}")
    print(f"Model metadata: {result.model_metadata_path}")
    if result.registered_model_id:
        print(f"Control-plane model id: {result.registered_model_id}")


if __name__ == "__main__":
    main()
