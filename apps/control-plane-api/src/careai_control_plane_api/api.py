import logging
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from statistics import mean
from typing import Annotated, Any, TypeVar

from careai_common.correlation import ensure_correlation_id
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from careai_control_plane_api.models import (
    ApprovalORM,
    AuditEventORM,
    DatasetAssetORM,
    DeploymentORM,
    DriftSnapshotORM,
    EvaluationRunORM,
    ModelArtifactORM,
    ModelErrorEventORM,
    PredictionEventORM,
    PromptTemplateORM,
)
from careai_control_plane_api.monitoring import (
    calculate_drift,
    feature_distribution,
    percentile,
    slo_status,
)
from careai_control_plane_api.schemas import (
    ApprovalCreate,
    ApprovalRead,
    AuditEventCreate,
    AuditEventRead,
    DatasetAssetCreate,
    DatasetAssetRead,
    DeploymentCreate,
    DeploymentRead,
    DriftCheckRequest,
    DriftCheckResponse,
    EvaluationRunCreate,
    EvaluationRunRead,
    ModelArtifactCreate,
    ModelArtifactRead,
    ModelErrorEventCreate,
    ModelErrorEventRead,
    MonitoringSummaryResponse,
    PredictionEventCreate,
    PredictionEventRead,
    PromoteModelRequest,
    PromptTemplateCreate,
    PromptTemplateRead,
)

OrmModel = TypeVar("OrmModel")
DEFAULT_LATENCY_SLO_MS = 750
DEFAULT_ERROR_RATE_SLO = 0.02
logger = logging.getLogger(__name__)


def get_session(request: Request) -> Generator[Session, None, None]:
    yield from request.app.state.database.session()


SessionDep = Annotated[Session, Depends(get_session)]


def actor_from_request(request: Request, explicit_actor: str | None = None) -> str:
    return explicit_actor or request.headers.get("x-actor") or "demo-operator"


def write_audit_event(
    session: Session,
    *,
    actor: str,
    action: str,
    target_type: str,
    target_id: str,
    metadata: dict[str, Any] | None = None,
) -> AuditEventORM:
    metadata = metadata or {}
    event = AuditEventORM(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        correlation_id=ensure_correlation_id(),
        metadata_json=metadata,
    )
    session.add(event)
    logger.info(
        "audit event recorded",
        extra={
            "actor": actor,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "model_version": metadata.get("model_version") or metadata.get("version"),
            "prompt_version": metadata.get("prompt_version")
            or (metadata.get("version") if target_type == "prompt" else None),
        },
    )
    return event


def list_records(session: Session, model: type[OrmModel]) -> list[OrmModel]:
    return list(session.scalars(select(model).order_by(model.created_at.desc(), model.id.desc())))


def latest_model_for_name(session: Session, model_name: str) -> ModelArtifactORM | None:
    return session.scalars(
        select(ModelArtifactORM)
        .where(ModelArtifactORM.name == model_name)
        .order_by(ModelArtifactORM.created_at.desc(), ModelArtifactORM.id.desc())
        .limit(1)
    ).first()


def monitoring_events_query(model_name: str, model_version: str | None = None):
    query = select(PredictionEventORM).where(PredictionEventORM.model_name == model_name)
    if model_version:
        query = query.where(PredictionEventORM.model_version == model_version)
    return query


def monitoring_error_events_query(model_name: str, model_version: str | None = None):
    query = select(ModelErrorEventORM).where(ModelErrorEventORM.model_name == model_name)
    if model_version:
        query = query.where(ModelErrorEventORM.model_version == model_version)
    return query


