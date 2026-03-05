from __future__ import annotations

from PIL import Image

from app.automation.config.config_node_steps import handle_regular_param_with_warning


class _DummyExecutor:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def log(self, message: str, log_callback=None) -> None:  # noqa: ANN001
        self.messages.append(str(message))
        if log_callback is not None:
            log_callback(message)


def test_handle_regular_param_with_warning_returns_false_when_search_region_is_none() -> None:
    executor = _DummyExecutor()
    screenshot = Image.new("RGB", (10, 10), (0, 0, 0))

    ok = handle_regular_param_with_warning(
        executor,
        screenshot,
        None,
        "123",
        None,
        None,
        None,
        None,
    )

    assert ok is False
    assert any("未计算到 Warning 搜索区域" in msg for msg in executor.messages)


