from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, List, Optional

from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir

from .common import _parse_float_pair


def _command_ui_patch_item_displays(arguments: argparse.Namespace) -> None:
    import json

    from ugc_file_tools.ui_patchers.misc.item_display_variants import (
        ItemDisplayVariantPatch,
        apply_item_display_variant_patches_in_gil,
    )

    patch_json_path = Path(str(arguments.patch_json_file)).resolve()
    if not patch_json_path.is_file():
        raise FileNotFoundError(str(patch_json_path))

    patch_object = json.loads(patch_json_path.read_text(encoding="utf-8"))
    if isinstance(patch_object, dict):
        patch_list = patch_object.get("patches")
    else:
        patch_list = patch_object

    if not isinstance(patch_list, list) or not patch_list:
        raise ValueError("patch-json 必须是 list[patch]，或 {'patches': list[patch]} 且非空")

    def _parse_optional_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        # bool 是 int 的子类：这里必须显式排除
        if isinstance(value, bool):
            raise ValueError("int 字段不允许 bool（请用 0/1 或显式整数）")
        if isinstance(value, int):
            return int(value)
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            text = value.strip()
            if text in {"", "."}:
                return None
            if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
                return int(text)
            raise ValueError(f"非数字字符串：{value!r}（请直接提供整数 code）")
        if isinstance(value, dict):
            if "code" in value:
                return _parse_optional_int(value.get("code"))
        raise ValueError(f"无法解析为 int：{value!r}")

    def _parse_optional_bool(value: Any) -> Optional[bool]:
        if value is None:
            return None
        if isinstance(value, bool):
            return bool(value)
        raise ValueError(f"无法解析为 bool：{value!r}（请用 true/false）")

    def _parse_optional_text(value: Any) -> Optional[str]:
        if value is None:
            return None
        return str(value)

    patches: List[ItemDisplayVariantPatch] = []
    for item in patch_list:
        if not isinstance(item, dict):
            raise TypeError("patch item must be dict")

        guid_value = item.get("guid")
        if not isinstance(guid_value, int):
            raise ValueError("patch item missing int guid")

        patches.append(
            ItemDisplayVariantPatch(
                guid=int(guid_value),
                display_type=(_parse_optional_text(item.get("display_type")) if "display_type" in item else None),
                can_interact=(_parse_optional_bool(item.get("can_interact")) if "can_interact" in item else None),
                keybind_kbm_code=(
                    _parse_optional_int(item.get("keybind_kbm_code"))
                    if "keybind_kbm_code" in item
                    else _parse_optional_int(item.get("keybind_kbm"))
                    if "keybind_kbm" in item
                    else None
                ),
                keybind_gamepad_code=(
                    _parse_optional_int(item.get("keybind_gamepad_code"))
                    if "keybind_gamepad_code" in item
                    else _parse_optional_int(item.get("keybind_gamepad"))
                    if "keybind_gamepad" in item
                    else None
                ),
                config_id_variable=(
                    _parse_optional_text(item.get("config_id_variable")) if "config_id_variable" in item else None
                ),
                cooldown_seconds_variable=(
                    _parse_optional_text(item.get("cooldown_seconds_variable"))
                    if "cooldown_seconds_variable" in item
                    else None
                ),
                use_count_enabled=(
                    _parse_optional_bool(item.get("use_count_enabled")) if "use_count_enabled" in item else None
                ),
                hide_when_empty_count=(
                    _parse_optional_bool(item.get("hide_when_empty_count"))
                    if "hide_when_empty_count" in item
                    else None
                ),
                use_count_variable=(
                    _parse_optional_text(item.get("use_count_variable")) if "use_count_variable" in item else None
                ),
                quantity_variable=(
                    _parse_optional_text(item.get("quantity_variable")) if "quantity_variable" in item else None
                ),
                show_quantity=(_parse_optional_bool(item.get("show_quantity")) if "show_quantity" in item else None),
                hide_when_zero=(_parse_optional_bool(item.get("hide_when_zero")) if "hide_when_zero" in item else None),
                no_equipment_behavior_code=(
                    _parse_optional_int(item.get("no_equipment_behavior_code"))
                    if "no_equipment_behavior_code" in item
                    else None
                ),
            )
        )

    output_gil_path = resolve_output_file_path_in_out_dir(Path(arguments.output_gil_file))
    output_gil_path.parent.mkdir(parents=True, exist_ok=True)

    canvas_size = _parse_float_pair(str(arguments.canvas_size))
    report = apply_item_display_variant_patches_in_gil(
        input_gil_file_path=Path(arguments.input_gil_file),
        output_gil_file_path=output_gil_path,
        patches=patches,
        verify_with_dll_dump=bool(arguments.verify),
        verify_canvas_size=canvas_size,
    )

    report_path_text = str(arguments.report_json or "").strip()
    if report_path_text != "":
        report_path = resolve_output_file_path_in_out_dir(Path(report_path_text))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    verify = report.get("verify")
    mismatch_total = verify.get("mismatch_total") if isinstance(verify, dict) else None

    print("=" * 80)
    print("道具展示写回完成：")
    print(f"- input:  {report.get('input_gil')}")
    print(f"- output: {report.get('output_gil')}")
    print(f"- patched: {report.get('patched_total')}/{report.get('requested_patch_total')}")
    if mismatch_total is not None:
        print(f"- verify_mismatch_total: {mismatch_total}")
    if report_path_text != "":
        print(f"- report_json: {str(report_path.resolve())}")
    print("=" * 80)


def register_ui_item_displays_subcommands(ui_subparsers: argparse._SubParsersAction) -> None:
    patch_item_displays_parser = ui_subparsers.add_parser(
        "patch-item-displays",
        help="按 JSON 批量写回道具展示控件（按 guid 定位；支持按键码/展示类型/变量绑定等）。",
    )
    patch_item_displays_parser.add_argument("input_gil_file", help="输入 .gil 文件路径")
    patch_item_displays_parser.add_argument("output_gil_file", help="输出 .gil 文件路径（建议不要覆盖原文件）")
    patch_item_displays_parser.add_argument(
        "--patch-json",
        dest="patch_json_file",
        required=True,
        help=(
            "patch JSON 文件路径：list[patch] 或 {'patches': list[patch]}。\n"
            "每个 patch 至少包含 guid(int)。可选字段：\n"
            "- display_type(str)\n"
            "- can_interact(bool)\n"
            "- keybind_kbm_code(int) / keybind_kbm(int|{'code':int})\n"
            "- keybind_gamepad_code(int) / keybind_gamepad(int|{'code':int})\n"
            "- config_id_variable/cooldown_seconds_variable/use_count_variable/quantity_variable(str)\n"
            "- use_count_enabled/hide_when_empty_count/show_quantity/hide_when_zero(bool)\n"
            "- no_equipment_behavior_code(int)\n"
            "变量引用格式：'玩家自身.变量名' / '关卡.变量名' / '.'(不绑定)。"
        ),
    )
    patch_item_displays_parser.add_argument(
        "--canvas-size",
        dest="canvas_size",
        default="1600,900",
        help="可选：用于解析 RectTransform 的画布尺寸（用于 verify dump 对齐），格式 'w,h'。",
    )
    patch_item_displays_parser.add_argument(
        "--verify",
        dest="verify",
        action="store_true",
        help="可选：写回后重新 dump-item-displays 并对 patch 字段做断言校验。",
    )
    patch_item_displays_parser.add_argument(
        "--report-json",
        dest="report_json",
        default="",
        help="可选：写回报告输出路径（JSON）。",
    )

    patch_item_displays_parser.set_defaults(entrypoint=_command_ui_patch_item_displays)


