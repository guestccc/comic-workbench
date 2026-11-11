"""系统工具接口：在当前项目目录打开终端并启动 Claude Code。"""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..config import PROJECT_DIR
from ..errors import AppError
from ..schemas import TerminalLaunchRead
from ..services.terminal import launch_claude_terminal

router = APIRouter(prefix="/api/system", tags=["系统"])

# 终端启动会创建本机进程，只允许回环客户端调用。
# testclient 是 FastAPI TestClient 的占位 host，仅用于测试。
_LOCAL_CLIENT_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


@router.post("/terminal", response_model=TerminalLaunchRead)
def open_terminal(request: Request) -> TerminalLaunchRead:
    """在项目根目录打开终端并运行 claude；工作目录不接受请求参数。"""
    host = request.client.host if request.client else ""
    if host not in _LOCAL_CLIENT_HOSTS:
        raise AppError(403, "只允许在本机打开终端", "TERMINAL_LOCAL_ONLY")

    launch = launch_claude_terminal(PROJECT_DIR)
    return TerminalLaunchRead(
        terminal=launch.terminal,
        directory=launch.directory,
        message="终端已打开，正在启动 Claude Code",
    )
