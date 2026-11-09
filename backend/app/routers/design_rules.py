"""结构化设计规则接口：草案、激活、停用、回滚与影响预览。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import (
    DesignRuleCreate,
    DesignRulePreviewRead,
    DesignRulePreviewRequest,
    DesignRuleRead,
    DesignRuleOnceApplyResult,
    DesignRuleOncePreview,
    DesignRuleOnceTarget,
    DesignRuleResultCreate,
    DesignRuleResultRead,
    DesignRuleTemplateApplyResult,
    DesignRuleTemplatePreview,
    DesignRuleUpdate,
)
from ..services import design_rules as service

router = APIRouter(prefix="/api", tags=["设计建议"])


@router.get(
    "/design-feedbacks/{feedback_id}/rules",
    response_model=list[DesignRuleRead],
)
def list_feedback_rules(
    feedback_id: int, db: Session = Depends(get_db)
) -> list[dict]:
    return service.list_rules_for_feedback(db, feedback_id)


@router.post(
    "/design-feedbacks/{feedback_id}/rules",
    response_model=DesignRuleRead,
    status_code=201,
)
def create_feedback_rule(
    feedback_id: int,
    payload: DesignRuleCreate,
    db: Session = Depends(get_db),
) -> dict:
    return service.create_rule(db, feedback_id, payload)


@router.post("/design-rules/preview", response_model=DesignRulePreviewRead)
def preview_rule_impact(
    payload: DesignRulePreviewRequest,
    db: Session = Depends(get_db),
) -> dict:
    return service.preview_impact(db, payload)


@router.post(
    "/design-rules/{rule_id}/apply-once/preview",
    response_model=DesignRuleOncePreview,
)
def preview_apply_once(
    rule_id: int,
    payload: DesignRuleOnceTarget,
    db: Session = Depends(get_db),
) -> dict:
    return service.preview_once(db, rule_id, payload)


@router.post(
    "/design-rules/{rule_id}/apply-once",
    response_model=DesignRuleOnceApplyResult,
)
def apply_once(
    rule_id: int,
    payload: DesignRuleOnceTarget,
    db: Session = Depends(get_db),
) -> dict:
    return service.apply_once(db, rule_id, payload)


@router.post(
    "/design-rules/{rule_id}/template-preview",
    response_model=DesignRuleTemplatePreview,
)
def preview_template_write(
    rule_id: int, db: Session = Depends(get_db)
) -> dict:
    return service.preview_template_write(db, rule_id)


@router.post(
    "/design-rules/{rule_id}/apply-to-template",
    response_model=DesignRuleTemplateApplyResult,
)
def apply_template_write(
    rule_id: int, db: Session = Depends(get_db)
) -> dict:
    return service.apply_template_write(db, rule_id)


@router.get(
    "/design-rules/{rule_id}/results",
    response_model=list[DesignRuleResultRead],
)
def list_rule_results(
    rule_id: int, db: Session = Depends(get_db)
) -> list[dict]:
    return service.list_rule_results(db, rule_id)


@router.post(
    "/design-rules/{rule_id}/results",
    response_model=DesignRuleResultRead,
    status_code=201,
)
def create_rule_result(
    rule_id: int,
    payload: DesignRuleResultCreate,
    db: Session = Depends(get_db),
) -> dict:
    return service.create_rule_result(db, rule_id, payload)


@router.patch("/design-rules/{rule_id}", response_model=DesignRuleRead)
def update_rule(
    rule_id: int,
    payload: DesignRuleUpdate,
    db: Session = Depends(get_db),
) -> dict:
    return service.update_rule(db, rule_id, payload)


@router.post(
    "/design-rules/{rule_id}/activate", response_model=DesignRuleRead
)
def activate_rule(rule_id: int, db: Session = Depends(get_db)) -> dict:
    return service.set_rule_status(db, rule_id, "active")


@router.post(
    "/design-rules/{rule_id}/disable", response_model=DesignRuleRead
)
def disable_rule(rule_id: int, db: Session = Depends(get_db)) -> dict:
    return service.set_rule_status(db, rule_id, "disabled")


@router.post(
    "/design-rules/{rule_id}/rollback", response_model=DesignRuleRead
)
def rollback_rule(rule_id: int, db: Session = Depends(get_db)) -> dict:
    return service.rollback_rule(db, rule_id)


@router.delete("/design-rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, db: Session = Depends(get_db)) -> Response:
    service.delete_rule(db, rule_id)
    return Response(status_code=204)
