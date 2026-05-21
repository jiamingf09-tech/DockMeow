"""Tests for subprocess helpers used by bundled command-line tools."""

from __future__ import annotations

from dockmeow.utils import subprocess as process_utils


def test_hidden_subprocess_kwargs_non_windows(monkeypatch) -> None:
    monkeypatch.setattr(process_utils.sys, "platform", "darwin")

    assert process_utils.hidden_subprocess_kwargs() == {}


def test_hidden_subprocess_kwargs_windows(monkeypatch) -> None:
    class FakeStartupInfo:
        def __init__(self) -> None:
            self.dwFlags = 0
            self.wShowWindow = None

    monkeypatch.setattr(process_utils.sys, "platform", "win32")
    monkeypatch.setattr(
        process_utils.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False
    )
    monkeypatch.setattr(
        process_utils.subprocess, "STARTF_USESHOWWINDOW", 0x00000001, raising=False
    )
    monkeypatch.setattr(process_utils.subprocess, "SW_HIDE", 0, raising=False)
    monkeypatch.setattr(
        process_utils.subprocess, "STARTUPINFO", FakeStartupInfo, raising=False
    )

    kwargs = process_utils.hidden_subprocess_kwargs()

    assert kwargs["creationflags"] == 0x08000000
    assert kwargs["startupinfo"].dwFlags & 0x00000001
    assert kwargs["startupinfo"].wShowWindow == 0
