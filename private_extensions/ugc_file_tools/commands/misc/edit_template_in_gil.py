from __future__ import annotations

"""
edit_template_in_gil.py

目标：
- 通过“DLL dump-json（数值键结构）→ 修改元件库模板 → protobuf-like 重编码 → 封装回 .gil”的方式，
  对 `.gil` 的元件库（payload_root['4']['1']）进行最小写回。

背景：
- pyugc 解码（dtype 驱动）非常适合“读”，但其 JSON key 会带 `@int/@string` 等注解，无法直接用于
  `gil_dump_codec.protobuf_like.encode_message(...)` 重编码；
- 因此写回沿用仓库既有实践：以 dump-json（数值键结构）作为可重编码的中间格式。

注意：
- 该脚本是“危险写盘”类工具：请务必备份输入 `.gil`，并输出到新文件名。
"""

import argparse
import copy
import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ugc_file_tools.gil_dump_codec.dump_gil_to_json import dump_gil_to_json
from ugc_file_tools.gil_dump_codec.gil_container import (
    build_gil_file_bytes_from_payload,
    read_gil_container_spec,
)
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.console_encoding import configure_console_encoding


def _dump_gil_to_raw_json_object(input_gil_file_path: Path) -> Dict[str, Any]:
    input_path = Path(input_gil_file_path).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    with tempfile.TemporaryDirectory(prefix="ugc_dump_") as temp_dir:
        raw_json_path = Path(temp_dir) / "dump.json"
        dump_gil_to_json(str(input_path), str(raw_json_path))
        raw_dump_object = json.loads(raw_json_path.read_text(encoding="utf-8"))

    if not isinstance(raw_dump_object, dict):
        raise ValueError("dump-json 顶层不是 dict")
    return raw_dump_object


def _get_payload_root(raw_dump_object: Dict[str, Any]) -> Dict[str, Any]:
    payload_root = raw_dump_object.get("4")
    if not isinstance(payload_root, dict):
        raise ValueError("dump-json 缺少根字段 '4'（期望为 dict）。")
    return payload_root


def _ensure_path_dict(root: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = root.get(key)
    if isinstance(value, dict):
        return value
    if value is None:
        new_value: Dict[str, Any] = {}
        root[key] = new_value
        return new_value
    raise ValueError(f"expected dict at key={key!r}, got {type(value).__name__}")


def _ensure_path_list_allow_scalar(root: Dict[str, Any], key: str) -> List[Any]:
    """
    dump-json 中 repeated 字段在“只有 1 个元素”时可能被输出为标量（int/dict/str）。
    这里将其统一为 list 视图，便于追加/遍历。
    """
    value = root.get(key)
    if isinstance(value, list):
        return value
    if value is None:
        new_value: List[Any] = []
        root[key] = new_value
        return new_value
    new_value = [value]
    root[key] = new_value
    return new_value


def _extract_first_int_from_repeated_field(node: Dict[str, Any], key: str) -> Optional[int]:
    value = node.get(key)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, list) and value and isinstance(value[0], int):
        return int(value[0])
    return None


def _find_template_entry(templates_list: List[Any], template_id_int: int) -> Dict[str, Any]:
    for item in templates_list:
        if not isinstance(item, dict):
            continue
        entry_id = _extract_first_int_from_repeated_field(item, "1")
        if entry_id == int(template_id_int):
            return item
    raise ValueError(f"未找到元件：template_id={template_id_int}")


def _set_template_id(entry: Dict[str, Any], template_id_int: int) -> None:
    entry["1"] = [int(template_id_int)]


def _set_template_name(entry: Dict[str, Any], name: str) -> None:
    meta_list = _ensure_path_list_allow_scalar(entry, "6")
    name_item: Optional[Dict[str, Any]] = None
    for item in meta_list:
        if not isinstance(item, dict):
            continue
        if item.get("1") == 1:
            name_item = item
            break
    if name_item is None:
        name_item = {"1": 1, "11": {"1": str(name)}}
        meta_list.insert(0, name_item)
        return

    container = name_item.get("11")
    if not isinstance(container, dict):
        container = {}
        name_item["11"] = container
    container["1"] = str(name)


