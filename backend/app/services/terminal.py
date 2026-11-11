"""本机终端启动：在工作台项目根目录打开终端并运行 Claude Code。

优先使用 Windows Terminal（`wt`），未安装时回退到 `cmd`。
只负责创建子进程，不接管输出、不等待退出；终端生命周期与工作台解耦。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..config import WINDOWS_TERMINAL_EXECUTABLE
from ..errors import AppError

# 终端里执行的固定命令：不接受任何请求参数拼接
TERMINAL_COMMAND = "cmd.exe"
CLAUDE_COMMAND = "claude"
WINDOWS_TERMINAL_COMMAND = "wt"
TERMINAL_WINDOWS_TERMINAL = "windows-terminal"
TERMINAL_CMD = "cmd"


@dataclass(slots=True, frozen=True)
class TerminalLaunch:
    """一次终端启动的结果，仅用于回填接口响应。"""

    terminal: str
    directory: str


def find_windows_terminal() -> str | None:
    """查找 Windows Terminal。

    顺序：环境变量 → 配置的便携版路径 → PATH → Store 版应用执行别名。
    本机是免安装便携版，只有配置路径能找到 `wt.exe`。
    """
    configured = os.environ.get("WINDOWS_TERMINAL_EXECUTABLE")
    if configured and Path(configured).is_file():
        return configured
    if WINDOWS_TERMINAL_EXECUTABLE.is_file():
        return str(WINDOWS_TERMINAL_EXECUTABLE)

    executable = shutil.which(WINDOWS_TERMINAL_COMMAND) or shutil.which(
        f"{WINDOWS_TERMINAL_COMMAND}.exe"
    )
    if executable:
        return executable

    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None
    alias = Path(local_app_data) / "Microsoft" / "WindowsApps" / "wt.exe"
    return str(alias) if alias.is_file() else None


def launch_claude_terminal(project_dir: Path) -> TerminalLaunch:
    """在新终端窗口中进入 project_dir 并启动 claude。

    失败时抛出 AppError，由全局异常处理器转成统一错误 JSON；
    绝不静默打开一个没有 claude 的空终端。
    """
    if os.name != "nt":
        raise AppError(
            501,
            "打开终端目前仅支持 Windows 本机运行",
            "TERMINAL_UNSUPPORTED",
        )
    if shutil.which(CLAUDE_COMMAND) is None:
        raise AppError(
            409,
            "未找到 claude 命令：请先在本机安装并登录 Claude Code，重启工作台后再试",
            "CLAUDE_NOT_FOUND",
        )

    directory = str(project_dir)
    windows_terminal = find_windows_terminal()
    if windows_terminal:
        command = [
            windows_terminal,
            "-d",
            directory,
            TERMINAL_COMMAND,
            "/k",
            CLAUDE_COMMAND,
        ]
        # wt 自己开窗口；隐藏它的启动控制台，避免宿主闪出多余黑窗
        creationflags = subprocess.CREATE_NO_WINDOW
        terminal = TERMINAL_WINDOWS_TERMINAL
    else:
        command = [TERMINAL_COMMAND, "/k", CLAUDE_COMMAND]
        creationflags = subprocess.CREATE_NEW_CONSOLE
        terminal = TERMINAL_CMD

    try:
        subprocess.Popen(
            command,
            cwd=directory,
            creationflags=creationflags,
            close_fds=True,
        )
    except OSError as exc:
        raise AppError(
            500,
            f"终端启动失败：{exc}",
            "TERMINAL_LAUNCH_FAILED",
        ) from exc

    return TerminalLaunch(terminal=terminal, directory=directory)
