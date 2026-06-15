import logging
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from statistics import mean
from typing import Annotated, Any, TypeVar

from careai_common.correlation import ensure_correlation_id
from careai_common.events import EventEnvelope, build_event
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
    ModelCardORM,
    ModelErrorEventORM,
    PredictionEventORM,
    PromptCardORM,
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
    CanaryDeploymentRequest,
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
    ModelCardCreate,
    ModelCardRead,
    ModelCardUpdate,
    ModelErrorEventCreate,
    ModelErrorEventRead,
    MonitoringSummaryResponse,
    PredictionEventCreate,
    PredictionEventRead,
    PromoteModelRequest,
    PromptCardCreate,
    PromptCardRead,
    PromptCardUpdate,
    PromptTemplateCreate,
    PromptTemplateRead,
    RollbackDeploymentRequest,
    SetTrafficRequest,
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


def publish_event_safely(request: Request, event: EventEnvelope) -> bool:
    try:
        return request.app.state.event_publisher.publish(event)
    except Exception as exc:
        logger.warning(
            "event publish failed",
            extra={"event_type": event.event_type, "error": str(exc)},
        )
        return False


def list_records(session: Session, model: type[OrmModel]) -> list[OrmModel]:
    return list(session.scalars(select(model).order_by(model.created_at.desc(), model.id.desc())))


def latest_model_for_name(session: Session, model_name: str) -> ModelArtifactORM | None:
    return session.scalars(
        select(ModelArtifactORM)
        .where(ModelArtifactORM.name == model_name)
        .order_by(ModelArtifactORM.created_at.desc(), ModelArtifactORM.id.desc())
        .limit(1)
    ).first()


def model_card_for(session: Session, model_id: str) -> ModelCardORM | None:
    return session.scalars(
        select(ModelCardORM)
        .where(ModelCardORM.model_id == model_id)
        .order_by(
            ModelCardORM.updated_at.desc(), ModelCardORM.created_at.desc(), ModelCardORM.id.desc()
        )
        .limit(1)
    ).first()


def prompt_card_for(session: Session, prompt_id: str) -> PromptCardORM | None:
    return session.scalars(
        select(PromptCardORM)
        .where(PromptCardORM.prompt_id == prompt_id)
        .order_by(
            PromptCardORM.updated_at.desc(),
            PromptCardORM.created_at.desc(),
            PromptCardORM.id.desc(),
        )
        .limit(1)
    ).first()


def has_approved_human_approval(session: Session, target_type: str, target_id: str) -> bool:
    return (
        session.scalars(
            select(ApprovalORM)
            .where(
                ApprovalORM.target_type == target_type,
                ApprovalORM.target_id == target_id,
                ApprovalORM.decision == "approved",
            )
            .limit(1)
        ).first()
        is not None
    )


def is_model_production_ready(session: Session, model_id: str) -> tuple[bool, list[str]]:
    missing: list[str] = []
    card = model_card_for(session, model_id)
    if card is None:
        missing.append("approved_model_card")
    elif card.approval_status != "approved":
        missing.append("approved_model_card")

    if not has_approved_human_approval(session, "model", model_id):
        missing.append("approved_model_governance_decision")

    return not missing, missing


def is_prompt_production_ready(session: Session, prompt: PromptTemplateORM) -> bool:
    card = prompt_card_for(session, prompt.id)
    return prompt.status == "approved" and card is not None and card.approval_status == "approved"


def validate_traffic_split(split: dict[str, int]) -> dict[str, int]:
    if not split:
        raise HTTPException(
            status_code=422,
            detail="traffic_split_json must include at least one model id",
        )
    normalized: dict[str, int] = {}
    for model_id, percent in split.items():
        if not model_id:
            raise HTTPException(
                status_code=422,
                detail="traffic_split_json model ids must be non-empty",
            )
        if percent < 0 or percent > 100:
            raise HTTPException(
                status_code=422,
                detail="traffic percentages must be between 0 and 100",
            )
        normalized[model_id] = int(percent)

    if sum(normalized.values()) != 100:
        raise HTTPException(
            status_code=422,
            detail="traffic_split_json percentages must sum to 100",
        )
    return normalized


def deployment_or_404(session: Session, deployment_id: str) -> DeploymentORM:
    deployment = session.get(DeploymentORM, deployment_id)
    if deployment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found")
    return deployment


