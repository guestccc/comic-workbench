"""设置接口：启动提示词与 DeepSeek API Key。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..config import (
    DEEPSEEK_KEY,
    DEFAULT_START_PROMPT,
    IMAGE_PREFIX_PROMPT_KEY,
    PROMPT_KEY,
)
from ..crud import (
    delete_setting,
    get_art_styles,
    get_image_prefix_prompt,
    get_start_prompt,
    mask_key,
    resolve_deepseek_key,
    save_art_styles,
    upsert_setting,
)
from ..database import get_db
from ..errors import AppError
from ..schemas import (
    ArtStyleOptimizeRequest,
    ArtStylesUpdate,
    DeepSeekKeyUpdate,
    DeepSeekStatus,
    ImagePrefixPromptUpdate,
    PromptOptimizeRequest,
    PromptUpdate,
    SettingsRead,
)
from ..services.deepseek import (
    stream_art_style_optimization,
    stream_prompt_optimization,
)

router = APIRouter(prefix="/api/settings", tags=["设置"])


def _build_settings(db: Session) -> SettingsRead:
    """组装设置页所需数据，Key 只返回脱敏值与来源，绝不返回明文。"""
    prompt, prompt_row = get_start_prompt(db)
    key, source, db_configured = resolve_deepseek_key(db)
    art_styles, active_art_style = get_art_styles(db)
    image_prefix_prompt, _ = get_image_prefix_prompt(db)
    return SettingsRead(
        prompt=prompt,
        is_default=prompt == DEFAULT_START_PROMPT,
        prompt_updated_at=prompt_row.updated_at if prompt_row is not None else None,
        deepseek=DeepSeekStatus(
            configured=key is not None,
            source=source,  # type: ignore[arg-type]
            masked_key=mask_key(key),
            db_configured=db_configured,
        ),
        art_styles=art_styles,  # type: ignore[arg-type]
        active_art_style=active_art_style,
        image_prefix_prompt=image_prefix_prompt,
    )


@router.get("", response_model=SettingsRead)
def read_settings(db: Session = Depends(get_db)) -> SettingsRead:
    return _build_settings(db)


@router.put("/prompt", response_model=SettingsRead)
def update_prompt(payload: PromptUpdate, db: Session = Depends(get_db)) -> SettingsRead:
    upsert_setting(db, PROMPT_KEY, payload.content)
    db.commit()
    return _build_settings(db)


@router.put("/image-prefix-prompt", response_model=SettingsRead)
def update_image_prefix_prompt(
    payload: ImagePrefixPromptUpdate, db: Session = Depends(get_db)
) -> SettingsRead:
    """保存全局生图前置提示词；所有故事共用，新故事自动生效。"""
    upsert_setting(db, IMAGE_PREFIX_PROMPT_KEY, payload.content.strip())
    db.commit()
    return _build_settings(db)


@router.post("/prompt/reset", response_model=SettingsRead)
def reset_prompt(db: Session = Depends(get_db)) -> SettingsRead:
    delete_setting(db, PROMPT_KEY)
    db.commit()
    return _build_settings(db)


@router.post("/prompt/optimize")
def optimize_prompt(
    payload: PromptOptimizeRequest, db: Session = Depends(get_db)
) -> StreamingResponse:
    """AI 优化启动提示词，以 SSE 流式返回。

    Key 仅在服务端读取并用于调用上游，不会下发到浏览器。
    """
    api_key, _, _ = resolve_deepseek_key(db)
    # 与 posts.py 一致：先把数据取到局部变量并结束读事务，
    # 后续流式调用期间不持有数据库事务。
    current_prompt = payload.current_prompt
    messages = [message.model_dump() for message in payload.messages]
    db.rollback()

    if api_key is None:
        raise AppError(
            409,
            "尚未配置 DeepSeek API Key，请先到「设置」页面完成配置",
            "DEEPSEEK_KEY_MISSING",
        )

    return StreamingResponse(
        stream_prompt_optimization(api_key, current_prompt, messages),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.put("/art-styles", response_model=SettingsRead)
def update_art_styles(
    payload: ArtStylesUpdate, db: Session = Depends(get_db)
) -> SettingsRead:
    """全量保存画风列表与当前选用的画风，两者在同一事务中落库。"""
    save_art_styles(
        db,
        [style.model_dump() for style in payload.styles],
        payload.active_id,
    )
    db.commit()
    return _build_settings(db)


@router.post("/art-styles/optimize")
def optimize_art_style(
    payload: ArtStyleOptimizeRequest, db: Session = Depends(get_db)
) -> StreamingResponse:
    """AI 优化画风描述，以 SSE 流式返回；Key 只在服务端使用。"""
    api_key, _, _ = resolve_deepseek_key(db)
    # 与启动提示词优化一致：取完数据后结束读事务，流式期间不持有数据库事务
    current_style = payload.current_style
    messages = [message.model_dump() for message in payload.messages]
    db.rollback()

    if api_key is None:
        raise AppError(
            409,
            "尚未配置 DeepSeek API Key，请先到「设置」页面完成配置",
            "DEEPSEEK_KEY_MISSING",
        )

    return StreamingResponse(
        stream_art_style_optimization(api_key, current_style, messages),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.put("/deepseek", response_model=SettingsRead)
def update_deepseek_key(
    payload: DeepSeekKeyUpdate, db: Session = Depends(get_db)
) -> SettingsRead:
    api_key = payload.api_key.get_secret_value().strip()
    upsert_setting(db, DEEPSEEK_KEY, api_key)
    db.commit()
    return _build_settings(db)


@router.delete("/deepseek", response_model=SettingsRead)
def clear_deepseek_key(db: Session = Depends(get_db)) -> SettingsRead:
    delete_setting(db, DEEPSEEK_KEY)
    db.commit()
    return _build_settings(db)