_SECTION_KEY_BY_ID = {
    4: "14",  # 可见性（推断：模型可见性）
    5: "15",  # 原生碰撞（推断：初始生效/可攀爬）
    6: "16",  # 创建设置（推断：初始创建；该字段在样本中为“禁用创建”flag）
    8: "18",  # 负载优化（推断：超出范围不运行）
    12: "22",  # 阵营（推断：跟随默认/初始玩家阵营）
}


def _find_or_create_section(entry: Dict[str, Any], section_id_int: int) -> Dict[str, Any]:
    if section_id_int not in _SECTION_KEY_BY_ID:
        raise ValueError(f"unsupported section_id: {section_id_int}")
    section_key = _SECTION_KEY_BY_ID[section_id_int]

    section_list = _ensure_path_list_allow_scalar(entry, "7")
    for item in section_list:
        if not isinstance(item, dict):
            continue
        if item.get("1") != int(section_id_int):
            continue
        section_value = item.get(section_key)
        if isinstance(section_value, dict):
            return section_value
        if section_value is None:
            new_section: Dict[str, Any] = {}
            item[section_key] = new_section
            return new_section
        raise ValueError(
            f"unexpected section type: entry['7'] id={section_id_int} key={section_key} "
            f"type={type(section_value).__name__}"
        )

    new_item: Dict[str, Any] = {"1": int(section_id_int), section_key: {}}
    section_list.append(new_item)
    return new_item[section_key]


def _set_bool_flag_in_section(section: Dict[str, Any], key: str, enabled: bool) -> None:
    if enabled:
        section[key] = 1
    else:
        section.pop(key, None)


def apply_template_edits(
    *,
    entry: Dict[str, Any],
    name: Optional[str],
    model_visible: Optional[bool],
    native_collision_initial_active: Optional[bool],
    native_collision_climbable: Optional[bool],
    initial_create: Optional[bool],
    camp: Optional[str],
    out_of_range_not_run: Optional[bool],
) -> None:
    if isinstance(name, str) and name.strip() != "":
        _set_template_name(entry, name.strip())

    if isinstance(model_visible, bool):
        visibility = _find_or_create_section(entry, 4)
        _set_bool_flag_in_section(visibility, "1", model_visible)

    if isinstance(native_collision_initial_active, bool) or isinstance(native_collision_climbable, bool):
        collision = _find_or_create_section(entry, 5)
        if isinstance(native_collision_initial_active, bool):
            _set_bool_flag_in_section(collision, "1", native_collision_initial_active)
        if isinstance(native_collision_climbable, bool):
            _set_bool_flag_in_section(collision, "2", native_collision_climbable)

    if isinstance(initial_create, bool):
        # 样本中：section id=6 的 field '1' 为“禁用初始创建”flag。
        create_section = _find_or_create_section(entry, 6)
        _set_bool_flag_in_section(create_section, "1", not initial_create)

    if isinstance(out_of_range_not_run, bool):
        load_opt = _find_or_create_section(entry, 8)
        # 样本中该段固定带 501=1；保持该字段，避免最小结构差异导致编辑器/游戏不兼容。
        load_opt["501"] = 1
        _set_bool_flag_in_section(load_opt, "1", out_of_range_not_run)

    if camp is not None:
        camp_text = str(camp).strip().lower()
        camp_section = _find_or_create_section(entry, 12)
        camp_section.clear()
        if camp_text in ("default", "follow_default"):
            camp_section["501"] = 1
        elif camp_text in ("player", "initial_player"):
            camp_section["1"] = 1
        else:
            raise ValueError("camp must be one of: default, player")