def rollback_recommended_for(session: Session, deployment: DeploymentORM) -> bool:
    model = session.get(ModelArtifactORM, deployment.champion_model_id)
    if model is None:
        return False

    events = list(session.scalars(monitoring_events_query(model.name, model.version)))
    error_events = list(session.scalars(monitoring_error_events_query(model.name, model.version)))
    observed_count = len(events) + len(error_events)
    error_rate = round(len(error_events) / observed_count, 6) if observed_count else 0.0
    p95_latency_ms = percentile(
        [event.latency_ms for event in events] + [event.latency_ms for event in error_events],
        0.95,
    )
    current_slo_status = slo_status(
        event_count=observed_count,
        error_rate=error_rate,
        p95_latency_ms=p95_latency_ms,
        error_rate_slo=DEFAULT_ERROR_RATE_SLO,
        latency_slo_ms=DEFAULT_LATENCY_SLO_MS,
    )
    latest_drift = session.scalars(
        select(DriftSnapshotORM)
        .where(
            DriftSnapshotORM.model_name == model.name,
            DriftSnapshotORM.model_version == model.version,
        )
        .order_by(DriftSnapshotORM.created_at.desc(), DriftSnapshotORM.id.desc())
        .limit(1)
    ).first()
    return current_slo_status == "breached" or (
        latest_drift is not None and latest_drift.drift_status == "red"
    )


