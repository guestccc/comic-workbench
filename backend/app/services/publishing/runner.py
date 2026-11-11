"""sau 子进程适配器：构建命令、执行、超时终止与状态判定。"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ...config import (
    PUBLISH_PLATFORM_DOUYIN,
    PUBLISH_PLATFORM_XIAOHONGSHU,
    PUBLISH_SUCCESS_MARKER,
    PUBLISH_TIMEZONE,
    XHS_DECLARATION_REPOST,
    AppSettings,
)
from ...models import PublishJob, utc_now

logger = logging.getLogger("comic_workbench")

_LOG_TAIL_CHARS = 200_000
_EXCERPT_CHARS = 4_000
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def strip_ansi(text: str) -> str:
    """sau 日志带终端颜色码；回显给页面和任务摘要前统一去掉。"""
    return _ANSI_ESCAPE.sub("", text)


@dataclass(slots=True)
class PublishRunResult:
    exit_code: int | None
    timed_out: bool
    output: str


def _schedule_for_cli(value: str) -> str:
    """payload_json 里的 UTC ISO → sau 需要的本地时间字符串。"""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(PUBLISH_TIMEZONE).strftime("%Y-%m-%d %H:%M")


def build_upload_command(settings: AppSettings, payload: dict) -> list[str]:
    """图文发布命令；抖音与小红书 CLI 参数一致，只换子命令。

    定时任务带 --schedule；立即任务不能带，sau 缺少该参数时走立即发布分支。
    """
    platform = payload.get("platform") or PUBLISH_PLATFORM_DOUYIN
    command = [
        str(settings.sau_executable),
        platform,
        "upload-note",
        "--account",
        payload["account_name"],
        "--images",
        *[str(path) for path in payload["images"]],
        "--title",
        payload["title"],
        "--note",
        payload["note"],
        "--tags",
        ",".join(payload.get("tags") or []),
    ]
    # 只有小红书 upload-note 支持这些参数；抖音图文没有对应选项
    if platform == PUBLISH_PLATFORM_XIAOHONGSHU:
        declaration = payload.get("declaration")
        if declaration and str(declaration) == XHS_DECLARATION_REPOST:
            # --repost-source 与 --declaration 互斥：来源转载只能走前者
            repost_source = str(payload.get("repost_source") or "").strip()
            if not repost_source:
                raise ValueError("来源转载声明缺少来源媒体名，拒绝发布")
            command.extend(["--repost-source", repost_source])
        elif declaration:
            command.extend(["--declaration", str(declaration)])
        # 合集暂停接入：sau 工作区还没有 --collection，传了会被判为未知参数
    schedule_at = payload.get("schedule_at")
    if payload.get("mode", "scheduled") == "immediate":
        if schedule_at:
            raise ValueError("立即发布任务不能包含 schedule_at")
        return command
    if not schedule_at:
        raise ValueError("定时发布任务缺少 schedule_at")
    command.extend(["--schedule", _schedule_for_cli(schedule_at)])
    return command


def _read_tail(path: Path, max_chars: int = _LOG_TAIL_CHARS) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    text = data.decode("utf-8", errors="replace")
    return text[-max_chars:]


def _kill_process_tree(process: subprocess.Popen) -> None:
    """Windows 用 taskkill 终止整棵进程树；其他平台退回 terminate。"""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
            check=False,
        )
        return
    process.terminate()


def run_sau_upload(
    settings: AppSettings,
    payload: dict,
    log_path: Path,
) -> PublishRunResult:
    """执行一次上传；日志同时写 stdout / stderr。"""
    command = build_upload_command(settings, payload)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    creationflags = (
        subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    )

    with log_path.open("wb") as log_file:
        process = subprocess.Popen(
            command,
            cwd=str(settings.sau_project_dir),
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=env,
            creationflags=creationflags,
        )
        try:
            process.wait(timeout=settings.publish_timeout_seconds)
            timed_out = False
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_process_tree(process)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("发布进程未在强杀后退出: pid=%s", process.pid)

    output = _read_tail(log_path)
    return PublishRunResult(
        exit_code=process.returncode,
        timed_out=timed_out,
        output=output,
    )


def classify_result(
    result: PublishRunResult, mode: str = "scheduled"
) -> tuple[str, str]:
    """把子进程结果映射成任务状态；退出码 0 但没有成功标记仍是 unknown。

    定时任务成功只代表平台已接受定时；立即任务成功则平台已发布。
    """
    if result.timed_out:
        return (
            "unknown",
            "发布进程超时被终止，请到对应平台创作中心核对是否已发布或已定时",
        )
    if result.exit_code not in (0, None):
        tail = "\n".join(result.output.strip().splitlines()[-6:])
        return "failed", f"发布器退出码 {result.exit_code}：{strip_ansi(tail)}"
    if PUBLISH_SUCCESS_MARKER in result.output:
        return ("published" if mode == "immediate" else "scheduled"), ""
    return (
        "unknown",
        "发布器退出码 0，但未观察到成功标记，请人工核对后再修正状态",
    )


def _execute_job(
    session_factory: sessionmaker[Session],
    settings: AppSettings,
    job_id: str,
) -> None:
    log_path = settings.resolved_publish_log_dir / f"{job_id}.log"
    try:
        with session_factory() as session:
            job = session.get(PublishJob, job_id)
            if job is None:
                return
            if job.status != "queued":
                logger.info("发布任务 %s 状态为 %s，跳过执行", job_id, job.status)
                return

            running = session.scalar(
                select(PublishJob.id).where(
                    PublishJob.platform == job.platform,
                    PublishJob.status == "running",
                    PublishJob.id != job.id,
                )
            )
            if running:
                job.status = "failed"
                job.error_message = "已有发布任务在运行，请稍后重试"
                job.finished_at = utc_now()
                session.commit()
                return

            job.status = "running"
            job.started_at = utc_now()
            job.error_message = ""
            session.commit()
            payload = dict(job.payload_json or {})

        result = run_sau_upload(settings, payload, log_path)
        status, error_message = classify_result(
            result, str(payload.get("mode") or "scheduled")
        )

        with session_factory() as session:
            job = session.get(PublishJob, job_id)
            if job is None:
                return
            job.status = status
            job.exit_code = result.exit_code
            job.stdout_excerpt = result.output[-_EXCERPT_CHARS:]
            job.error_message = error_message
            job.finished_at = utc_now()
            session.commit()
    except Exception as exc:  # noqa: BLE001 - 任务线程必须兜底，不能静默死掉
        logger.exception("发布任务 %s 执行失败", job_id)
        try:
            with session_factory() as session:
                job = session.get(PublishJob, job_id)
                if job is not None and job.status in ("queued", "running"):
                    job.status = "failed"
                    job.error_message = f"发布器启动或执行失败：{exc}"
                    job.finished_at = utc_now()
                    session.commit()
        except Exception:  # noqa: BLE001
            logger.exception("回写发布任务 %s 失败状态时再次出错", job_id)


def start_job_thread(
    session_factory: sessionmaker[Session],
    settings: AppSettings,
    job_id: str,
) -> None:
    """后台线程执行，避免阻塞创建任务的 HTTP 响应。"""
    thread = threading.Thread(
        target=_execute_job,
        args=(session_factory, settings, job_id),
        daemon=True,
        name=f"publish-{job_id}",
    )
    thread.start()


def run_sau_check(
    settings: AppSettings,
    account_name: str,
    platform: str = PUBLISH_PLATFORM_DOUYIN,
    timeout: int = 180,
) -> bool:
    """调用 sau <platform> check；退出码 0 视为有效。"""
    command = [
        str(settings.sau_executable),
        platform,
        "check",
        "--account",
        account_name,
    ]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    try:
        result = subprocess.run(
            command,
            cwd=str(settings.sau_project_dir),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def start_sau_login(
    settings: AppSettings,
    account_name: str,
    platform: str = PUBLISH_PLATFORM_DOUYIN,
) -> Path:
    """打开有头浏览器等待扫码；立即返回，登录结果由「检测登录」确认。"""
    log_dir = settings.resolved_publish_log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"login_{platform}_{account_name}_{stamp}.log"
    command = [
        str(settings.sau_executable),
        platform,
        "login",
        "--account",
        account_name,
        "--headed",
    ]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    with log_path.open("wb") as log_file:
        subprocess.Popen(
            command,
            cwd=str(settings.sau_project_dir),
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=env,
            creationflags=(
                subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            ),
        )
    return log_path
