# train-claims-risk

Synthetic claims-risk scoring pipeline for the `careai-platform` MLOps demo. It generates synthetic healthcare-style claims features, trains a scikit-learn classifier, logs experiment metadata to MLflow, writes control-plane-compatible model metadata, and optionally registers the candidate model with `control-plane-api`.

No real patient data, PHI, or PII is used.

## Generate Data

```bash
python -m train_claims_risk.generate_data \
  --output data/synthetic_claims.csv \
  --rows 5000
```

Generated columns:

- `age_bucket`
- `plan_type`
- `prior_claim_count`
- `recent_visit_count`
- `medication_count`
- `chronic_condition_count`
- `region_code`
- `high_risk_claim_next_30d`

All values are synthetic and deterministic when the same seed is used.

## Train Locally

```bash
python -m train_claims_risk.train \
  --data data/synthetic_claims.csv
```

Outputs are written to `artifacts/train-claims-risk/`:

- `feature-list.json`
- `metrics.json`
- `model-metadata.json`

By default, MLflow logs to local `mlruns/`. To use the local MLflow service from Docker Compose:

```bash
make local-up
export MLFLOW_TRACKING_URI=http://localhost:5000
python -m train_claims_risk.train \
  --data data/synthetic_claims.csv
```

Then open `http://localhost:5000` and look for the `claims-risk-synthetic` experiment.

For local file-backed runs without Docker, MLflow 3 requires:

```bash
MLFLOW_ALLOW_FILE_STORE=true mlflow ui --backend-store-uri mlruns
```

## Register With Control Plane

Start the control-plane API:

```bash
.venv/bin/uvicorn careai_control_plane_api.main:app --reload --port 8000
```

Train and register the model as a candidate:

```bash
python -m train_claims_risk.train \
  --data data/synthetic_claims.csv \
  --register-control-plane-url http://localhost:8000
```

If the API is unavailable, training still succeeds and prints a registration-skipped message.

## Metrics

The pipeline computes:

- AUC
- Precision
- Recall
- F1
- Calibration summary by probability bucket
- Segment metrics by `age_bucket`
- Segment metrics by `plan_type`

## Enterprise MLOps Mapping

- Synthetic data generation demonstrates reproducible data creation without PHI.
- The training data hash supports lineage and reproducibility.
- The feature list is logged as an artifact for review and downstream serving contracts.
- MLflow captures parameters, metrics, artifacts, and the trained model.
- `model-metadata.json` matches the `control-plane-api` model registration schema.
- Candidate-stage registration demonstrates governed promotion before production.
- Segment metrics provide the first hook for responsible AI and model monitoring discussions.
