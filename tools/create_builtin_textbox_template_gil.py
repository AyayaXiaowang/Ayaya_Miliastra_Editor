from __future__ import annotations

"""
create_builtin_textbox_template_gil.py

目的：为对外仓库提供一个可公开版本化的 TextBox 模板 `.gil`，避免 UI Workbench 导出链路依赖
`ugc_file_tools/save/**` 的本地真源样本库。

做法：
- 以 `builtin_resources/空的界面控件组/进度条样式.gil` 的容器格式为基底；
- 从其 `root4/9` 里挑选一个“可用的 RectTransform record”做骨架；
- 构造一个包含 node19(TextBox 文本配置) 的 record；
- 输出最小化 payload_root，仅保留 `field_9`（UI 段）。

运行：
  - 预演：python -X utf8 -m tools.create_builtin_textbox_template_gil
  - 写盘：python -X utf8 -m tools.create_builtin_textbox_template_gil --apply
"""

import argparse
import copy
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple


SECTION_9 = "9"


@dataclass(frozen=True, slots=True)
class CreateTextboxTemplatePlan:
    source_gil_rel_path: str
    output_gil_rel_path: str


PLAN = CreateTextboxTemplatePlan(
    source_gil_rel_path="private_extensions/ugc_file_tools/builtin_resources/空的界面控件组/进度条样式.gil",
    output_gil_rel_path="private_extensions/ugc_file_tools/builtin_resources/空的界面控件组/文本框样式.gil",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    raise TypeError(f"{label} must be Mapping, got {type(value).__name__}")


def _extract_ui_record_list_from_dump(dump_obj: Dict[str, Any]) -> List[Any]:
    from ugc_file_tools.ui.readable_dump import extract_ui_record_list

    return extract_ui_record_list(dump_obj)


def _choose_rect_skeleton_record(dump_obj: Dict[str, Any]) -> Dict[str, Any]:
    """
    选择一个含 RectTransform(state0) 且无 children 的 record 作为骨架。
    优先复用 progressbar 选择逻辑，保证 record shape 接近真实可克隆控件实例。
    """
    from ugc_file_tools.ui_patchers.web_ui.web_ui_import_progressbar import choose_progressbar_record_template
    from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import get_children_guids_from_parent_record

    records = _extract_ui_record_list_from_dump(dump_obj)
    best = choose_progressbar_record_template(records)
    if best is not None:
        # 保险：确保无 children
        children = get_children_guids_from_parent_record(best)
        if not children:
            return dict(best)

    # 兜底：任意 record（含 RectTransform）且无 children
    from ugc_file_tools.ui_patchers.web_ui.web_ui_import_rect import has_rect_transform_state

    for rec in records:
        if not isinstance(rec, dict):
            continue
        if not has_rect_transform_state(rec, state_index=0):
            continue
        children = get_children_guids_from_parent_record(rec)
        if children:
            continue
        return dict(rec)
    raise RuntimeError("未找到可用的 RectTransform record 作为 TextBox 模板骨架（内部错误）。")


def _set_widget_name_in_place(record: Dict[str, Any], *, name: str) -> None:
    component_list = record.get("505")
    if not isinstance(component_list, list) or not component_list:
        raise ValueError("record missing component_list at field 505")
    comp0 = component_list[0]
    if not isinstance(comp0, dict):
        raise ValueError("record component_list[0] must be dict")
    node12 = comp0.get("12")
    if not isinstance(node12, dict):
        node12 = {}
        comp0["12"] = node12
    node12["501"] = str(name)


def _clear_children_in_place(record: Dict[str, Any]) -> None:
    # children 在 record.field_503 中，以 "<binary_data> ..." 形式存在；缺失视为无 children
    record.pop("503", None)


def _drop_nonessential_components_keep_name_rect(record: Dict[str, Any]) -> None:
    """
    为避免携带进度条/其它控件的 binding 组件，尽量只保留：
    - component[0]：name
    - component[2]：RectTransform
    其它组件全部丢弃（会显著降低“错误控件形态混入 textbox 模板”的风险）。
    """
    component_list = record.get("505")
    if not isinstance(component_list, list):
        raise ValueError("record missing component_list at field 505")
    if len(component_list) < 3:
        raise ValueError("record.component_list too short (<3)")
    name_comp = component_list[0]
    rect_comp = component_list[2]
    record["505"] = [name_comp, {}, rect_comp]


def _append_textbox_node19_component(record: Dict[str, Any]) -> None:
    """
    添加一个包含 node19 的组件：
    - nested['19']['505']['501'] 为文本内容
    - nested['19']['502'] 为字号
    """
    component_list = record.get("505")
    if not isinstance(component_list, list):
        raise ValueError("record missing component_list at field 505")
    node19: Dict[str, Any] = {"502": 16, "505": {"501": ""}}
    component_list.append({"503": {"19": node19}})


def build_textbox_template_payload_root(*, source_gil_path: Path) -> Dict[str, Any]:
    from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import dump_gil_to_raw_json_object

    dump_obj = dump_gil_to_raw_json_object(Path(source_gil_path).resolve())
    skeleton = _choose_rect_skeleton_record(dump_obj)
    skeleton_copy = copy.deepcopy(skeleton)

    rec = copy.deepcopy(skeleton)
    _clear_children_in_place(rec)
    _drop_nonessential_components_keep_name_rect(rec)
    _set_widget_name_in_place(rec, name="文本框")
    _append_textbox_node19_component(rec)

    # 从 source dump 中取 root4/9 的 registry(501) 作为占位（保持形态正确），并用仅含 1 条 record 的 list
    payload_root = dump_obj.get("4")
    payload_root_map = _ensure_mapping(payload_root, label="dump['4']")
    node9 = payload_root_map.get("9")
    node9_map = _ensure_mapping(node9, label="dump['4']['9']")

    registry = node9_map.get("501")
    if registry is None:
        registry = []

    # 关键：部分 dump-json 实现会在 repeated message 只有 1 个元素时把其折叠为 dict，
    # 这会导致 `extract_ui_record_list` fail-fast（期望 list）。
    # 因此确保 record_list 至少 2 个元素，稳定保持为 list 形态。
    minimized_node9 = {"501": registry, "502": [rec, skeleton_copy]}
    return {SECTION_9: minimized_node9}


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="写盘生成 builtin textbox 模板 .gil")
    args = parser.parse_args(argv)

    repo_root = _repo_root()
    private_extensions_root = (repo_root / "private_extensions").resolve()
    if not private_extensions_root.is_dir():
        raise FileNotFoundError(str(private_extensions_root))
    sys.path.insert(0, str(private_extensions_root))

    source_path = (repo_root / PLAN.source_gil_rel_path).resolve()
    if not source_path.is_file():
        raise FileNotFoundError(str(source_path))
    out_path = (repo_root / PLAN.output_gil_rel_path).resolve()

    from ugc_file_tools.gil_dump_codec.gil_container import build_gil_file_bytes_from_payload, read_gil_container_spec
    from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message

    container_spec = read_gil_container_spec(source_path)
    payload_root = build_textbox_template_payload_root(source_gil_path=source_path)
    payload_bytes = encode_message(dict(payload_root))
    out_bytes = build_gil_file_bytes_from_payload(payload_bytes=payload_bytes, container_spec=container_spec)

    print(f"[source] {source_path.as_posix()}")
    print(f"[output] {out_path.as_posix()}")
    print(f"[size] {len(out_bytes)} bytes")
    if bool(args.apply):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(out_bytes)
        print("[apply] written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

