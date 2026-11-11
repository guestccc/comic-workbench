"""按需抓取已发布作品链接：子进程调用 + 标题匹配 + 错误映射。"""

from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path

from ...config import AppSettings
from ...errors import AppError
from .link_parsing import (
    match_capture_item,
    merge_capture_items,
    parse_worker_output,
)

LINK_CAPTURE_TIMEOUT_SECONDS = 120

_WORKER = Path(__file__).with_name("link_capture_worker.py")

# 一次只跑一个浏览器：并发抓取既占内存，也更容易触发平台风控。
_CAPTURE_LOCK = threading.Lock()


def _unavailable(message: str) -> AppError:
    return AppError(503, message, "PUBLISH_LINK_CAPTURE_UNAVAILABLE")


def fetch_published_link(
    settings: AppSettings,
    platform: str,
    account_name: str,
    title: str,
) -> str:
    """返回匹配到的作品链接；失败抛出带错误码的 AppError。"""
    if not title.strip():
        raise AppError(
            422, "任务载荷没有标题，无法匹配作品", "PUBLISH_LINK_TITLE_MISSING"
        )
    python = settings.sau_python
    if not python.is_file():
        raise _unavailable(f"找不到 sau 解释器：{python}，无法启动抓取")
    if not _WORKER.is_file():
        raise _unavailable(f"找不到抓取脚本：{_WORKER}")
    cookie = (
        settings.sau_project_dir / "cookies" / f"{platform}_{account_name}.json"
    )
    if not cookie.is_file():
        raise _unavailable(
            f"找不到 {platform} 账号 {account_name} 的 Cookie，"
            "请先在设置页扫码登录后再抓取"
        )
    if not _CAPTURE_LOCK.acquire(blocking=False):
        raise AppError(
            409, "已有作品链接抓取正在进行，请稍后重试", "PUBLISH_LINK_CAPTURE_BUSY"
        )

    try:
        payload = _run_worker(python, cookie, platform, settings.sau_project_dir)
    finally:
        _CAPTURE_LOCK.release()

    items = payload.get("items")
    items = merge_capture_items(items if isinstance(items, list) else [])
    reason = str(payload.get("reason") or "").strip()
    if not items:
        raise AppError(
            502,
            f"抓取失败：{reason or '作品列表为空，请到创作中心确认登录态'}",
            "PUBLISH_LINK_CAPTURE_FAILED",
        )

    url = match_capture_item(platform, title, items)
    if url is None:
        raise AppError(
            404,
            f"在平台已发布作品中未找到标题「{title}」，本次读取 {len(items)} 条；"
            "请确认作品已发布，或直接粘贴链接回填",
            "PUBLISH_LINK_NOT_FOUND",
        )
    return url


def _run_worker(
    python: Path, cookie: Path, platform: str, cwd: Path
) -> dict:
    command = [
        str(python),
        str(_WORKER),
        "--platform",
        platform,
        "--cookie",
        str(cookie),
    ]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=LINK_CAPTURE_TIMEOUT_SECONDS,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AppError(
            502,
            f"抓取作品链接超时（{LINK_CAPTURE_TIMEOUT_SECONDS} 秒），请稍后重试",
            "PUBLISH_LINK_CAPTURE_FAILED",
        ) from exc
    except OSError as exc:
        raise _unavailable(f"无法启动抓取进程：{exc}") from exc

    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    if result.returncode != 0:
        tail = "\n".join(stderr.strip().splitlines()[-4:])
        raise AppError(
            502,
            f"抓取进程退出码 {result.returncode}：{tail or '无输出'}",
            "PUBLISH_LINK_CAPTURE_FAILED",
        )
    try:
        payload = parse_worker_output(stdout)
    except ValueError as exc:
        tail = "\n".join(stderr.strip().splitlines()[-4:])
        raise AppError(
            502,
            f"抓取器返回结果无法解析：{tail or '无输出'}",
            "PUBLISH_LINK_CAPTURE_FAILED",
        ) from exc
    return payload
