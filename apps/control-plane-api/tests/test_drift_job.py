from careai_control_plane_api.drift_job import run_once, run_scheduled


def test_run_once_posts_drift_check(monkeypatch) -> None:
    captured: dict = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"drift_status": "green", "snapshot_id": "snapshot-001"}

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, url: str, json: dict):
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("careai_control_plane_api.drift_job.httpx.Client", FakeClient)

    result = run_once(
        control_plane_url="http://localhost:8000/",
        model_name="claims-risk",
        lookback_hours=12,
        minimum_events=5,
    )

    assert result == {"drift_status": "green", "snapshot_id": "snapshot-001"}
    assert captured["url"] == (
        "http://localhost:8000/monitoring/models/claims-risk/drift-check"
    )
    assert captured["json"] == {"lookback_hours": 12, "minimum_events": 5}


def test_run_scheduled_repeats_without_sleep_for_zero_interval(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_run_once(**kwargs):
        calls.append(kwargs)
        return {"drift_status": "green", "call": len(calls)}

    monkeypatch.setattr("careai_control_plane_api.drift_job.run_once", fake_run_once)

    results = run_scheduled(
        control_plane_url="http://localhost:8000",
        model_name="claims-risk",
        lookback_hours=24,
        minimum_events=1,
        interval_seconds=0,
        iterations=2,
    )

    assert results == [
        {"drift_status": "green", "call": 1},
        {"drift_status": "green", "call": 2},
    ]
    assert len(calls) == 2