def build_monitoring_dashboard_contract(
    *,
    model_name: str,
    event_count: int,
    error_count: int,
    avg_latency_ms: float | None,
    p95_latency_ms: int | None,
    high_risk_rate: float | None,
    error_rate: float,
    latency_slo_ms: int,
    error_rate_slo: float,
    current_slo_status: str,
    latest_drift_status: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": "monitoring-dashboard-v1",
        "model_name": model_name,
        "cards": [
            {"label": "Prediction Events", "value": event_count},
            {"label": "Error Events", "value": error_count},
            {"label": "Avg Latency (ms)", "value": avg_latency_ms},
            {"label": "P95 Latency (ms)", "value": p95_latency_ms},
            {"label": "High Risk Rate", "value": high_risk_rate},
            {"label": "Error Rate", "value": error_rate},
            {"label": "SLO Status", "value": current_slo_status},
            {"label": "Latest Drift", "value": latest_drift_status},
        ],
        "slos": {
            "p95_latency_ms": latency_slo_ms,
            "error_rate": error_rate_slo,
        },
        "rollback_triggers": [
            "drift_status_red",
            "p95_latency_above_slo",
            "error_rate_above_threshold",
            "data_quality_missingness_spike",
        ],
    }


router = APIRouter()


@router.post(
    "/datasets",
    response_model=DatasetAssetRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Datasets"],
    summary="Register a synthetic dataset asset",
    description="Registers a synthetic healthcare-like dataset and writes an audit event.",
)
def create_dataset(
    payload: DatasetAssetCreate,
    request: Request,
    session: SessionDep,
) -> DatasetAssetORM:
    dataset = DatasetAssetORM(**payload.model_dump())
    session.add(dataset)
    session.flush()
    write_audit_event(
        session,
        actor=actor_from_request(request),
        action="dataset.created",
        target_type="dataset",
        target_id=dataset.id,
        metadata={"name": dataset.name, "version": dataset.version},
    )
    session.commit()
    session.refresh(dataset)
    return dataset


@router.get(
    "/datasets",
    response_model=list[DatasetAssetRead],
    tags=["Datasets"],
    summary="List dataset assets",
    description="Lists registered synthetic dataset assets.",
)
def get_datasets(session: SessionDep) -> list[DatasetAssetORM]:
    return list_records(session, DatasetAssetORM)


@router.post(
    "/models",
    response_model=ModelArtifactRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Models"],
    summary="Register a model artifact",
    description="Registers model metadata, metrics, lineage, and current lifecycle stage.",
)
def create_model(
    payload: ModelArtifactCreate,
    request: Request,
    session: SessionDep,
) -> ModelArtifactORM:
    model = ModelArtifactORM(**payload.model_dump())
    session.add(model)
    session.flush()
    write_audit_event(
        session,
        actor=actor_from_request(request),
        action="model.created",
        target_type="model",
        target_id=model.id,
        metadata={"name": model.name, "version": model.version, "stage": model.stage},
    )
    session.commit()
    session.refresh(model)
    return model


@router.get(
    "/models",
    response_model=list[ModelArtifactRead],
    tags=["Models"],
    summary="List model artifacts",
    description="Lists registered model artifacts and lifecycle stages.",
)
def get_models(session: SessionDep) -> list[ModelArtifactORM]:
    return list_records(session, ModelArtifactORM)


