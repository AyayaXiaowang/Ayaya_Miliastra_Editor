from __future__ import annotations

from app.automation.config.config_node_steps import compute_regular_param_click_editor_by_port_gap


class _Port:
    def __init__(self, bbox):  # noqa: ANN001
        self.bbox = bbox


def test_compute_regular_param_click_editor_by_port_gap_returns_point_when_gap_enough() -> None:
    node_bbox = (0, 0, 200, 200)
    current_port = _Port((10, 10, 15, 13))
    # 当前端口 bottom=23；下一端口 top=36；gap=13（恰好容得下一行端口高度）
    next_port = _Port((10, 36, 15, 13))

    pt = compute_regular_param_click_editor_by_port_gap(node_bbox, current_port, next_port)

    # base=(x+7,y+6)=(17,16) → click=(+2*w,+1*h)=(47,29)
    assert pt == (47, 29)


def test_compute_regular_param_click_editor_by_port_gap_returns_none_when_gap_insufficient() -> None:
    node_bbox = (0, 0, 200, 200)
    current_port = _Port((10, 10, 15, 13))
    # bottom=23；next top=30；gap=7 < port_h(13)
    next_port = _Port((10, 30, 15, 13))

    # gap 不足：输入框在当前行右侧 → 仅右移 2*w
    assert compute_regular_param_click_editor_by_port_gap(node_bbox, current_port, next_port) == (47, 16)


def test_compute_regular_param_click_editor_by_port_gap_uses_node_bottom_when_no_next_port() -> None:
    node_bbox = (0, 0, 200, 100)
    current_port = _Port((10, 60, 15, 13))

    pt = compute_regular_param_click_editor_by_port_gap(node_bbox, current_port, None)

    # base=(17,66) → click=(47,79)
    assert pt == (47, 79)


