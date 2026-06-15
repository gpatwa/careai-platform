import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from train_claims_risk.features import AGE_BUCKETS, LABEL_COLUMN, PLAN_TYPES, REGION_CODES

DEFAULT_SEED = 20260614


def generate_synthetic_claims(rows: int, seed: int = DEFAULT_SEED) -> pd.DataFrame:
    """Generate deterministic synthetic healthcare-like claims data without PHI."""

    if rows <= 0:
        raise ValueError("rows must be greater than zero")

    rng = np.random.default_rng(seed)
    age_bucket = rng.choice(AGE_BUCKETS, size=rows, p=[0.25, 0.27, 0.28, 0.20])
    plan_type = rng.choice(PLAN_TYPES, size=rows, p=[0.22, 0.30, 0.24, 0.14, 0.10])
    region_code = rng.choice(REGION_CODES, size=rows)

    age_factor = (
        pd.Series(age_bucket)
        .map({"18-34": 0.0, "35-49": 0.35, "50-64": 0.75, "65+": 1.1})
        .to_numpy()
    )
    plan_factor = pd.Series(plan_type).map(
        {
            "bronze": 0.35,
            "silver": 0.15,
            "gold": 0.0,
            "platinum": -0.10,
            "medicare_advantage": 0.45,
        }
    ).to_numpy()

    chronic_condition_count = np.clip(rng.poisson(0.7 + age_factor * 0.9), 0, 8)
    prior_claim_count = np.clip(rng.poisson(1.6 + chronic_condition_count * 0.8), 0, 24)
    recent_visit_count = np.clip(rng.poisson(0.8 + chronic_condition_count * 0.55), 0, 15)
    medication_count = np.clip(rng.poisson(1.1 + chronic_condition_count * 1.15), 0, 18)

    risk_logit = (
        -3.1
        + age_factor * 0.55
        + plan_factor
        + prior_claim_count * 0.08
        + recent_visit_count * 0.16
        + medication_count * 0.07
        + chronic_condition_count * 0.48
        + rng.normal(0, 0.35, size=rows)
    )
    probability = 1 / (1 + np.exp(-risk_logit))
    label = rng.binomial(1, probability)

    return pd.DataFrame(
        {
            "age_bucket": age_bucket,
            "plan_type": plan_type,
            "prior_claim_count": prior_claim_count.astype(int),
            "recent_visit_count": recent_visit_count.astype(int),
            "medication_count": medication_count.astype(int),
            "chronic_condition_count": chronic_condition_count.astype(int),
            "region_code": region_code,
            LABEL_COLUMN: label.astype(int),
        }
    )


def write_synthetic_claims(output: str | Path, rows: int, seed: int = DEFAULT_SEED) -> Path:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = generate_synthetic_claims(rows=rows, seed=seed)
    data.to_csv(output_path, index=False)
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate synthetic claims-risk training data.")
    parser.add_argument("--output", required=True, help="Output CSV path.")
    parser.add_argument(
        "--rows",
        type=int,
        default=5000,
        help="Number of synthetic rows to generate.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help="Deterministic generation seed.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = write_synthetic_claims(args.output, rows=args.rows, seed=args.seed)
    print(f"Wrote {args.rows} synthetic rows to {output_path}")


if __name__ == "__main__":
    main()