def refresh_deployment_health(session: Session, deployment: DeploymentORM) -> None:
    if deployment.status in {"rolled_back", "inactive"}:
        return
    if rollback_recommended_for(session, deployment):
        deployment.health_status = "rollback_recommended"


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
    "/model-cards",
    response_model=ModelCardRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Governance"],
    summary="Create a model card",
    description="Creates a responsible AI model card for a registered synthetic model.",
)
def create_model_card(
    payload: ModelCardCreate,
    request: Request,
    session: SessionDep,
) -> ModelCardORM:
    if session.get(ModelArtifactORM, payload.model_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    if model_card_for(session, payload.model_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Model card already exists; use PUT to update it",
        )

    card = ModelCardORM(**payload.model_dump())
    session.add(card)
    session.flush()
    write_audit_event(
        session,
        actor=actor_from_request(request),
        action="model_card.created",
        target_type="model",
        target_id=card.model_id,
        metadata={"card_id": card.id, "approval_status": card.approval_status},
    )
    session.commit()
    session.refresh(card)
    return card


@router.get(
    "/model-cards",
    response_model=list[ModelCardRead],
    tags=["Governance"],
    summary="List model cards",
    description="Lists responsible AI model cards.",
)
def get_model_cards(session: SessionDep) -> list[ModelCardORM]:
    return list_records(session, ModelCardORM)


@router.get(
    "/model-cards/{model_id}",
    response_model=ModelCardRead,
    tags=["Governance"],
    summary="Get a model card",
    description="Retrieves the model card for a registered synthetic model.",
)
def get_model_card(model_id: str, session: SessionDep) -> ModelCardORM:
    card = model_card_for(session, model_id)
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model card not found")
    return card


@router.put(
    "/model-cards/{model_id}",
    response_model=ModelCardRead,
    tags=["Governance"],
    summary="Update a model card",
    description="Updates responsible AI model card content and approval status.",
)
def update_model_card(
    model_id: str,
    payload: ModelCardUpdate,
    request: Request,
    session: SessionDep,
) -> ModelCardORM:
    card = model_card_for(session, model_id)
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model card not found")

    for field_name, value in payload.model_dump().items():
        setattr(card, field_name, value)
    write_audit_event(
        session,
        actor=actor_from_request(request),
        action="model_card.updated",
        target_type="model",
        target_id=model_id,
        metadata={"card_id": card.id, "approval_status": card.approval_status},
    )
    session.commit()
    session.refresh(card)
    return card


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
    if payload.stage == "production":
        production_ready, missing_controls = is_model_production_ready(session, model.id)
        if not production_ready:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Model cannot move to production until governance gates pass.",
                    "missing_controls": missing_controls,
                },
            )

    model.stage = payload.stage
    correlation_id = ensure_correlation_id()
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
    publish_event_safely(
        request,
        build_event(
            event_type="model.promotion_requested",
            source="control-plane-api",
            subject=f"model/{model.id}",
            correlation_id=correlation_id,
            payload={
                "model_id": model.id,
                "model_name": model.name,
                "model_version": model.version,
                "from_stage": previous_stage,
                "to_stage": payload.stage,
                "requested_by": actor_from_request(request, payload.actor),
                "notes": payload.notes,
            },
        ),
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
    payload_data = payload.model_dump()
    champion_model_id = payload.champion_model_id or payload.model_id
    payload_data["champion_model_id"] = champion_model_id
    payload_data["rollback_model_id"] = payload.rollback_model_id or champion_model_id
    if not payload.traffic_split_json:
        payload_data["traffic_split_json"] = {champion_model_id: payload.traffic_percent}
    deployment = DeploymentORM(**payload_data)
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
    deployments = list_records(session, DeploymentORM)
    for deployment in deployments:
        refresh_deployment_health(session, deployment)
    session.commit()
    return deployments


@router.post(
    "/deployments/{deployment_id}/canary",
    response_model=DeploymentRead,
    tags=["Deployments"],
    summary="Start a canary deployment",
    description="Adds a challenger model and sends a controlled percentage of traffic to it.",
)
def start_canary(
    deployment_id: str,
    payload: CanaryDeploymentRequest,
    request: Request,
    session: SessionDep,
) -> DeploymentORM:
    deployment = deployment_or_404(session, deployment_id)
    split = validate_traffic_split(
        {
            deployment.champion_model_id: 100 - payload.challenger_percent,
            payload.challenger_model_id: payload.challenger_percent,
        }
    )
    deployment.challenger_model_id = payload.challenger_model_id
    deployment.traffic_split_json = split
    deployment.traffic_percent = 100
    deployment.deployment_type = "canary"
    deployment.status = "active"
    deployment.health_status = "canary"
    if deployment.rollback_model_id is None:
        deployment.rollback_model_id = deployment.champion_model_id
    write_audit_event(
        session,
        actor=actor_from_request(request, payload.actor),
        action="deployment.canary_started",
        target_type="deployment",
        target_id=deployment.id,
        metadata={
            "champion_model_id": deployment.champion_model_id,
            "challenger_model_id": deployment.challenger_model_id,
            "traffic_split_json": split,
            "notes": payload.notes,
        },
    )
    session.commit()
    session.refresh(deployment)
    return deployment


@router.post(
    "/deployments/{deployment_id}/set-traffic",
    response_model=DeploymentRead,
    tags=["Deployments"],
    summary="Set deployment traffic split",
    description="Updates champion/challenger traffic percentages for a deployment.",
)
def set_deployment_traffic(
    deployment_id: str,
    payload: SetTrafficRequest,
    request: Request,
    session: SessionDep,
) -> DeploymentORM:
    deployment = deployment_or_404(session, deployment_id)
    split = validate_traffic_split(payload.traffic_split_json)
    allowed_ids = {deployment.champion_model_id}
    if deployment.challenger_model_id:
        allowed_ids.add(deployment.challenger_model_id)
    if deployment.rollback_model_id:
        allowed_ids.add(deployment.rollback_model_id)
    unknown_ids = sorted(set(split) - allowed_ids)
    if unknown_ids:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Traffic split includes unknown deployment model ids",
                "ids": unknown_ids,
            },
        )

    deployment.traffic_split_json = split
    deployment.traffic_percent = 100
    deployment.health_status = "healthy" if not deployment.challenger_model_id else "canary"
    refresh_deployment_health(session, deployment)
    write_audit_event(
        session,
        actor=actor_from_request(request, payload.actor),
        action="deployment.traffic_updated",
        target_type="deployment",
        target_id=deployment.id,
        metadata={"traffic_split_json": split, "notes": payload.notes},
    )
    session.commit()
    session.refresh(deployment)
    return deployment


@router.post(
    "/deployments/{deployment_id}/rollback",
    response_model=DeploymentRead,
    tags=["Deployments"],
    summary="Rollback a deployment",
    description="Routes all traffic to the rollback model and clears challenger traffic.",
)
def rollback_deployment(
    deployment_id: str,
    payload: RollbackDeploymentRequest,
    request: Request,
    session: SessionDep,
) -> DeploymentORM:
    deployment = deployment_or_404(session, deployment_id)
    rollback_model_id = deployment.rollback_model_id or deployment.champion_model_id
    previous_champion_id = deployment.champion_model_id
    deployment.model_id = rollback_model_id
    deployment.champion_model_id = rollback_model_id
    deployment.challenger_model_id = None
    deployment.traffic_split_json = {rollback_model_id: 100}
    deployment.traffic_percent = 100
    deployment.status = "active"
    deployment.deployment_type = "rollback"
    deployment.health_status = "rolled_back"
    write_audit_event(
        session,
        actor=actor_from_request(request, payload.actor),
        action="deployment.rolled_back",
        target_type="deployment",
        target_id=deployment.id,
        metadata={
            "previous_champion_model_id": previous_champion_id,
            "rollback_model_id": rollback_model_id,
            "notes": payload.notes,
        },
    )
    session.commit()
    session.refresh(deployment)
    return deployment


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


