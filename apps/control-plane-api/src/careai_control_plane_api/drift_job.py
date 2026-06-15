import argparse
import json
import time
from typing import Any

import httpx


def run_once(
    *,
    control_plane_url: str,
    model_name: str,
    lookback_hours: int,
    minimum_events: int,
) -> dict[str, Any]:
    endpoint = f"{control_plane_url.rstrip('/')}/monitoring/models/{model_name}/drift-check"
    payload = {"lookback_hours": lookback_hours, "minimum_events": minimum_events}
    with httpx.Client(timeout=10.0) as client:
        response = client.post(endpoint, json=payload)
        response.raise_for_status()
        return dict(response.json())


def run_scheduled(
    *,
    control_plane_url: str,
    model_name: str,
    lookback_hours: int,
    minimum_events: int,
    interval_seconds: int,
    iterations: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index in range(iterations):
        results.append(
            run_once(
                control_plane_url=control_plane_url,
                model_name=model_name,
                lookback_hours=lookback_hours,
                minimum_events=minimum_events,
            )
        )
        if interval_seconds > 0 and index < iterations - 1:
            time.sleep(interval_seconds)
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run scheduled drift checks against the careai control plane."
    )
    parser.add_argument("--control-plane-url", default="http://localhost:8000")
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--lookback-hours", type=int, default=24)
    parser.add_argument("--minimum-events", type=int, default=1)
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=0,
        help="Delay between checks. Use 0 for a one-shot cron or Container Apps Job.",
    )
    parser.add_argument("--iterations", type=int, default=1)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    results = run_scheduled(
        control_plane_url=args.control_plane_url,
        model_name=args.model_name,
        lookback_hours=args.lookback_hours,
        minimum_events=args.minimum_events,
        interval_seconds=args.interval_seconds,
        iterations=args.iterations,
    )
    print(json.dumps(results[-1] if len(results) == 1 else results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
