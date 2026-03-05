from __future__ import annotations

from unittest.mock import patch

from PIL import Image

from app.automation.config.config_params import execute_config_node_merged
from engine.graph.models.graph_model import GraphModel


class _DummyExecutor:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def log(self, message: str, log_callback=None) -> None:  # noqa: ANN001
        self.messages.append(str(message))
        if log_callback is not None:
            log_callback(message)

    def ensure_program_point_visible(self, *_args, **_kwargs) -> None:  # noqa: ANN001
        return

    def get_node_def_for_model(self, _node):  # noqa: ANN001
        return None


class _Port:
    def __init__(self, *, name_cn: str, bbox: tuple[int, int, int, int], center: tuple[int, int]):  # noqa: D401
        self.name_cn = name_cn
        self.bbox = bbox
        self.center = center
        self.side = "left"
        self.kind = "data"
        self.index = 0


class _DummySnapshotCache:
    def __init__(self, _executor, _node, _log_callback) -> None:  # noqa: ANN001
        self.screenshot = Image.new("RGB", (240, 180), (0, 0, 0))
        self.node_bbox = (0, 0, 200, 160)
        self.ports = [
            _Port(name_cn="A", bbox=(10, 10, 15, 13), center=(17, 16)),
            _Port(name_cn="B", bbox=(10, 36, 15, 13), center=(17, 42)),
        ]

    def ensure(self, *, reason: str, require_bbox: bool) -> bool:
        _ = (reason, require_bbox)
        return True

    def mark_dirty(self, *, require_bbox: bool = False) -> None:
        _ = require_bbox
        return


def test_execute_config_node_merged_regular_param_uses_port_gap_method() -> None:
    """
    轻量集成回归：
    - 普通参数（非布尔/枚举/三维向量）必须走“端口间距法”输入，不再走端口偏移 fallback。
    """
    graph_model = GraphModel(graph_id="g1")
    node = graph_model.add_node(
        title="测试节点",
        category="测试",
        input_names=["A", "B"],
        output_names=[],
        pos=(100.0, 200.0),
    )
    todo_item = {
        "node_id": node.id,
        "params": [{"param_name": "A", "param_value": "123"}],
    }

    executor = _DummyExecutor()

    calls: list[dict] = []

    def _dummy_locate_input_port(*_args, **_kwargs):  # noqa: ANN001
        return (17, 16)

    def _dummy_handle_regular_param_by_port_gap(  # noqa: ANN001
        _executor,
        _screenshot,
        _node_bbox,
        _current_port,
        _next_port,
        _param_value,
        _pause_hook,
        _allow_continue,
        _log_callback,
        _visual_callback,
        **_kwargs,
    ) -> bool:
        calls.append({"ok": True})
        return True

    def _dummy_handle_regular_param_fallback(*_args, **_kwargs) -> bool:  # noqa: ANN001
        raise AssertionError("普通参数不应再调用 handle_regular_param_fallback")

    with patch("app.automation.config.config_params.NodePortsSnapshotCache", _DummySnapshotCache), patch(
        "app.automation.config.config_params.visualize_node_and_ports",
        lambda *_args, **_kwargs: None,  # noqa: ANN001
    ), patch(
        "app.automation.config.config_params.log_port_candidates_debug",
        lambda *_args, **_kwargs: None,  # noqa: ANN001
    ), patch(
        "app.automation.config.config_params.locate_input_port",
        _dummy_locate_input_port,
    ), patch(
        "app.automation.config.config_params.handle_regular_param_by_port_gap",
        _dummy_handle_regular_param_by_port_gap,
    ), patch(
        "app.automation.config.config_params.handle_regular_param_fallback",
        _dummy_handle_regular_param_fallback,
    ):
        ok = execute_config_node_merged(
            executor,
            todo_item,
            graph_model,
            log_callback=None,
            pause_hook=None,
            allow_continue=None,
            visual_callback=None,
        )

    assert ok is True
    assert len(calls) == 1


def test_execute_config_node_merged_regular_param_port_gap_failure_does_not_fallback() -> None:
    """
    轻量集成回归：
    - 普通参数端口间距法失败时应直接失败返回 False；不应调用端口偏移 fallback。
    """
    graph_model = GraphModel(graph_id="g1")
    node = graph_model.add_node(
        title="测试节点",
        category="测试",
        input_names=["A", "B"],
        output_names=[],
        pos=(100.0, 200.0),
    )
    todo_item = {
        "node_id": node.id,
        "params": [{"param_name": "A", "param_value": "123"}],
    }

    executor = _DummyExecutor()

    def _dummy_locate_input_port(*_args, **_kwargs):  # noqa: ANN001
        return (17, 16)

    def _dummy_handle_regular_param_by_port_gap(  # noqa: ANN001
        _executor,
        _screenshot,
        _node_bbox,
        _current_port,
        _next_port,
        _param_value,
        _pause_hook,
        _allow_continue,
        _log_callback,
        _visual_callback,
        **_kwargs,
    ) -> bool:
        return False

    def _dummy_handle_regular_param_fallback(*_args, **_kwargs) -> bool:  # noqa: ANN001
        raise AssertionError("普通参数端口间距法失败时也不应调用 handle_regular_param_fallback")

    with patch("app.automation.config.config_params.NodePortsSnapshotCache", _DummySnapshotCache), patch(
        "app.automation.config.config_params.visualize_node_and_ports",
        lambda *_args, **_kwargs: None,  # noqa: ANN001
    ), patch(
        "app.automation.config.config_params.log_port_candidates_debug",
        lambda *_args, **_kwargs: None,  # noqa: ANN001
    ), patch(
        "app.automation.config.config_params.locate_input_port",
        _dummy_locate_input_port,
    ), patch(
        "app.automation.config.config_params.handle_regular_param_by_port_gap",
        _dummy_handle_regular_param_by_port_gap,
    ), patch(
        "app.automation.config.config_params.handle_regular_param_fallback",
        _dummy_handle_regular_param_fallback,
    ):
        ok = execute_config_node_merged(
            executor,
            todo_item,
            graph_model,
            log_callback=None,
            pause_hook=None,
            allow_continue=None,
            visual_callback=None,
        )

    assert ok is False