@router.post(
    "/prompt-cards",
    response_model=PromptCardRead,
    status_code=status.HTTP_201_CREATED,
    tags=["Governance"],
    summary="Create a prompt card",
    description="Creates a responsible AI prompt card for a registered prompt template.",
)
def create_prompt_card(
    payload: PromptCardCreate,
    request: Request,
    session: SessionDep,
) -> PromptCardORM:
    if session.get(PromptTemplateORM, payload.prompt_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found")
    if prompt_card_for(session, payload.prompt_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Prompt card already exists; use PUT to update it",
        )

    card = PromptCardORM(**payload.model_dump())
    session.add(card)
    session.flush()
    write_audit_event(
        session,
        actor=actor_from_request(request),
        action="prompt_card.created",
        target_type="prompt",
        target_id=card.prompt_id,
        metadata={"card_id": card.id, "approval_status": card.approval_status},
    )
    session.commit()
    session.refresh(card)
    return card


@router.get(
    "/prompt-cards",
    response_model=list[PromptCardRead],
    tags=["Governance"],
    summary="List prompt cards",
    description="Lists responsible AI prompt cards.",
)
def get_prompt_cards(session: SessionDep) -> list[PromptCardORM]:
    return list_records(session, PromptCardORM)


@router.get(
    "/prompt-cards/{prompt_id}",
    response_model=PromptCardRead,
    tags=["Governance"],
    summary="Get a prompt card",
    description="Retrieves the prompt card for a registered prompt template.",
)
def get_prompt_card(prompt_id: str, session: SessionDep) -> PromptCardORM:
    card = prompt_card_for(session, prompt_id)
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt card not found")
    return card


@router.put(
    "/prompt-cards/{prompt_id}",
    response_model=PromptCardRead,
    tags=["Governance"],
    summary="Update a prompt card",
    description="Updates responsible AI prompt card content and approval status.",
)
def update_prompt_card(
    prompt_id: str,
    payload: PromptCardUpdate,
    request: Request,
    session: SessionDep,
) -> PromptCardORM:
    card = prompt_card_for(session, prompt_id)
    if card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt card not found")

    for field_name, value in payload.model_dump().items():
        setattr(card, field_name, value)
    write_audit_event(
        session,
        actor=actor_from_request(request),
        action="prompt_card.updated",
        target_type="prompt",
        target_id=prompt_id,
        metadata={"card_id": card.id, "approval_status": card.approval_status},
    )
    session.commit()
    session.refresh(card)
    return card


@router.get(
    "/prompts",
    response_model=list[PromptTemplateRead],
    tags=["Prompts"],
    summary="List prompt templates",
    description="Lists prompt templates and governance status.",
)
def get_prompts(
    session: SessionDep,
    production_ready_only: bool = Query(default=False),
) -> list[PromptTemplateORM]:
    prompts = list_records(session, PromptTemplateORM)
    if production_ready_only:
        return [prompt for prompt in prompts if is_prompt_production_ready(session, prompt)]
    return prompts


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
    request: Request,
    session: SessionDep,
) -> AuditEventORM:
    event = AuditEventORM(**payload.model_dump())
    session.add(event)
    publish_event_safely(
        request,
        build_event(
            event_type="audit.created",
            source="control-plane-api",
            subject=f"{event.target_type}/{event.target_id}",
            correlation_id=event.correlation_id,
            payload={
                "actor": event.actor,
                "action": event.action,
                "target_type": event.target_type,
                "target_id": event.target_id,
                "metadata_json": event.metadata_json,
            },
        ),
    )
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
            status_code=422,
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
    publish_event_safely(
        request,
        build_event(
            event_type="model.drift_detected",
            source="control-plane-api",
            subject=f"model/{model_name}",
            correlation_id=snapshot.correlation_id,
            payload={
                "model_name": model_name,
                "model_version": model_version,
                "drift_status": drift_status,
                "snapshot_id": snapshot.id,
                "rollback_recommended": rollback_recommended,
                "metrics_json": {
                    "feature_metrics": feature_metrics,
                    "dashboard_contract": dashboard_contract,
                },
            },
        ),
    )
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
