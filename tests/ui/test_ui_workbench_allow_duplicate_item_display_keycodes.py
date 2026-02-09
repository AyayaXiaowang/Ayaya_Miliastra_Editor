from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_web_ui_import_allows_duplicate_item_display_keybind_codes(tmp_path: Path, monkeypatch) -> None:
    """回归：同一页面内“可交互道具展示”的按键码即使重复，也不应阻断导出。

    说明：
    - 该链路属于私有扩展 ugc_file_tools；若目录缺失则跳过。
    - 这里只验证“写回端不抛异常 + report 给出 warning”，不要求 DLL verify。
    """
    repo_root = Path(__file__).resolve().parents[2]
    private_extensions_root = repo_root / "private_extensions"
    ugc_tools_root = private_extensions_root / "ugc_file_tools"
    if not ugc_tools_root.is_dir():
        pytest.skip("ugc_file_tools 私有扩展不在当前工作区中，跳过用例。")

    monkeypatch.syspath_prepend(str(private_extensions_root))

    from ugc_file_tools.ui_patchers.web_ui_import_main import import_web_ui_control_group_template_to_gil_layout

    base_gil = ugc_tools_root / "save" / "空的界面控件组" / "道具展示.gil"
    if not base_gil.is_file():
        pytest.skip("缺少道具展示基底存档样本（private_extensions/ugc_file_tools/save/空的界面控件组/道具展示.gil）。")

    template = {
        "template_id": "dup_keybind_codes",
        "template_name": "dup_keybind_codes",
        "widgets": [
            {
                "widget_type": "道具展示",
                "widget_id": "w1",
                "ui_key": "dup_keybind__w1",
                "widget_name": "按钮_道具展示_1",
                "layer_index": 10,
                "position": [100, 100],
                "size": [220, 64],
                "settings": {
                    "can_interact": True,
                    "display_type": "模板道具",
                    "keybind_kbm_code": 14,
                    "keybind_gamepad_code": 14,
                },
            },
            {
                "widget_type": "道具展示",
                "widget_id": "w2",
                "ui_key": "dup_keybind__w2",
                "widget_name": "按钮_道具展示_2",
                "layer_index": 9,
                "position": [100, 180],
                "size": [220, 64],
                "settings": {
                    "can_interact": True,
                    "display_type": "模板道具",
                    "keybind_kbm_code": 14,
                    "keybind_gamepad_code": 14,
                },
            },
        ],
    }

    template_path = tmp_path / "template.json"
    template_path.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")

    out_gil = tmp_path / "out.gil"
    registry_path = tmp_path / "ui_guid_registry.json"

    report = import_web_ui_control_group_template_to_gil_layout(
        input_gil_file_path=base_gil,
        output_gil_file_path=out_gil,
        template_json_file_path=template_path,
        target_layout_guid=None,
        new_layout_name="dup_keybind_codes_layout",
        base_layout_guid=None,
        empty_layout=False,
        clone_children=True,
        pc_canvas_size=(1600.0, 900.0),
        mobile_canvas_size=(1280.0, 720.0),
        enable_progressbars=False,
        enable_textboxes=False,
        progressbar_template_gil_file_path=None,
        textbox_template_gil_file_path=None,
        item_display_template_gil_file_path=base_gil,
        verify_with_dll_dump=False,
        ui_guid_registry_file_path=registry_path,
    )

    output_gil_path = Path(str(report.get("output_gil") or "")).resolve()
    assert output_gil_path.is_file()
    warnings = report.get("interactive_item_display_key_code_warnings")
    assert isinstance(warnings, list)
    assert any(w.get("warning") == "duplicate_keybind_code_allowed" for w in warnings)

