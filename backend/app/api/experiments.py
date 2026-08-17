from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import client_ip, get_current_user
from app.models import Experiment, User
from app.schemas import ExperimentCreate, ExperimentPublic, WinnerRequest
from app.services.experiment_service import (
    create_experiment,
    declare_winner,
    experiment_metrics,
    list_experiments,
    require_experiment,
    start_experiment,
    stop_experiment,
)

router = APIRouter(tags=["experiments"])


def _public(db: Session, row: Experiment, with_metrics: bool = False) -> ExperimentPublic:
    payload = ExperimentPublic.model_validate(row)
    if with_metrics:
        payload = payload.model_copy(update={"metrics": experiment_metrics(db, row)})
    return payload


@router.get("/brands/{brand_id}/experiments", response_model=list[ExperimentPublic])
def get_experiments(
    brand_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ExperimentPublic]:
    return [_public(db, row) for row in list_experiments(db, user, brand_id)]


@router.post(
    "/brands/{brand_id}/experiments",
    response_model=ExperimentPublic,
    status_code=status.HTTP_201_CREATED,
)
def post_experiment(
    brand_id: UUID,
    payload: ExperimentCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExperimentPublic:
    return _public(
        db, create_experiment(db, user, brand_id, payload, ip=client_ip(request))
    )


@router.get("/experiments/{experiment_id}", response_model=ExperimentPublic)
def get_experiment(
    experiment_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExperimentPublic:
    row = require_experiment(db, user, experiment_id)
    return _public(db, row, with_metrics=True)


@router.post("/experiments/{experiment_id}/start", response_model=ExperimentPublic)
def post_start(
    experiment_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExperimentPublic:
    row = start_experiment(db, user, experiment_id, ip=client_ip(request))
    return _public(db, row, with_metrics=True)


@router.post("/experiments/{experiment_id}/stop", response_model=ExperimentPublic)
def post_stop(
    experiment_id: UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExperimentPublic:
    row = stop_experiment(db, user, experiment_id, ip=client_ip(request))
    return _public(db, row, with_metrics=True)


@router.post("/experiments/{experiment_id}/winner", response_model=ExperimentPublic)
def post_winner(
    experiment_id: UUID,
    payload: WinnerRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExperimentPublic:
    row = declare_winner(db, user, experiment_id, payload, ip=client_ip(request))
    return _public(db, row, with_metrics=True)
