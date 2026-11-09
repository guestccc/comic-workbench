"""设计建议库接口：建议 CRUD 与应用记录。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas import (
    DesignFeedbackApplicationCreate,
    DesignFeedbackApplicationRead,
    DesignFeedbackCreate,
    DesignFeedbackDetail,
    DesignFeedbackRead,
    DesignFeedbackRulePromote,
    DesignFeedbackUpdate,
)
from ..services import design_feedbacks as service

router = APIRouter(prefix="/api/design-feedbacks", tags=["设计建议"])


@router.get("", response_model=list[DesignFeedbackRead])
def list_design_feedbacks(
    request: Request,
    status: str | None = Query(default=None),
    category: str | None = Query(default=None),
    scope: str | None = Query(default=None),
    story_id: int | None = Query(default=None, ge=1),
    keyword: str | None = Query(default=None, max_length=120),
    db: Session = Depends(get_db),
) -> list[dict]:
    upload_dir = request.app.state.app_settings.upload_dir
    return service.list_design_feedbacks(
        db,
        upload_dir,
        status=status,
        category=category,
        scope=scope,
        story_id=story_id,
        keyword=keyword,
    )


@router.post("", response_model=DesignFeedbackDetail, status_code=201)
def create_design_feedback(
    payload: DesignFeedbackCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    upload_dir = request.app.state.app_settings.upload_dir
    return service.create_design_feedback(db, upload_dir, payload)


@router.get("/{feedback_id}", response_model=DesignFeedbackDetail)
def get_design_feedback(
    feedback_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    upload_dir = request.app.state.app_settings.upload_dir
    return service.get_design_feedback_detail(db, upload_dir, feedback_id)


@router.patch("/{feedback_id}", response_model=DesignFeedbackDetail)
def update_design_feedback(
    feedback_id: int,
    payload: DesignFeedbackUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    upload_dir = request.app.state.app_settings.upload_dir
    return service.update_design_feedback(db, upload_dir, feedback_id, payload)


@router.delete("/{feedback_id}", status_code=204)
def delete_design_feedback(
    feedback_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    upload_dir = request.app.state.app_settings.upload_dir
    service.delete_design_feedback(db, upload_dir, feedback_id)
    return Response(status_code=204)


@router.post("/{feedback_id}/promote", response_model=DesignFeedbackDetail)
def promote_design_feedback(
    feedback_id: int,
    payload: DesignFeedbackRulePromote,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    upload_dir = request.app.state.app_settings.upload_dir
    return service.promote_design_feedback(db, upload_dir, feedback_id, payload)


@router.delete("/{feedback_id}/promote", response_model=DesignFeedbackDetail)
def remove_design_feedback_rule(
    feedback_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    upload_dir = request.app.state.app_settings.upload_dir
    return service.remove_design_feedback_rule(db, upload_dir, feedback_id)


@router.post(
    "/{feedback_id}/applications",
    response_model=DesignFeedbackApplicationRead,
    status_code=201,
)
def create_design_feedback_application(
    feedback_id: int,
    payload: DesignFeedbackApplicationCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    upload_dir = request.app.state.app_settings.upload_dir
    return service.create_design_feedback_application(
        db, upload_dir, feedback_id, payload
    )


@router.delete(
    "/{feedback_id}/applications/{application_id}", status_code=204
)
def delete_design_feedback_application(
    feedback_id: int,
    application_id: int,
    db: Session = Depends(get_db),
) -> Response:
    service.delete_design_feedback_application(
        db, feedback_id, application_id
    )
    return Response(status_code=204)
