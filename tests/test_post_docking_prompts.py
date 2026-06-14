from __future__ import annotations

from dockmeow.ui.post_docking_prompts import (
    disable_star_prompt,
    record_successful_docking,
)


class MemorySettings:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def value(self, key: str, defaultValue=None, type=None):
        return self.values.get(key, defaultValue)

    def setValue(self, key: str, value) -> None:
        self.values[key] = value


def test_open_source_notice_is_only_planned_once() -> None:
    settings = MemorySettings()

    first = record_successful_docking(settings)
    second = record_successful_docking(settings)

    assert first.completed_count == 1
    assert first.show_open_source_notice is True
    assert second.completed_count == 2
    assert second.show_open_source_notice is False


def test_star_prompt_only_uses_requested_milestones() -> None:
    settings = MemorySettings()
    star_counts: list[int] = []

    for _ in range(100):
        plan = record_successful_docking(settings)
        if plan.show_star_prompt:
            star_counts.append(plan.completed_count)

    assert star_counts == [10, 50, 100]


def test_star_prompt_can_be_disabled_after_first_milestone() -> None:
    settings = MemorySettings()

    for _ in range(10):
        plan = record_successful_docking(settings)
    assert plan.completed_count == 10
    assert plan.show_star_prompt is True

    disable_star_prompt(settings)

    for _ in range(90):
        plan = record_successful_docking(settings)
        assert plan.show_star_prompt is False