def _parse_on_off_flag(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in ("on", "true", "1", "yes", "y"):
        return True
    if text in ("off", "false", "0", "no", "n"):
        return False
    raise ValueError(f"invalid flag value: {value!r} (expected on/off)")


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    argument_parser = argparse.ArgumentParser(description="修改/克隆 .gil 元件库模板（TemplateConfig）并写回为新的 .gil。")
    argument_parser.add_argument("--input-gil", dest="input_gil_file", required=True, help="输入 .gil 文件路径")
    argument_parser.add_argument(
        "--output-gil",
        dest="output_gil_file",
        default="edited_templates/output.gil",
        help="输出 .gil 文件路径（强制落盘到 ugc_file_tools/out/ 下）",
    )
    argument_parser.add_argument("--template-id", dest="template_id", type=int, required=True, help="要修改/克隆的元件ID")
    argument_parser.add_argument(
        "--clone-to-template-id",
        dest="clone_to_template_id",
        type=int,
        help="可选：克隆为新的元件ID（提供该参数时不会修改原元件，而是追加一个新元件）",
    )
    argument_parser.add_argument("--set-name", dest="set_name", help="可选：设置元件名称")
    argument_parser.add_argument("--model-visible", dest="model_visible", help="可选：模型可见性 on/off")
    argument_parser.add_argument(
        "--native-collision-initial-active",
        dest="native_collision_initial_active",
        help="可选：原生碰撞-初始生效 on/off（字段映射基于样本推断）",
    )
    argument_parser.add_argument(
        "--native-collision-climbable",
        dest="native_collision_climbable",
        help="可选：原生碰撞-是否可攀爬 on/off（字段映射基于样本推断）",
    )
    argument_parser.add_argument("--initial-create", dest="initial_create", help="可选：初始创建 on/off")
    argument_parser.add_argument("--camp", dest="camp", help="可选：阵营 default/player")
    argument_parser.add_argument("--out-of-range-not-run", dest="out_of_range_not_run", help="可选：超出范围不运行 on/off")

    arguments = argument_parser.parse_args(list(argv) if argv is not None else None)

    input_gil_file_path = Path(arguments.input_gil_file)
    if not input_gil_file_path.is_file():
        raise FileNotFoundError(str(input_gil_file_path))

    default_output_name = f"{input_gil_file_path.stem}.edited.gil"
    output_gil_file_path = resolve_output_file_path_in_out_dir(
        Path(arguments.output_gil_file),
        default_file_name=default_output_name,
    )
    output_gil_file_path.parent.mkdir(parents=True, exist_ok=True)

    raw_dump_object = _dump_gil_to_raw_json_object(input_gil_file_path)
    payload_root = _get_payload_root(raw_dump_object)
    template_section = _ensure_path_dict(payload_root, "4")
    template_entries = _ensure_path_list_allow_scalar(template_section, "1")

    source_entry = _find_template_entry(template_entries, int(arguments.template_id))

    target_entry: Dict[str, Any]
    if arguments.clone_to_template_id is not None:
        new_id = int(arguments.clone_to_template_id)
        if any(
            isinstance(item, dict) and _extract_first_int_from_repeated_field(item, "1") == new_id
            for item in template_entries
        ):
            raise ValueError(f"clone_to_template_id 已存在：{new_id}")
        target_entry = copy.deepcopy(source_entry)
        _set_template_id(target_entry, new_id)
        if not isinstance(arguments.set_name, str) or arguments.set_name.strip() == "":
            _set_template_name(target_entry, f"{arguments.template_id}_clone_{new_id}")
        template_entries.append(target_entry)
    else:
        target_entry = source_entry

    apply_template_edits(
        entry=target_entry,
        name=(str(arguments.set_name) if arguments.set_name is not None else None),
        model_visible=_parse_on_off_flag(arguments.model_visible),
        native_collision_initial_active=_parse_on_off_flag(arguments.native_collision_initial_active),
        native_collision_climbable=_parse_on_off_flag(arguments.native_collision_climbable),
        initial_create=_parse_on_off_flag(arguments.initial_create),
        camp=(str(arguments.camp) if arguments.camp is not None else None),
        out_of_range_not_run=_parse_on_off_flag(arguments.out_of_range_not_run),
    )

    payload_bytes = encode_message(payload_root)
    container_spec = read_gil_container_spec(input_gil_file_path)
    output_bytes = build_gil_file_bytes_from_payload(payload_bytes=payload_bytes, container_spec=container_spec)
    output_gil_file_path.write_bytes(output_bytes)

    print(f"写回完成：{str(output_gil_file_path)}")


if __name__ == "__main__":
    main()