@router.get(
    "/models/{model_id}",
    response_model=ModelArtifactRead,
    tags=["Models"],
    summary="Get a model artifact",
    description="Retrieves one model artifact by identifier.",
)
def get_model(model_id: str, session: SessionDep) -> ModelArtifactORM:
    model = session.get(ModelArtifactORM, model_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    return model


@router.post(
    "/models/{model_id}/promote",
    response_model=ModelArtifactRead,
    tags=["Models"],
    summary="Promote a model artifact",
    description="Moves a model to an allowed lifecycle stage and records an audit event.",
)
def promote_model(
    model_id: str,
    payload: PromoteModelRequest,
    request: Request,
    session: SessionDep,
) -> ModelArtifactORM:
    model = session.get(ModelArtifactORM, model_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")

    previous_stage = model.stage
    model.stage = payload.stage
    write_audit_event(
        session,
        actor=actor_from_request(request, payload.actor),
        action="model.promoted",
        target_type="model",
        target_id=model.id,
        metadata={
            "from_stage": previous_stage,
            "to_stage": payload.stage,
            "notes": payload.notes,
        },
    )
    session.commit()
    session.refresh(model)
    return model


@router.post(
    "/deployments",
    response_model=DeploymentRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Deployments"],
    summary="Create a deployment record",
    description="Tracks a model deployment target, traffic allocation, and status.",
)
def create_deployment(
    payload: DeploymentCreate,
    request: Request,
    session: SessionDep,
) -> DeploymentORM:
    deployment = DeploymentORM(**payload.model_dump())
    session.add(deployment)
    session.flush()
    write_audit_event(
        session,
        actor=actor_from_request(request),
        action="deployment.created",
        target_type="deployment",
        target_id=deployment.id,
        metadata={"model_id": deployment.model_id, "environment": deployment.environment},
    )
    session.commit()
    session.refresh(deployment)
    return deployment


@router.get(
    "/deployments",
    response_model=list[DeploymentRead],
    tags=["Deployments"],
    summary="List deployments",
    description="Lists tracked deployment records.",
)
def get_deployments(session: SessionDep) -> list[DeploymentORM]:
    return list_records(session, DeploymentORM)


@router.post(
    "/prompts",
    response_model=PromptTemplateRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Prompts"],
    summary="Register a prompt template",
    description="Stores prompt template metadata and safety notes.",
)
def create_prompt(
    payload: PromptTemplateCreate,
    request: Request,
    session: SessionDep,
) -> PromptTemplateORM:
    prompt = PromptTemplateORM(**payload.model_dump())
    session.add(prompt)
    session.flush()
    write_audit_event(
        session,
        actor=actor_from_request(request),
        action="prompt.created",
        target_type="prompt",
        target_id=prompt.id,
        metadata={"name": prompt.name, "version": prompt.version, "status": prompt.status},
    )
    session.commit()
    session.refresh(prompt)
    return prompt


@router.get(
    "/prompts",
    response_model=list[PromptTemplateRead],
    tags=["Prompts"],
    summary="List prompt templates",
    description="Lists prompt templates and governance status.",
)
def get_prompts(session: SessionDep) -> list[PromptTemplateORM]:
    return list_records(session, PromptTemplateORM)


@router.post(
    "/evaluations",
    response_model=EvaluationRunRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Evaluations"],
    summary="Create an evaluation run",
    description="Records evaluation metrics, pass/fail status, and report location.",
)
def create_evaluation(
    payload: EvaluationRunCreate,
    request: Request,
    session: SessionDep,
) -> EvaluationRunORM:
    evaluation = EvaluationRunORM(**payload.model_dump())
    session.add(evaluation)
    session.flush()
    write_audit_event(
        session,
        actor=actor_from_request(request),
        action="evaluation.created",
        target_type="evaluation",
        target_id=evaluation.id,
        metadata={
            "target_type": evaluation.target_type,
            "target_id": evaluation.target_id,
            "passed": evaluation.passed,
        },
    )
    session.commit()
    session.refresh(evaluation)
    return evaluation


@router.get(
    "/evaluations",
    response_model=list[EvaluationRunRead],
    tags=["Evaluations"],
    summary="List evaluation runs",
    description="Lists recorded model or prompt evaluation runs.",
)
def get_evaluations(session: SessionDep) -> list[EvaluationRunORM]:
    return list_records(session, EvaluationRunORM)


@router.post(
    "/approvals",
    response_model=ApprovalRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Approvals"],
    summary="Create an approval decision",
    description="Records a human approval decision and writes an audit event.",
)
def create_approval(
    payload: ApprovalCreate,
    request: Request,
    session: SessionDep,
) -> ApprovalORM:
    approval = ApprovalORM(**payload.model_dump())
    session.add(approval)
    session.flush()
    write_audit_event(
        session,
        actor=actor_from_request(request),
        action="approval.created",
        target_type="approval",
        target_id=approval.id,
        metadata={
            "target_type": approval.target_type,
            "target_id": approval.target_id,
            "decision": approval.decision,
        },
    )
    session.commit()
    session.refresh(approval)
    return approval


@router.get(
    "/approvals",
    response_model=list[ApprovalRead],
    tags=["Approvals"],
    summary="List approval decisions",
    description="Lists recorded approval decisions.",
)
def get_approvals(session: SessionDep) -> list[ApprovalORM]:
    return list_records(session, ApprovalORM)


@router.get(
    "/audit-events",
    response_model=list[AuditEventRead],
    tags=["Audit"],
    summary="List audit events",
    description="Lists audit events written by mutating control-plane operations.",
)
def get_audit_events(session: SessionDep) -> list[AuditEventORM]:
    return list_records(session, AuditEventORM)


@router.post(
    "/audit-events",
    response_model=AuditEventRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Audit"],
    summary="Create an external audit event",
    description="Stores an audit event emitted by another platform service.",
)
def create_audit_event(
    payload: AuditEventCreate,
    session: SessionDep,
) -> AuditEventORM:
    event = AuditEventORM(**payload.model_dump())
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


@router.post(
    "/monitoring/prediction-events",
    response_model=PredictionEventRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Monitoring"],
    summary="Ingest a prediction event",
    description="Stores safe synthetic prediction telemetry emitted by inference services.",
)
def create_prediction_event(
    payload: PredictionEventCreate,
    request: Request,
    session: SessionDep,
) -> PredictionEventORM:
    event = PredictionEventORM(**payload.model_dump())
    session.add(event)
    session.flush()
    write_audit_event(
        session,
        actor=actor_from_request(request, "inference-service"),
        action="prediction_event.ingested",
        target_type="prediction_event",
        target_id=event.id,
        metadata={
            "model_name": event.model_name,
            "model_version": event.model_version,
            "risk_band": event.risk_band,
            "latency_ms": event.latency_ms,
        },
    )
    session.commit()
    session.refresh(event)
    return event


@router.post(
    "/monitoring/error-events",
    response_model=ModelErrorEventRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Monitoring"],
    summary="Ingest a model error event",
    description=(
        "Stores safe operational error telemetry for SLO monitoring. Payloads must not "
        "contain raw PHI, PII, or request bodies."
    ),
)
def create_model_error_event(
    payload: ModelErrorEventCreate,
    request: Request,
    session: SessionDep,
) -> ModelErrorEventORM:
    event = ModelErrorEventORM(**payload.model_dump())
    session.add(event)
    session.flush()
    write_audit_event(
        session,
        actor=actor_from_request(request, "inference-service"),
        action="model_error_event.ingested",
        target_type="model_error_event",
        target_id=event.id,
        metadata={
            "model_name": event.model_name,
            "model_version": event.model_version,
            "error_type": event.error_type,
            "status_code": event.status_code,
            "latency_ms": event.latency_ms,
        },
    )
    session.commit()
    session.refresh(event)
    return event


@router.get(
    "/monitoring/models/{model_name}/events",
    response_model=list[PredictionEventRead],
    tags=["Monitoring"],
    summary="List prediction events for a model",
    description="Returns recent prediction telemetry for monitoring dashboards.",
)
def get_prediction_events(
    model_name: str,
    session: SessionDep,
    model_version: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[PredictionEventORM]:
    return list(
        session.scalars(
            monitoring_events_query(model_name, model_version)
            .order_by(PredictionEventORM.created_at.desc(), PredictionEventORM.id.desc())
            .limit(limit)
        )
    )


@router.get(
    "/monitoring/models/{model_name}/error-events",
    response_model=list[ModelErrorEventRead],
    tags=["Monitoring"],
    summary="List model error events",
    description="Returns recent safe operational error telemetry for SLO dashboards.",
)
def get_model_error_events(
    model_name: str,
    session: SessionDep,
    model_version: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[ModelErrorEventORM]:
    return list(
        session.scalars(
            monitoring_error_events_query(model_name, model_version)
            .order_by(ModelErrorEventORM.created_at.desc(), ModelErrorEventORM.id.desc())
            .limit(limit)
        )
    )


@router.get(
    "/monitoring/models/{model_name}/summary",
    response_model=MonitoringSummaryResponse,
    tags=["Monitoring"],
    summary="Get monitoring summary for a model",
    description="Returns dashboard-ready model monitoring metrics and latest drift state.",
)
def get_monitoring_summary(
    model_name: str,
    session: SessionDep,
    model_version: str | None = Query(default=None),
) -> MonitoringSummaryResponse:
    events = list(session.scalars(monitoring_events_query(model_name, model_version)))
    error_events = list(session.scalars(monitoring_error_events_query(model_name, model_version)))
    latency_values = [event.latency_ms for event in events] + [
        event.latency_ms for event in error_events
    ]
    scores = [event.prediction_score for event in events]
    risk_band_counts = {"low": 0, "medium": 0, "high": 0}
    for event in events:
        risk_band_counts[event.risk_band] = risk_band_counts.get(event.risk_band, 0) + 1

    latest_drift = session.scalars(
        select(DriftSnapshotORM)
        .where(DriftSnapshotORM.model_name == model_name)
        .order_by(DriftSnapshotORM.created_at.desc(), DriftSnapshotORM.id.desc())
        .limit(1)
    ).first()

    event_count = len(events)
    error_count = len(error_events)
    observed_count = event_count + error_count
    avg_latency_ms = round(mean(latency_values), 2) if latency_values else None
    avg_prediction_score = round(mean(scores), 6) if scores else None
    high_risk_rate = (
        round(risk_band_counts.get("high", 0) / event_count, 6) if event_count else None
    )
    error_rate = round(error_count / observed_count, 6) if observed_count else 0.0
    latest_drift_status = latest_drift.drift_status if latest_drift else None
    p95_latency_ms = percentile(latency_values, 0.95)
    current_slo_status = slo_status(
        event_count=observed_count,
        error_rate=error_rate,
        p95_latency_ms=p95_latency_ms,
        error_rate_slo=DEFAULT_ERROR_RATE_SLO,
        latency_slo_ms=DEFAULT_LATENCY_SLO_MS,
    )

    dashboard_contract = build_monitoring_dashboard_contract(
        model_name=model_name,
        event_count=event_count,
        error_count=error_count,
        avg_latency_ms=avg_latency_ms,
        p95_latency_ms=p95_latency_ms,
        high_risk_rate=high_risk_rate,
        error_rate=error_rate,
        latency_slo_ms=DEFAULT_LATENCY_SLO_MS,
        error_rate_slo=DEFAULT_ERROR_RATE_SLO,
        current_slo_status=current_slo_status,
        latest_drift_status=latest_drift_status,
    )

    return MonitoringSummaryResponse(
        model_name=model_name,
        event_count=event_count,
        error_count=error_count,
        model_versions=sorted(
            {event.model_version for event in events}
            | {event.model_version for event in error_events}
        ),
        avg_latency_ms=avg_latency_ms,
        p95_latency_ms=p95_latency_ms,
        avg_prediction_score=avg_prediction_score,
        risk_band_counts=risk_band_counts,
        high_risk_rate=high_risk_rate,
        error_rate=error_rate,
        latency_slo_ms=DEFAULT_LATENCY_SLO_MS,
        error_rate_slo=DEFAULT_ERROR_RATE_SLO,
        slo_status=current_slo_status,
        latest_drift_status=latest_drift_status,
        latest_drift_snapshot_id=latest_drift.id if latest_drift else None,
        dashboard_contract=dashboard_contract,
    )


@router.post(
    "/monitoring/models/{model_name}/drift-check",
    response_model=DriftCheckResponse,
    tags=["Monitoring"],
    summary="Run a deterministic drift check",
    description=(
        "Compares baseline training feature distributions to recent prediction feature "
        "distributions using PSI-style metrics."
    ),
)
def run_drift_check(
    model_name: str,
    payload: DriftCheckRequest,
    request: Request,
    session: SessionDep,
) -> DriftCheckResponse:
    if payload.red_threshold < payload.yellow_threshold:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="red_threshold must be greater than or equal to yellow_threshold",
        )

    cutoff = datetime.now(UTC) - timedelta(hours=payload.lookback_hours)
    recent_events = list(
        session.scalars(
            monitoring_events_query(model_name)
            .where(PredictionEventORM.created_at >= cutoff)
            .order_by(PredictionEventORM.created_at.desc(), PredictionEventORM.id.desc())
        )
    )
    if len(recent_events) < payload.minimum_events:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not enough recent prediction events for drift check",
        )

    latest_model = latest_model_for_name(session, model_name)
    model_version = (
        recent_events[0].model_version
        if recent_events
        else latest_model.version
        if latest_model
        else "unknown"
    )

    baseline_count = 0
    if payload.baseline_distribution_json is not None:
        baseline_distribution = payload.baseline_distribution_json
    elif payload.baseline_features_json is not None:
        baseline_count = len(payload.baseline_features_json)
        baseline_distribution = feature_distribution(payload.baseline_features_json)
    else:
        lineage = latest_model.lineage_json if latest_model else {}
        baseline_distribution = lineage.get("baseline_feature_distribution")
        baseline_count = int(lineage.get("baseline_feature_count", 0))

    if not baseline_distribution:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Baseline distribution is required for drift check",
        )

    recent_features = [event.request_features_json for event in recent_events]
    recent_distribution = feature_distribution(recent_features)
    drift_status, feature_metrics = calculate_drift(
        baseline_distribution=baseline_distribution,
        recent_distribution=recent_distribution,
        yellow_threshold=payload.yellow_threshold,
        red_threshold=payload.red_threshold,
    )
    request.app.state.observability.record_drift_status(
        model_name=model_name,
        status=drift_status,
    )
    rollback_recommended = drift_status == "red"
    dashboard_contract = {
        "schema_version": "model-drift-v1",
        "model_name": model_name,
        "model_version": model_version,
        "status": drift_status,
        "feature_drift": feature_metrics,
        "training_serving_skew": {
            "baseline_count": baseline_count,
            "recent_count": len(recent_events),
        },
        "rollback_recommended": rollback_recommended,
        "rollback_triggers": [
            "red_drift_on_any_key_feature",
            "sustained_latency_or_error_slo_breach",
            "human_review_required_for_high_business_impact",
        ],
    }

    snapshot = DriftSnapshotORM(
        model_name=model_name,
        model_version=model_version,
        drift_status=drift_status,
        metrics_json={
            "feature_metrics": feature_metrics,
            "dashboard_contract": dashboard_contract,
        },
        baseline_count=baseline_count,
        recent_count=len(recent_events),
        correlation_id=ensure_correlation_id(),
    )
    session.add(snapshot)
    session.flush()
    write_audit_event(
        session,
        actor="monitoring-job",
        action="drift_check.completed",
        target_type="model",
        target_id=model_name,
        metadata={
            "model_version": model_version,
            "drift_status": drift_status,
            "snapshot_id": snapshot.id,
            "rollback_recommended": rollback_recommended,
        },
    )
    session.commit()
    session.refresh(snapshot)

    return DriftCheckResponse(
        model_name=model_name,
        model_version=model_version,
        drift_status=drift_status,
        baseline_count=baseline_count,
        recent_count=len(recent_events),
        feature_metrics=feature_metrics,
        rollback_recommended=rollback_recommended,
        snapshot_id=snapshot.id,
        created_at=snapshot.created_at,
        dashboard_contract=dashboard_contract,
    )
