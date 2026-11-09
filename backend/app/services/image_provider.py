"""生图服务：配置解析、OpenAI 兼容调用与图片下载校验。

P0 只做同步调用：文生图走 /v1/images/generations，
带角色参考图时走 /v1/images/edits（multipart，多图字段 image[]）。
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from ..config import (
    DEFAULT_IMAGE_PROVIDER_BASE_URL,
    DEFAULT_IMAGE_QUALITY,
    DEFAULT_IMAGE_SIZE,
    DEFAULT_IMAGE_MODEL,
    IMAGE_DOWNLOAD_TIMEOUT,
    IMAGE_PROVIDER_API_KEY,
    IMAGE_PROVIDER_CONFIG_KEY,
    IMAGE_PROVIDER_CONNECT_TIMEOUT,
    IMAGE_PROVIDER_READ_TIMEOUT,
    MAX_PAGE_IMAGE_BYTES,
)
from ..crud import delete_setting, get_setting, mask_key, upsert_setting
from ..errors import AppError
from ..services.files import detect_image_type
from sqlalchemy.orm import Session

logger = logging.getLogger("comic_workbench")

# 上游边缘节点偶尔会在 TLS 握手阶段直接重置连接；这是建立连接前的失败，
# 重试不会重复提交生图任务。读超时不重试，避免一张图被计费两次。
_CONNECT_ATTEMPTS = 4
_CONNECT_RETRY_BACKOFF_SECONDS = 0.3


def _request_with_connect_retry(
    request: Callable[[], httpx.Response],
) -> httpx.Response:
    """只重试连接阶段失败（DNS / TCP / TLS 握手），不重试已发出的请求。"""
    for attempt in range(1, _CONNECT_ATTEMPTS + 1):
        try:
            return request()
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            if attempt >= _CONNECT_ATTEMPTS:
                raise
            logger.warning(
                "生图服务连接失败，第 %s/%s 次重试：%s",
                attempt,
                _CONNECT_ATTEMPTS,
                exc,
            )
            time.sleep(_CONNECT_RETRY_BACKOFF_SECONDS * attempt)
    raise AssertionError("unreachable")


@dataclass(slots=True)
class ImageProviderConfig:
    base_url: str
    api_key: str | None
    model: str
    size: str
    quality: str
    source: str
    db_configured: bool


@dataclass(slots=True)
class ReferenceImage:
    name: str
    data: bytes
    content_type: str = "image/png"
    extension: str = "png"


@dataclass(slots=True)
class GeneratedImage:
    data: bytes
    content_type: str
    extension: str
    sha256: str
    width: int | None
    height: int | None
    elapsed_ms: int
    request_id: str | None
    model: str
    size: str


def _read_config(db: Session) -> dict:
    row = get_setting(db, IMAGE_PROVIDER_CONFIG_KEY)
    if row is None or not row.value.strip():
        return {}
    try:
        parsed = json.loads(row.value)
    except json.JSONDecodeError:
        logger.warning("生图配置 JSON 解析失败，已按默认值处理")
        return {}
    return parsed if isinstance(parsed, dict) else {}


def resolve_image_provider(db: Session) -> ImageProviderConfig:
    """环境变量优先，其次数据库配置，最后默认值。"""
    config = _read_config(db)
    key_row = get_setting(db, IMAGE_PROVIDER_API_KEY)
    db_key = key_row.value.strip() if key_row is not None and key_row.value.strip() else None
    env_key = os.environ.get("IMAGE_PROVIDER_API_KEY", "").strip()

    base_url = (
        os.environ.get("IMAGE_PROVIDER_BASE_URL", "").strip()
        or str(config.get("base_url") or "").strip()
        or DEFAULT_IMAGE_PROVIDER_BASE_URL
    ).rstrip("/")
    model = (
        os.environ.get("IMAGE_PROVIDER_MODEL", "").strip()
        or str(config.get("model") or "").strip()
        or DEFAULT_IMAGE_MODEL
    )
    size = (
        os.environ.get("IMAGE_PROVIDER_SIZE", "").strip()
        or str(config.get("size") or "").strip()
        or DEFAULT_IMAGE_SIZE
    )
    quality = (
        os.environ.get("IMAGE_PROVIDER_QUALITY", "").strip()
        or str(config.get("quality") or "").strip()
        or DEFAULT_IMAGE_QUALITY
    )

    if env_key:
        return ImageProviderConfig(
            base_url=base_url,
            api_key=env_key,
            model=model,
            size=size,
            quality=quality,
            source="env",
            db_configured=db_key is not None,
        )
    if db_key:
        return ImageProviderConfig(
            base_url=base_url,
            api_key=db_key,
            model=model,
            size=size,
            quality=quality,
            source="db",
            db_configured=True,
        )
    return ImageProviderConfig(
        base_url=base_url,
        api_key=None,
        model=model,
        size=size,
        quality=quality,
        source="none",
        db_configured=False,
    )


def provider_status(config: ImageProviderConfig) -> dict:
    return {
        "configured": config.api_key is not None,
        "source": config.source,
        "masked_key": mask_key(config.api_key),
        "base_url": config.base_url,
        "model": config.model,
        "size": config.size,
        "quality": config.quality,
        "db_configured": config.db_configured,
    }


def save_image_provider(
    db: Session,
    *,
    base_url: str,
    model: str,
    size: str,
    quality: str,
    api_key: str | None,
) -> None:
    config = {
        "base_url": base_url.rstrip("/"),
        "model": model,
        "size": size,
        "quality": quality,
    }
    upsert_setting(db, IMAGE_PROVIDER_CONFIG_KEY, json.dumps(config, ensure_ascii=False))
    if api_key:
        upsert_setting(db, IMAGE_PROVIDER_API_KEY, api_key)
    db.commit()


def clear_image_provider_key(db: Session) -> None:
    delete_setting(db, IMAGE_PROVIDER_API_KEY)
    db.commit()


def _headers(config: ImageProviderConfig) -> dict[str, str]:
    if not config.api_key:
        raise AppError(
            409,
            "尚未配置生图 API Key，请先到「设置」页面完成配置",
            "IMAGE_PROVIDER_NOT_CONFIGURED",
        )
    return {
        "Authorization": f"Bearer {config.api_key}",
        "Accept": "application/json",
    }


def _raise_for_status(response: httpx.Response) -> None:
    status = response.status_code
    if status == 200:
        return
    logger.warning("生图上游返回异常状态: %s", status)
    if status in (401, 403):
        raise AppError(502, "生图 API Key 无效或没有权限，请在设置中检查", "IMAGE_PROVIDER_AUTH_FAILED")
    if status == 402:
        raise AppError(502, "生图账户余额不足，请充值后重试", "IMAGE_PROVIDER_INSUFFICIENT_BALANCE")
    if status == 429:
        raise AppError(429, "生图请求过于频繁，请稍后重试", "IMAGE_PROVIDER_RATE_LIMITED")
    if status in (400, 422):
        detail = response.text[:300].strip()
        raise AppError(
            502,
            f"生图服务拒绝了请求：{detail or '请检查提示词后重试'}",
            "IMAGE_PROVIDER_REJECTED",
        )
    raise AppError(503, "生图服务暂时不可用，请稍后重试", "IMAGE_PROVIDER_UNAVAILABLE")


def list_models(config: ImageProviderConfig) -> list[str]:
    """调用 /v1/models；只用于测试连接，不产生生图费用。"""
    headers = _headers(config)

    def request() -> httpx.Response:
        with httpx.Client(timeout=30.0) as client:
            return client.get(f"{config.base_url}/v1/models", headers=headers)

    try:
        response = _request_with_connect_retry(request)
    except httpx.TimeoutException as exc:
        raise AppError(504, "连接生图服务超时", "IMAGE_PROVIDER_TIMEOUT") from exc
    except httpx.RequestError as exc:
        raise AppError(502, "无法连接生图服务，请检查网络", "IMAGE_PROVIDER_NETWORK_ERROR") from exc
    _raise_for_status(response)
    try:
        payload = response.json()
    except ValueError as exc:
        raise AppError(502, "生图服务返回了无法解析的响应", "IMAGE_PROVIDER_BAD_OUTPUT") from exc
    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []
    return [
        str(item.get("id"))
        for item in items
        if isinstance(item, dict) and item.get("id")
    ]


def _load_image_bytes(url: str) -> tuple[bytes, str]:
    if not url.startswith(("http://", "https://")):
        raise AppError(502, "生图服务返回了非法的图片地址", "IMAGE_PROVIDER_BAD_OUTPUT")
    try:
        with httpx.Client(
            timeout=IMAGE_DOWNLOAD_TIMEOUT, follow_redirects=True
        ) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                buffer = bytearray()
                for chunk in response.iter_bytes():
                    buffer.extend(chunk)
                    if len(buffer) > MAX_PAGE_IMAGE_BYTES:
                        raise AppError(
                            413,
                            f"生成图片超过 {MAX_PAGE_IMAGE_BYTES // (1024 * 1024)}MB",
                            "FILE_TOO_LARGE",
                        )
                data = bytes(buffer)
    except httpx.HTTPError as exc:
        raise AppError(502, f"下载生成图片失败：{exc}", "IMAGE_PROVIDER_DOWNLOAD_FAILED") from exc
    if not data:
        raise AppError(502, "生图服务返回了空图片", "IMAGE_PROVIDER_BAD_OUTPUT")
    content_type = response.headers.get("content-type", "").split(";")[0].strip()
    return data, content_type


def _parse_image(payload: dict, elapsed_ms: int, model: str, size: str) -> GeneratedImage:
    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not items:
        raise AppError(502, "生图服务没有返回图片", "IMAGE_PROVIDER_BAD_OUTPUT")
    item = items[0] if isinstance(items[0], dict) else {}
    request_id = payload.get("task_id") or payload.get("id")
    width = item.get("width")
    height = item.get("height")

    b64 = item.get("b64_json")
    if isinstance(b64, str) and b64.strip():
        try:
            data = base64.b64decode(b64, validate=True)
        except (ValueError, TypeError) as exc:
            raise AppError(502, "生图服务返回的 base64 图片无法解析", "IMAGE_PROVIDER_BAD_OUTPUT") from exc
        content_type = str(item.get("mime_type") or "image/png")
    else:
        url = item.get("url")
        if not isinstance(url, str) or not url.strip():
            raise AppError(502, "生图服务返回结果里没有图片地址", "IMAGE_PROVIDER_BAD_OUTPUT")
        data, content_type = _load_image_bytes(url.strip())

    if len(data) > MAX_PAGE_IMAGE_BYTES:
        raise AppError(
            413,
            f"生成图片超过 {MAX_PAGE_IMAGE_BYTES // (1024 * 1024)}MB",
            "FILE_TOO_LARGE",
        )
    extension = detect_image_type(data[:16])
    if extension is None:
        raise AppError(502, "生图服务返回的内容不是 JPG / PNG / WebP 图片", "IMAGE_PROVIDER_BAD_OUTPUT")
    return GeneratedImage(
        data=data,
        content_type=content_type or f"image/{extension}",
        extension=extension,
        sha256=hashlib.sha256(data).hexdigest(),
        width=width if isinstance(width, int) else None,
        height=height if isinstance(height, int) else None,
        elapsed_ms=elapsed_ms,
        request_id=str(request_id) if request_id else None,
        model=model,
        size=size,
    )


def generate_image(
    config: ImageProviderConfig,
    prompt: str,
    references: list[ReferenceImage] | None = None,
) -> GeneratedImage:
    """同步生成一张图；有参考图时走 edits。"""
    if not prompt.strip():
        raise AppError(422, "生图提示词不能为空", "IMAGE_PROMPT_EMPTY")
    headers = _headers(config)
    started = time.monotonic()
    timeout = httpx.Timeout(
        IMAGE_PROVIDER_READ_TIMEOUT, connect=IMAGE_PROVIDER_CONNECT_TIMEOUT
    )
    fields = {
        "model": config.model,
        "prompt": prompt,
        "size": config.size,
        "n": 1,
    }
    if config.quality and config.quality != "auto":
        fields["quality"] = config.quality

    def request() -> httpx.Response:
        with httpx.Client(timeout=timeout) as client:
            if references:
                # multipart 的所有字段都必须是字符串
                form_fields = {key: str(value) for key, value in fields.items()}
                files = [
                    (
                        "image[]",
                        (
                            f"reference-{index}.{reference.extension}",
                            reference.data,
                            reference.content_type,
                        ),
                    )
                    for index, reference in enumerate(references, start=1)
                ]
                return client.post(
                    f"{config.base_url}/v1/images/edits",
                    headers=headers,
                    data=form_fields,
                    files=files,
                )
            return client.post(
                f"{config.base_url}/v1/images/generations",
                headers=headers,
                json=fields,
            )

    try:
        response = _request_with_connect_retry(request)
    except httpx.TimeoutException as exc:
        raise AppError(
            504,
            f"生图超时（已等待 {int(IMAGE_PROVIDER_READ_TIMEOUT)} 秒），请稍后重试",
            "IMAGE_PROVIDER_TIMEOUT",
        ) from exc
    except httpx.RequestError as exc:
        raise AppError(502, "无法连接生图服务，请检查网络", "IMAGE_PROVIDER_NETWORK_ERROR") from exc

    _raise_for_status(response)
    try:
        payload = response.json()
    except ValueError as exc:
        raise AppError(502, "生图服务返回了无法解析的响应", "IMAGE_PROVIDER_BAD_OUTPUT") from exc
    if not isinstance(payload, dict):
        raise AppError(502, "生图服务返回格式不正确", "IMAGE_PROVIDER_BAD_OUTPUT")
    return _parse_image(
        payload,
        elapsed_ms=int((time.monotonic() - started) * 1000),
        model=config.model,
        size=config.size,
    )
