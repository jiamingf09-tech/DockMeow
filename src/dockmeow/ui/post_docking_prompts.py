"""Post-docking user prompts and their persisted state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

REPO_URL = "https://github.com/jiamingf09-tech/DockMeow"
ISSUES_URL = f"{REPO_URL}/issues"
STAR_PROMPT_MILESTONES = frozenset({10, 50, 100})

_DOCKING_COUNT_KEY = "post_docking/completed_count"
_OPEN_SOURCE_NOTICE_SHOWN_KEY = "post_docking/open_source_notice_shown"
_STAR_PROMPT_DISABLED_KEY = "post_docking/star_prompt_disabled"
_STAR_PROMPT_SHOWN_MILESTONES_KEY = "post_docking/star_prompt_shown_milestones"


class SettingsLike(Protocol):
    def value(self, key: str, defaultValue: Any = None, type: Any = None) -> Any:
        ...

    def setValue(self, key: str, value: Any) -> None:
        ...


@dataclass(frozen=True)
class PostDockingPromptPlan:
    """Prompt decisions for one completed docking run."""

    completed_count: int
    show_open_source_notice: bool
    show_star_prompt: bool


def settings() -> QSettings:
    """Return DockMeow's machine-local prompt settings."""

    return QSettings("DockMeow", "DockMeow")


def record_successful_docking(
    prompt_settings: SettingsLike | None = None,
) -> PostDockingPromptPlan:
    """Increment completion count and decide which post-docking prompts to show."""

    prompt_settings = prompt_settings or settings()
    completed_count = _read_int(prompt_settings, _DOCKING_COUNT_KEY) + 1
    prompt_settings.setValue(_DOCKING_COUNT_KEY, completed_count)

    show_open_source_notice = not _read_bool(
        prompt_settings,
        _OPEN_SOURCE_NOTICE_SHOWN_KEY,
    )
    if show_open_source_notice:
        prompt_settings.setValue(_OPEN_SOURCE_NOTICE_SHOWN_KEY, True)

    shown_milestones = _read_milestones(prompt_settings)
    show_star_prompt = (
        completed_count in STAR_PROMPT_MILESTONES
        and not _read_bool(prompt_settings, _STAR_PROMPT_DISABLED_KEY)
        and completed_count not in shown_milestones
    )
    if show_star_prompt:
        shown_milestones.add(completed_count)
        _write_milestones(prompt_settings, shown_milestones)

    return PostDockingPromptPlan(
        completed_count=completed_count,
        show_open_source_notice=show_open_source_notice,
        show_star_prompt=show_star_prompt,
    )


def disable_star_prompt(prompt_settings: SettingsLike | None = None) -> None:
    """Persist the user's choice to hide future star/issue prompts."""

    (prompt_settings or settings()).setValue(_STAR_PROMPT_DISABLED_KEY, True)


def show_open_source_notice(parent: QWidget | None = None) -> None:
    """Show the one-time open-source/free-software notice."""

    dialog = _PromptDialog(
        title="DockMeow 免费开源提醒",
        body=(
            "<p>DockMeow 是在 GitHub 免费开源的软件：</p>"
            f'<p><a href="{REPO_URL}">{REPO_URL}</a></p>'
            "<p>如果您是付费得到的该软件，建议您寻找卖家退款。</p>"
        ),
        parent=parent,
    )
    dialog.exec()


def show_star_prompt(completed_count: int, parent: QWidget | None = None) -> bool:
    """Show the milestone feedback prompt.

    Returns:
        True when the user checked "do not show again".
    """

    dialog = _PromptDialog(
        title="喜欢 DockMeow 吗？",
        body=(
            f"<p>您已经完成 {completed_count} 次对接，欢迎告诉我们使用体验。</p>"
            "<p>如果 DockMeow 帮到了您，可以来 GitHub 点个 Star；如果遇到问题，"
            "也欢迎直接提 Issue：</p>"
            f'<p><a href="{REPO_URL}">打开 DockMeow 项目并点 Star</a><br>'
            f'<a href="{ISSUES_URL}">提交 Issue / 反馈建议</a></p>'
        ),
        show_never_again=True,
        parent=parent,
    )
    dialog.exec()
    return dialog.never_again_checked


class _PromptDialog(QDialog):
    def __init__(
        self,
        *,
        title: str,
        body: str,
        show_never_again: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.never_again_checked = False
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)

        label = QLabel(body)
        label.setWordWrap(True)
        label.setOpenExternalLinks(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        layout.addWidget(label)

        self._never_again: QCheckBox | None = None
        if show_never_again:
            self._never_again = QCheckBox("不再显示此提醒")
            layout.addWidget(self._never_again)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self._accept)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        if self._never_again is not None:
            self.never_again_checked = self._never_again.isChecked()
        self.accept()


def _read_bool(prompt_settings: SettingsLike, key: str) -> bool:
    value = prompt_settings.value(key, False)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _read_int(prompt_settings: SettingsLike, key: str) -> int:
    try:
        return int(prompt_settings.value(key, 0))
    except (TypeError, ValueError):
        return 0


def _read_milestones(prompt_settings: SettingsLike) -> set[int]:
    raw = str(prompt_settings.value(_STAR_PROMPT_SHOWN_MILESTONES_KEY, "") or "")
    milestones: set[int] = set()
    for part in raw.split(","):
        try:
            milestones.add(int(part))
        except ValueError:
            continue
    return milestones


def _write_milestones(prompt_settings: SettingsLike, milestones: set[int]) -> None:
    value = ",".join(str(item) for item in sorted(milestones))
    prompt_settings.setValue(_STAR_PROMPT_SHOWN_MILESTONES_KEY, value)
