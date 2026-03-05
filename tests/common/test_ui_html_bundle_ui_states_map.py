from __future__ import annotations

from pathlib import Path

from app.ui.controllers.ui_html_bundle_importer import _build_ui_states_payload_from_bundle


def test_build_ui_states_payload_from_bundle() -> None:
    # Arrange: bundle payload: 1 group, 2 states
    bundle_payload = {
        "bundle_type": "ui_workbench_ui_layout_bundle",
        "bundle_version": 1,
        "layout": {"layout_id": "layout_x", "layout_name": "HTML导入_界面布局"},
        "templates": [
            {
                "template_id": "t0",
                "template_name": "t0",
                "widgets": [
                    {
                        "widget_id": "w0",
                        "ui_key": "ui_key:demo__rect__state_a",
                        "__ui_state_group": "demo_group",
                        "__ui_state": "a",
                        "__ui_state_default": True,
                    },
                    {
                        "widget_id": "w1",
                        "ui_key": "ui_key:demo__rect__state_b",
                        "__ui_state_group": "demo_group",
                        "__ui_state": "b",
                        "__ui_state_default": False,
                    },
                ],
            }
        ],
    }

    # Act
    payload = _build_ui_states_payload_from_bundle(
        workspace_root=Path(".").resolve(),
        package_id="测试项目",
        source_html_relpath="管理配置/UI源码/ceshi.html",
        layout_id="layout_html__demo",
        layout_name="关卡选择",
        bundle_payload=bundle_payload,
    )

    # Assert
    groups = payload["ui_state_groups"]
    assert isinstance(groups, list)
    assert len(groups) == 1
    assert groups[0]["group"] == "demo_group"
    states = groups[0]["states"]
    assert [s["state"] for s in states] == ["a", "b"]
    assert [s["is_default"] for s in states] == [True, False]
    assert states[0]["ui_keys"] == ["ui_key:demo__rect__state_a"]
    assert states[1]["ui_keys"] == ["ui_key:demo__rect__state_b"]

