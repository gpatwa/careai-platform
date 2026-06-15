from collections.abc import Generator
from typing import Annotated, Any, TypeVar

from careai_common.correlation import ensure_correlation_id
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from careai_control_plane_api.models import (
    ApprovalORM,
    AuditEventORM,
    DatasetAssetORM,
    DeploymentORM,
    EvaluationRunORM,
    ModelArtifactORM,
    PromptTemplateORM,
)
from careai_control_plane_api.schemas import (
    ApprovalCreate,
    ApprovalRead,
    AuditEventRead,
    DatasetAssetCreate,
    DatasetAssetRead,
    DeploymentCreate,
    DeploymentRead,
    EvaluationRunCreate,
    EvaluationRunRead,
    ModelArtifactCreate,
    ModelArtifactRead,
    PromoteModelRequest,
    PromptTemplateCreate,
    PromptTemplateRead,
)

OrmModel = TypeVar("OrmModel")


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
    event = AuditEventORM(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        correlation_id=ensure_correlation_id(),
        metadata_json=metadata or {},
    )
    session.add(event)
    return event


def list_records(session: Session, model: type[OrmModel]) -> list[OrmModel]:
    return list(session.scalars(select(model).order_by(model.created_at.desc(), model.id.desc())))


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
