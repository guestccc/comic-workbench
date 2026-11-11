"""顶栏终端启动：接口契约、Windows Terminal 查找与进程启动参数。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.errors import AppError
from app.routers import system
from app.services import terminal


def _which_claude_only(name):
    return "claude.cmd" if name == "claude" else None


def test_open_terminal_uses_project_dir(client, monkeypatch):
    calls: list = []

    def fake_launch(project_dir):
        calls.append(project_dir)
        return terminal.TerminalLaunch(terminal="cmd", directory=str(project_dir))

    monkeypatch.setattr(system, "launch_claude_terminal", fake_launch)

    response = client.post("/api/system/terminal")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["terminal"] == "cmd"
    assert body["directory"] == str(system.PROJECT_DIR)
    assert body["message"]
    assert calls == [system.PROJECT_DIR]


def test_open_terminal_rejects_remote_client(monkeypatch):
    monkeypatch.setattr(
        system,
        "launch_claude_terminal",
        lambda project_dir: pytest.fail("远程客户端不应创建终端进程"),
    )
    remote_request = SimpleNamespace(client=SimpleNamespace(host="10.0.0.9"))

    with pytest.raises(AppError) as exc_info:
        system.open_terminal(remote_request)

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "TERMINAL_LOCAL_ONLY"


def test_launch_requires_claude_in_path(monkeypatch):
    monkeypatch.setattr(terminal.shutil, "which", lambda name: None)

    with pytest.raises(AppError) as exc_info:
        terminal.launch_claude_terminal(system.PROJECT_DIR)

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "CLAUDE_NOT_FOUND"


def test_launch_prefers_windows_terminal(monkeypatch, tmp_path):
    recorded: dict = {}
    wt_path = r"D:\WindowsTerminal\wt.exe"

    def fake_popen(command, **kwargs):
        recorded["command"] = command
        recorded["kwargs"] = kwargs
        return SimpleNamespace(pid=1)

    monkeypatch.setattr(terminal.shutil, "which", _which_claude_only)
    monkeypatch.setattr(terminal, "find_windows_terminal", lambda: wt_path)
    monkeypatch.setattr(terminal.subprocess, "Popen", fake_popen)

    launch = terminal.launch_claude_terminal(tmp_path)

    assert launch == terminal.TerminalLaunch(
        terminal="windows-terminal", directory=str(tmp_path)
    )
    assert recorded["command"] == [
        wt_path,
        "-d",
        str(tmp_path),
        "cmd.exe",
        "/k",
        "claude",
    ]
    assert recorded["kwargs"]["cwd"] == str(tmp_path)
    assert recorded["kwargs"]["creationflags"] == terminal.subprocess.CREATE_NO_WINDOW


def test_launch_falls_back_to_cmd(monkeypatch, tmp_path):
    recorded: dict = {}

    def fake_popen(command, **kwargs):
        recorded["command"] = command
        recorded["kwargs"] = kwargs
        return SimpleNamespace(pid=1)

    monkeypatch.setattr(terminal.shutil, "which", _which_claude_only)
    monkeypatch.setattr(terminal, "find_windows_terminal", lambda: None)
    monkeypatch.setattr(terminal.subprocess, "Popen", fake_popen)

    launch = terminal.launch_claude_terminal(tmp_path)

    assert launch == terminal.TerminalLaunch(terminal="cmd", directory=str(tmp_path))
    assert recorded["command"] == ["cmd.exe", "/k", "claude"]
    assert recorded["kwargs"]["cwd"] == str(tmp_path)
    assert recorded["kwargs"]["creationflags"] == terminal.subprocess.CREATE_NEW_CONSOLE


def test_launch_reports_popen_failure(monkeypatch, tmp_path):
    def fake_popen(command, **kwargs):
        raise OSError("无法创建控制台")

    monkeypatch.setattr(terminal.shutil, "which", _which_claude_only)
    monkeypatch.setattr(terminal, "find_windows_terminal", lambda: None)
    monkeypatch.setattr(terminal.subprocess, "Popen", fake_popen)

    with pytest.raises(AppError) as exc_info:
        terminal.launch_claude_terminal(tmp_path)

    assert exc_info.value.status_code == 500
    assert exc_info.value.code == "TERMINAL_LAUNCH_FAILED"


def test_find_windows_terminal_prefers_env(monkeypatch, tmp_path):
    wt = tmp_path / "wt.exe"
    wt.write_text("", encoding="utf-8")
    monkeypatch.setenv("WINDOWS_TERMINAL_EXECUTABLE", str(wt))
    monkeypatch.setattr(terminal, "WINDOWS_TERMINAL_EXECUTABLE", tmp_path / "no.exe")

    assert terminal.find_windows_terminal() == str(wt)


def test_find_windows_terminal_uses_configured_path(monkeypatch, tmp_path):
    wt = tmp_path / "wt.exe"
    wt.write_text("", encoding="utf-8")
    monkeypatch.delenv("WINDOWS_TERMINAL_EXECUTABLE", raising=False)
    monkeypatch.setattr(terminal, "WINDOWS_TERMINAL_EXECUTABLE", wt)
    monkeypatch.setattr(
        terminal.shutil,
        "which",
        lambda name: pytest.fail("配置路径存在时不应再查 PATH"),
    )

    assert terminal.find_windows_terminal() == str(wt)


def test_find_windows_terminal_falls_back_to_path(monkeypatch, tmp_path):
    missing = tmp_path / "missing.exe"
    monkeypatch.delenv("WINDOWS_TERMINAL_EXECUTABLE", raising=False)
    monkeypatch.setattr(terminal, "WINDOWS_TERMINAL_EXECUTABLE", missing)
    monkeypatch.setattr(
        terminal.shutil,
        "which",
        lambda name: r"C:\Tools\wt.exe" if name in ("wt", "wt.exe") else None,
    )

    assert terminal.find_windows_terminal() == r"C:\Tools\wt.exe"


def test_find_windows_terminal_uses_store_alias(monkeypatch, tmp_path):
    alias = tmp_path / "Microsoft" / "WindowsApps" / "wt.exe"
    alias.parent.mkdir(parents=True)
    alias.write_text("", encoding="utf-8")
    monkeypatch.delenv("WINDOWS_TERMINAL_EXECUTABLE", raising=False)
    monkeypatch.setattr(terminal, "WINDOWS_TERMINAL_EXECUTABLE", tmp_path / "no.exe")
    monkeypatch.setattr(terminal.shutil, "which", lambda name: None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert terminal.find_windows_terminal() == str(alias)


def test_find_windows_terminal_returns_none_when_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("WINDOWS_TERMINAL_EXECUTABLE", raising=False)
    monkeypatch.setattr(terminal, "WINDOWS_TERMINAL_EXECUTABLE", Path(tmp_path) / "no.exe")
    monkeypatch.setattr(terminal.shutil, "which", lambda name: None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))

    assert terminal.find_windows_terminal() is None
