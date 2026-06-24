import argparse
import json
import time

from careai_control_plane_api.api import run_due_autonomous_workflows
from careai_control_plane_api.database import Database


def run_once(
    *,
    database_url: str | None,
    limit: int,
    max_steps_per_workflow: int,
    workflow_type: str | None = None,
) -> dict[str, int | list[str]]:
    database = Database(database_url)
    database.prepare_schema()
    session_generator = database.session()
    session = next(session_generator)
    try:
        summary = run_due_autonomous_workflows(
            session,
            actor="autonomous-planner",
            workflow_type=workflow_type,
            limit=limit,
            max_steps_per_workflow=max_steps_per_workflow,
        )
        session.commit()
        return summary
    finally:
        session_generator.close()


def run_scheduled(
    *,
    database_url: str | None,
    interval_seconds: int,
    iterations: int | None,
    limit: int,
    max_steps_per_workflow: int,
    workflow_type: str | None = None,
) -> list[dict[str, int | list[str]]]:
    if interval_seconds < 0:
        raise ValueError("interval_seconds must be non-negative")

    summaries: list[dict[str, int | list[str]]] = []
    count = 0
    while iterations is None or count < iterations:
        summaries.append(
            run_once(
                database_url=database_url,
                limit=limit,
                max_steps_per_workflow=max_steps_per_workflow,
                workflow_type=workflow_type,
            )
        )
        count += 1
        if iterations is not None and count >= iterations:
            break
        if interval_seconds == 0:
            continue
        time.sleep(interval_seconds)
    return summaries


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run due autonomous careai workflows.")
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--max-steps-per-workflow", type=int, default=5)
    parser.add_argument("--workflow-type", default=None)
    parser.add_argument("--interval-seconds", type=int, default=0)
    parser.add_argument("--iterations", type=int, default=1)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    summaries = run_scheduled(
        database_url=args.database_url,
        interval_seconds=args.interval_seconds,
        iterations=args.iterations,
        limit=args.limit,
        max_steps_per_workflow=args.max_steps_per_workflow,
        workflow_type=args.workflow_type,
    )
    print(json.dumps(summaries[-1] if summaries else {}, sort_keys=True))


if __name__ == "__main__":
    main()
