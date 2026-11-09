"""设计规则落实检测接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..errors import AppError
from ..models import DesignRuleCoverageRun
from ..schemas import (
    DesignRuleCoverageConfirm,
    DesignRuleCoverageRunRead,
)
from ..services.design_rule_coverage import (
    confirm_items,
    start_coverage_run,
)
from ..services.design_rules import get_rule

router = APIRouter(prefix="/api", tags=["设计规则落实检测"])


def _read(run: DesignRuleCoverageRun) -> DesignRuleCoverageRunRead:
    return DesignRuleCoverageRunRead(
        id=run.id,
        rule_id=run.rule_id,
        feedback_id=run.feedback_id,
        rule_version=run.rule_version,
        scope_snapshot=run.scope_snapshot or {},
        status=run.status,
        total=run.total,
        processed=run.processed,
        covered=run.covered,
        partial=run.partial,
        missing=run.missing,
        pending=run.pending,
        error_count=run.error_count,
        items=run.items or [],
        error_message=run.error_message or "",
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


@router.post(
    "/design-rules/{rule_id}/coverage-runs",
    response_model=DesignRuleCoverageRunRead,
    status_code=202,
)
def create_coverage_run(
    rule_id: int, request: Request, db: Session = Depends(get_db)
) -> DesignRuleCoverageRunRead:
    rule = get_rule(db, rule_id)
    run = start_coverage_run(db, rule, request.app.state.session_factory)
    return _read(run)


@router.get(
    "/design-rules/{rule_id}/coverage-runs/latest",
    response_model=DesignRuleCoverageRunRead | None,
)
def latest_coverage_run(
    rule_id: int, db: Session = Depends(get_db)
) -> DesignRuleCoverageRunRead | None:
    get_rule(db, rule_id)
    run = db.scalar(
        select(DesignRuleCoverageRun)
        .where(DesignRuleCoverageRun.rule_id == rule_id)
        .order_by(
            DesignRuleCoverageRun.created_at.desc(),
            DesignRuleCoverageRun.id.desc(),
        )
        .limit(1)
    )
    return _read(run) if run is not None else None


@router.get(
    "/design-rule-coverage-runs/{run_id}",
    response_model=DesignRuleCoverageRunRead,
)
def read_coverage_run(
    run_id: int, db: Session = Depends(get_db)
) -> DesignRuleCoverageRunRead:
    run = db.get(DesignRuleCoverageRun, run_id)
    if run is None:
        raise AppError(404, "落实检测任务不存在", "DESIGN_COVERAGE_RUN_NOT_FOUND")
    return _read(run)


@router.post(
    "/design-rule-coverage-runs/{run_id}/cancel",
    response_model=DesignRuleCoverageRunRead,
)
def cancel_coverage_run(
    run_id: int, db: Session = Depends(get_db)
) -> DesignRuleCoverageRunRead:
    run = db.get(DesignRuleCoverageRun, run_id)
    if run is None:
        raise AppError(404, "落实检测任务不存在", "DESIGN_COVERAGE_RUN_NOT_FOUND")
    if run.status in ("queued", "running"):
        run.status = "canceled"
        db.commit()
        db.refresh(run)
    return _read(run)


@router.patch(
    "/design-rule-coverage-runs/{run_id}/confirm",
    response_model=DesignRuleCoverageRunRead,
)
def confirm_coverage_items(
    run_id: int,
    payload: DesignRuleCoverageConfirm,
    db: Session = Depends(get_db),
) -> DesignRuleCoverageRunRead:
    run = db.get(DesignRuleCoverageRun, run_id)
    if run is None:
        raise AppError(404, "落实检测任务不存在", "DESIGN_COVERAGE_RUN_NOT_FOUND")
    if run.status not in ("succeeded", "canceled"):
        raise AppError(
            409,
            "检测任务尚未结束，完成后才能确认",
            "DESIGN_COVERAGE_RUN_NOT_READY",
        )
    run = confirm_items(
        db,
        run,
        payload.item_keys,
        payload.status,
        payload.note,
    )
    return _read(run)
