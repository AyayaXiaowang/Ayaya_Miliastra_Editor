from __future__ import annotations

import json
import re
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from ugc_file_tools.fs_naming import sanitize_file_stem
from ugc_file_tools.gia.container import unwrap_gia_container, validate_gia_container_file
from ugc_file_tools.gia_export.templates import CustomVariableDef, extract_custom_variable_defs_from_bundle
from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_field_map
from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import decoded_field_map_to_numeric_message


JsonDict = Dict[str, Any]


@dataclass(frozen=True, slots=True)
class ImportGiaTemplatesAndInstancesPlan:
    """
    导入“元件模板 + 装饰物/实体实例” `.gia` 到 Graph_Generater 项目存档：
    - 元件库/*.json + 元件库/templates_index.json
    - 实体摆放/*.json + 实体摆放/instances_index.json

    当前适配的 `.gia` 形态（已用真实样本验证）：
    - Root.field_1: templates(GraphUnit, class=1,type=1,which=1, field_11 payload)
    - Root.field_2: decorations(GraphUnit, class=1,type=14,which=28, field_21 wrapper)
      - wrapper.1.payload.4[*].50.502 -> template_root_id_int
      - wrapper.1.payload.5[*].11 -> transform(pos/rot/scale)
    """

    input_gia_file: Path
    project_archive_path: Path
    overwrite: bool = False
    decode_max_depth: int = 28
    skip_templates: bool = False
    skip_instances: bool = False
    # instances_mode（Root.field_2 的处理方式）：
    # - "instances"：
    #   Root.field_2 每个 unit 写入一个 实体摆放/*.json（旧行为；可能产生大量文件）。
    # - "decorations_carrier"：
    #   将 Root.field_2 全部 unit 合并为一个“装饰物载体实体”，写入到该实体的
    #   `metadata.common_inspector.model.decorations`（避免产生海量实例文件）。
    # - "decorations_to_template"：
    #   将 Root.field_2 **按被引用 template_id 分组**，写入到对应元件（模板）的
    #   `metadata.common_inspector.model.decorations`（以元件为主，不生成实体摆放文件）。
    #
    # 默认仍使用 decorations_carrier（兼容旧 UI/CLI 行为）；若你导入的是“元件自带实体/装饰物组（prefab）”，
    # 更推荐使用 decorations_to_template。
    instances_mode: str = "decorations_to_template"  # instances | decorations_carrier | decorations_to_template

    # 当 instances_mode="decorations_carrier" 时，允许显式指定输出载体的 template/instance id/name；
    # decorations_to_template 会写入“被引用模板自身”，不支持指定单个载体 ID（若需要全局合并请使用 decorations_carrier）。
    # 留空则会基于 input_gia_file.stem 自动生成，并在冲突时自动加后缀。
    decorations_carrier_template_id: str = ""
    decorations_carrier_template_name: str = ""
    decorations_carrier_instance_id: str = ""
    decorations_carrier_instance_name: str = ""


def _parse_int_like(value: Any, *, label: str) -> int:
    """
    解析“应该是整数”的字段，兼容某些 `.gia` 在中间流程中把 varint 写成 utf8 数字字符串的情况。

    允许：
    - int（但不接受 bool）
    - str（去空白后为十进制整数文本，可带 +/-）
    """
    if isinstance(value, bool):
        raise TypeError(f"{label} 必须为 int（非 bool）或数字字符串（got: bool={value!r}）")
    if isinstance(value, int):
        return int(value)
    if isinstance(value, str):
        s = str(value).strip()
        if s != "" and s.lstrip("+-").isdigit():
            return int(s)
    raise TypeError(f"{label} 必须为 int 或数字字符串（got: {type(value).__name__} {value!r}）")


def _coerce_optional_int_like(value: Any) -> Optional[int]:
    """
    尝试将 value 解析为 int；失败则返回 None（用于可选字段）。
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return int(value)
    if isinstance(value, str):
        s = str(value).strip()
        if s != "" and s.lstrip("+-").isdigit():
            return int(s)
    return None


_PLACEHOLDER_INSTANCE_NAME_RE = re.compile(r"^(装饰物|Decoration)(?:[_#\s]?\d+)?$", re.IGNORECASE)


def _is_placeholder_instance_name(name: str) -> bool:
    text = str(name or "").strip()
    if text == "":
        return True
    return bool(_PLACEHOLDER_INSTANCE_NAME_RE.fullmatch(text))


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _to_list_of_dicts(value: Any) -> list[JsonDict]:
    out: list[JsonDict] = []
    for element in _as_list(value):
        if isinstance(element, dict):
            out.append(element)
    return out

def _extract_graph_unit_id_int(unit: Mapping[str, Any]) -> int:
    id_msg = unit.get("1")
    if not isinstance(id_msg, Mapping):
        raise TypeError("GraphUnit['1'] 必须为 dict(GraphUnitId)")
    return _parse_int_like(id_msg.get("4"), label="GraphUnitId['4'](id_int)")


def _extract_template_type_code_int(unit: Mapping[str, Any]) -> Optional[int]:
    payload11 = unit.get("11")
    if not isinstance(payload11, Mapping):
        return None
    payload = payload11.get("1")
    if not isinstance(payload, Mapping):
        return None
    return _coerce_optional_int_like(payload.get("2"))


def _default_entity_type_for_template_type_code(template_type_code_int: Optional[int]) -> str:
    # 对齐 `gil_package_exporter/template_exporter.py`：怪物/角色映射为“角色”，其它默认“物件”
    if isinstance(template_type_code_int, int) and 30000000 <= int(template_type_code_int) < 40000000:
        return "角色"
    return "物件"


def _build_custom_variables_component(custom_defs: Sequence[CustomVariableDef]) -> Optional[JsonDict]:
    if not custom_defs:
        return None
    items: list[JsonDict] = []
    for d in list(custom_defs):
        items.append(
            {
                "变量名": str(d.name),
                "数据类型": str(d.var_type_text),
                "默认值": d.default_value,
            }
        )
    return {"component_type": "自定义变量", "settings": {"已定义自定义变量": items}}


def _extract_template_root_id_int_from_decoration_payload(payload: Mapping[str, Any]) -> Optional[int]:
    # 经验：payload.4[*].50.502 存放 template_root_id
    entries = payload.get("4")
    for entry in _to_list_of_dicts(entries):
        msg50 = entry.get("50")
        if not isinstance(msg50, Mapping):
            continue
        rid_int = _coerce_optional_int_like(msg50.get("502"))
        if isinstance(rid_int, int):
            return int(rid_int)
    return None


def _find_transform_message_from_decoration_payload(payload: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    entries = payload.get("5")
    for entry in _to_list_of_dicts(entries):
        t = entry.get("11")
        if not isinstance(t, Mapping):
            continue
        # heuristic：transform 常见包含 pos/rot/scale（允许部分字段缺失，按 default 补齐）
        if isinstance(t.get("1"), Mapping) or isinstance(t.get("2"), Mapping) or isinstance(t.get("3"), Mapping):
            return t
    return None


def _as_float(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _extract_vector3(msg: Any, *, default: Tuple[float, float, float]) -> Tuple[float, float, float]:
    if not isinstance(msg, Mapping):
        return default
    x = _as_float(msg.get("1"))
    y = _as_float(msg.get("2"))
    z = _as_float(msg.get("3"))
    return (float(default[0] if x is None else x), float(default[1] if y is None else y), float(default[2] if z is None else z))


def _extract_rotation_deg(rot_msg: Any) -> Tuple[float, float, float]:
    # 对齐 `gil_package_exporter/instance_exporter.py`：rotation 使用 Vector3（允许缺字段，按 0 补齐）
    return _extract_vector3(rot_msg, default=(0.0, 0.0, 0.0))


def _extract_graph_unit_class_type_which_id(unit: Mapping[str, Any]) -> Tuple[int, int, Optional[int], int]:
    """
    返回 (class_int, type_int, which_int, id_int)。

    经验：
    - 元件模板：class=1,type=1,which=1
    - 装饰物/实体摆放：class=1,type=14,which=28

    约定：
    - 若 GraphUnitId 缺字段/类型不支持，返回 (0, 0, which_out, 0) 供上层跳过该 unit。
    """
    which_out = _coerce_optional_int_like(unit.get("5"))
    id_msg = unit.get("1")
    if not isinstance(id_msg, Mapping):
        return 0, 0, which_out, 0

    class_int = _coerce_optional_int_like(id_msg.get("2"))
    type_int = _coerce_optional_int_like(id_msg.get("3"))
    id_int = _coerce_optional_int_like(id_msg.get("4"))
    if not isinstance(class_int, int) or not isinstance(type_int, int) or not isinstance(id_int, int):
        return 0, 0, which_out, 0

    return int(class_int), int(type_int), which_out, int(id_int)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_existing_template_paths(templates_dir: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    if not templates_dir.is_dir():
        return out
    for p in templates_dir.glob("*.json"):
        if p.name == "templates_index.json":
            continue
        obj = _read_json(p)
        if not isinstance(obj, dict):
            continue
        tid = str(obj.get("template_id") or "").strip()
        if tid == "":
            continue
        if tid in out:
            raise ValueError(f"目标项目存档的元件库存在重复 template_id：{tid!r}")
        out[tid] = p.resolve()
    return out


def _load_existing_instance_paths(instances_dir: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    if not instances_dir.is_dir():
        return out
    for p in instances_dir.glob("*.json"):
        if p.name == "instances_index.json":
            continue
        obj = _read_json(p)
        if not isinstance(obj, dict):
            continue
        iid = str(obj.get("instance_id") or "").strip()
        if iid == "":
            continue
        if iid in out:
            raise ValueError(f"目标项目存档的实体摆放存在重复 instance_id：{iid!r}")
        out[iid] = p.resolve()
    return out


def _build_templates_index_from_disk(*, project_root: Path, templates_dir: Path) -> list[JsonDict]:
    exported: list[JsonDict] = []
    if not templates_dir.is_dir():
        return exported
    for p in templates_dir.glob("*.json"):
        if p.name == "templates_index.json":
            continue
        obj = _read_json(p)
        if not isinstance(obj, dict):
            continue
        tid = str(obj.get("template_id") or "").strip()
        name = str(obj.get("name") or "").strip()
        entity_type = str(obj.get("entity_type") or "").strip()
        if tid == "" or name == "" or entity_type == "":
            continue
        exported.append(
            {
                "template_id": tid,
                "name": name,
                "entity_type": entity_type,
                "output": str(p.relative_to(project_root)).replace("\\", "/"),
            }
        )
    return sorted(exported, key=lambda item: str(item.get("template_id") or ""))


def _build_instances_index_from_disk(*, project_root: Path, instances_dir: Path) -> list[JsonDict]:
    exported: list[JsonDict] = []
    if not instances_dir.is_dir():
        return exported
    for p in instances_dir.glob("*.json"):
        if p.name == "instances_index.json":
            continue
        obj = _read_json(p)
        if not isinstance(obj, dict):
            continue
        iid = str(obj.get("instance_id") or "").strip()
        name = str(obj.get("name") or "").strip()
        tid = str(obj.get("template_id") or "").strip()
        meta = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else {}
        entity_type = str(meta.get("entity_type") or "").strip()
        is_level_entity = bool(meta.get("is_level_entity"))
        if iid == "" or name == "" or tid == "" or entity_type == "":
            continue
        exported.append(
            {
                "instance_id": iid,
                "name": name,
                "template_id": tid,
                "entity_type": entity_type,
                "is_level_entity": bool(is_level_entity),
                "output": str(p.relative_to(project_root)).replace("\\", "/"),
            }
        )
    return sorted(
        exported,
        key=lambda item: (
            0 if item.get("is_level_entity") else 1,
            str(item.get("name") or ""),
            str(item.get("instance_id") or ""),
        ),
    )


def _generate_unique_id(*, preferred: str, used: set[str]) -> str:
    base = str(preferred or "").strip()
    if base == "":
        base = "unnamed"
    if base not in used:
        used.add(base)
        return base
    for i in range(2, 10000):
        candidate = f"{base}_{i}"
        if candidate not in used:
            used.add(candidate)
            return candidate
    raise ValueError(f"无法生成唯一 ID：preferred={preferred!r}")


def _coerce_positive_int_text(value: object, *, label: str) -> int:
    """
    将用户输入（通常来自 plan 的 string 字段）强制解析为十进制非负整数。

    说明：
    - 项目存档的 template_id/instance_id 在写回 `.gil`/导出 `.gia` 时通常需要可 `int(...)`。
    - 这里不接受空字符串或非数字（避免 downstream 在别处爆炸，且更易定位）。
    """
    text = str(value or "").strip()
    if text == "" or not text.isdigit():
        raise ValueError(f"{label} 必须为十进制非负整数文本（got: {value!r}）")
    return int(text)


def _collect_used_numeric_ids(text_ids: Sequence[str]) -> set[int]:
    used: set[int] = set()
    for t in list(text_ids):
        s = str(t or "").strip()
        if s.isdigit():
            used.add(int(s))
    return used


def _is_decorations_carrier_template(obj: Mapping[str, Any]) -> bool:
    meta = obj.get("metadata")
    if isinstance(meta, Mapping):
        ugc = meta.get("ugc")
        if isinstance(ugc, Mapping):
            if str(ugc.get("source") or "").strip() == "imported_from_gia_decorations_carrier":
                return True
    entity_config = obj.get("entity_config")
    if isinstance(entity_config, Mapping):
        render = entity_config.get("render")
        if isinstance(render, Mapping):
            if str(render.get("model_name") or "").strip() == "空模型":
                return True
    return False


def _is_decorations_carrier_instance(obj: Mapping[str, Any]) -> bool:
    meta = obj.get("metadata")
    if isinstance(meta, Mapping):
        if str(meta.get("ugc_decorations_source") or "").strip() == "gia_bundle.field_2":
            return True
        common_inspector = meta.get("common_inspector")
        if isinstance(common_inspector, Mapping):
            model = common_inspector.get("model")
            if isinstance(model, Mapping) and isinstance(model.get("decorations"), list):
                return True
    return False


def _pick_unique_prefixed_id_int(*, prefix: int, seed: int, used: set[int]) -> int:
    """
    在固定高位前缀下生成一个不冲突的 32-bit 正整数 ID（用于 decorations_carrier 的载体 template/instance）。

    prefix 推荐使用：
    - template: 0x7F000000
    - instance: 0x7E000000
    """
    prefix_int = int(prefix) & 0xFF000000
    base_suffix = int(seed) & 0x00FFFFFF
    for i in range(0, 10000):
        candidate = int(prefix_int | ((base_suffix + i) & 0x00FFFFFF))
        if candidate not in used:
            used.add(candidate)
            return candidate
    raise ValueError(f"无法生成唯一 ID：prefix=0x{prefix_int:X} seed=0x{int(seed):X}")


def run_import_gia_templates_and_instances_to_project_archive(*, plan: ImportGiaTemplatesAndInstancesPlan) -> Dict[str, Any]:
    input_gia = Path(plan.input_gia_file).resolve()
    project_root = Path(plan.project_archive_path).resolve()
    if not input_gia.is_file() or input_gia.suffix.lower() != ".gia":
        raise FileNotFoundError(str(input_gia))
    if not project_root.is_dir():
        raise FileNotFoundError(str(project_root))

    validate_gia_container_file(input_gia)
    proto_bytes = unwrap_gia_container(input_gia, check_header=False)
    field_map, consumed = decode_message_to_field_map(
        data_bytes=proto_bytes,
        start_offset=0,
        end_offset=len(proto_bytes),
        remaining_depth=int(plan.decode_max_depth),
    )
    if consumed != len(proto_bytes):
        raise ValueError(
            "protobuf 解析未消费完整字节流："
            f"consumed={consumed} total={len(proto_bytes)} file={str(input_gia)!r}"
        )
    root_message = decoded_field_map_to_numeric_message(field_map, prefer_raw_hex_for_utf8=False)
    if not isinstance(root_message, dict):
        raise TypeError("decoded root_message 必须为 dict(numeric_message)")

    templates_units = _to_list_of_dicts(root_message.get("1"))
    decorations_units = _to_list_of_dicts(root_message.get("2"))
    root_file_path = str(root_message.get("3") or "").strip()
    root_game_version = str(root_message.get("5") or "").strip()

    templates_dir = (project_root / "元件库").resolve()
    instances_dir = (project_root / "实体摆放").resolve()

    existing_template_paths = _load_existing_template_paths(templates_dir)
    existing_instance_paths = _load_existing_instance_paths(instances_dir)

    instances_mode = str(getattr(plan, "instances_mode", "") or "instances").strip().lower()
    if instances_mode not in {"instances", "decorations_carrier", "decorations_to_template"}:
        raise ValueError(
            "instances_mode 仅支持：instances | decorations_carrier | decorations_to_template，"
            f"got: {getattr(plan, 'instances_mode', None)!r}"
        )

    planned_writes: list[Path] = []
    imported_template_ids: set[str] = set()
    imported_instance_ids: set[str] = set()
    templates_by_id: dict[int, JsonDict] = {}
    template_output_path_by_id: dict[str, Path] = {}
    instance_output_path_by_id: dict[str, Path] = {}
    template_name_cache: dict[str, str] = {}
    planned_instance_renames: list[tuple[Path, Path]] = []

    carrier_template_obj: Optional[JsonDict] = None
    carrier_template_output_path: Optional[Path] = None
    carrier_template_id_text: str = ""
    carrier_instance_output_path: Optional[Path] = None
    carrier_instance_id_text: str = ""
    carrier_instance_name_text: str = ""
    imported_decorations_count: int = 0
    decorations_to_template_target_template_ids: set[str] = set()

    def _get_template_display_name(template_id_text: str) -> str:
        tid = str(template_id_text or "").strip()
        cached = template_name_cache.get(tid)
        if cached is not None:
            return str(cached)
        existing_path = existing_template_paths.get(tid)
        if existing_path is None:
            template_name_cache[tid] = ""
            return ""
        obj = _read_json(Path(existing_path))
        if isinstance(obj, dict):
            name_text = str(obj.get("name") or "").strip()
            template_name_cache[tid] = str(name_text)
            return str(name_text)
        template_name_cache[tid] = ""
        return ""

    def _resolve_instance_display_name(*, gia_unit_name: str, template_id_text: str) -> str:
        raw_unit_name = str(gia_unit_name or "").strip()
        template_name = str(_get_template_display_name(str(template_id_text)) or "").strip()
        if _is_placeholder_instance_name(raw_unit_name):
            return template_name or raw_unit_name or "装饰物"
        return raw_unit_name or template_name or "装饰物"

    # ===== templates =====
    if not bool(plan.skip_templates):
        for unit in list(templates_units):
            class_int, type_int, which_int, template_root_id_int = _extract_graph_unit_class_type_which_id(unit)
            if not (class_int == 1 and type_int == 1 and which_int == 1):
                continue
            template_id_text = str(template_root_id_int)
            name_text = str(unit.get("3") or "").strip() or f"template_{template_id_text}"
            template_name_cache[template_id_text] = str(name_text)

            type_code_int = _extract_template_type_code_int(unit)
            entity_type = _default_entity_type_for_template_type_code(type_code_int)

            custom_defs: list[CustomVariableDef] = []
            payload11 = unit.get("11")
            if isinstance(payload11, Mapping) and isinstance(payload11.get("1"), Mapping):
                custom_defs = extract_custom_variable_defs_from_bundle({"1": dict(unit)})
            default_components: list[JsonDict] = []
            custom_comp = _build_custom_variables_component(custom_defs)
            if custom_comp is not None:
                default_components.append(custom_comp)

            template_obj: JsonDict = {
                "template_id": template_id_text,
                "name": str(name_text),
                "entity_type": str(entity_type),
                "description": "由 .gia 导入",
                "default_graphs": [],
                "default_variables": [],
                "default_components": default_components,
                "entity_config": {},
                "metadata": {
                    "ugc": {
                        "source": "imported_from_gia",
                        "source_gia_file": str(input_gia),
                        "source_gia_bundle_file_path": root_file_path,
                        "source_gia_game_version": root_game_version,
                        "source_template_root_id_int": int(template_root_id_int),
                        "source_template_type_code_int": int(type_code_int) if isinstance(type_code_int, int) else None,
                    }
                },
                "graph_variable_overrides": {},
                "updated_at": "",
            }

            file_stem = sanitize_file_stem(name_text)
            existing_path = existing_template_paths.get(template_id_text)
            if existing_path is not None and not bool(plan.overwrite):
                raise FileExistsError(
                    f"目标项目存档已存在同 template_id 的模板（如需覆盖请使用 --overwrite）："
                    f"template_id={template_id_text} file={str(existing_path)}"
                )
            output_path = (
                Path(existing_path)
                if existing_path is not None
                else (templates_dir / f"{file_stem}_{template_id_text}.json").resolve()
            )
            planned_writes.append(Path(output_path))
            templates_by_id[int(template_root_id_int)] = template_obj
            imported_template_ids.add(template_id_text)
            template_output_path_by_id[template_id_text] = Path(output_path)

    # ===== instances (decorations) =====
    skipped_missing_template_ref: list[int] = []
    skipped_missing_transform: list[int] = []
    if not bool(plan.skip_instances):
        if instances_mode == "instances":
            for unit in list(decorations_units):
                class_int, type_int, which_int, unit_id_int = _extract_graph_unit_class_type_which_id(unit)
                if not (class_int == 1 and type_int == 14 and which_int == 28):
                    continue
                wrapper = unit.get("21")
                payload = wrapper.get("1") if isinstance(wrapper, Mapping) else None
                if not isinstance(payload, Mapping):
                    skipped_missing_template_ref.append(int(unit_id_int))
                    continue

                template_root_id_int = _extract_template_root_id_int_from_decoration_payload(payload)
                if not isinstance(template_root_id_int, int):
                    skipped_missing_template_ref.append(int(unit_id_int))
                    continue

                transform = _find_transform_message_from_decoration_payload(payload)
                if not isinstance(transform, Mapping):
                    skipped_missing_transform.append(int(unit_id_int))
                    transform = {}

                # 解析但不使用（保留用于未来扩展/调试；同时确保缺字段时走一致的 default 逻辑）
                _pos = _extract_vector3(transform.get("1"), default=(0.0, 0.0, 0.0))
                _rot = _extract_rotation_deg(transform.get("2"))
                _scale = _extract_vector3(transform.get("3"), default=(1.0, 1.0, 1.0))

                raw_unit_name = str(unit.get("3") or "").strip()
                instance_id_text = str(unit_id_int)
                template_id_text = str(template_root_id_int)
                name_text = _resolve_instance_display_name(
                    gia_unit_name=str(raw_unit_name),
                    template_id_text=str(template_id_text),
                )

                file_stem = sanitize_file_stem(name_text)
                existing_path = existing_instance_paths.get(instance_id_text)
                if existing_path is not None and not bool(plan.overwrite):
                    raise FileExistsError(
                        f"目标项目存档已存在同 instance_id 的实体摆放（如需覆盖请使用 --overwrite）："
                        f"instance_id={instance_id_text} file={str(existing_path)}"
                    )
                desired_path = (instances_dir / f"{file_stem}_{instance_id_text}.json").resolve()
                if existing_path is not None and bool(plan.overwrite):
                    existing_path_resolved = Path(existing_path).resolve()
                    if desired_path != existing_path_resolved:
                        if desired_path.exists():
                            raise FileExistsError(
                                "overwrite 导入需要重命名实体摆放文件，但目标路径已存在："
                                f"src={str(existing_path_resolved)} dst={str(desired_path)}"
                            )
                        planned_instance_renames.append((existing_path_resolved, desired_path))
                    output_path = desired_path
                else:
                    output_path = Path(existing_path) if existing_path is not None else desired_path
                planned_writes.append(Path(output_path))
                imported_instance_ids.add(instance_id_text)
                imported_decorations_count += 1
                instance_output_path_by_id[instance_id_text] = Path(output_path)
        elif instances_mode == "decorations_carrier":
            # decorations_carrier：将所有 unit 合并写入一个“装饰物载体实体”
            for unit in list(decorations_units):
                class_int, type_int, which_int, unit_id_int = _extract_graph_unit_class_type_which_id(unit)
                if not (class_int == 1 and type_int == 14 and which_int == 28):
                    continue
                wrapper = unit.get("21")
                payload = wrapper.get("1") if isinstance(wrapper, Mapping) else None
                if not isinstance(payload, Mapping):
                    skipped_missing_template_ref.append(int(unit_id_int))
                    continue
                template_root_id_int = _extract_template_root_id_int_from_decoration_payload(payload)
                if not isinstance(template_root_id_int, int):
                    skipped_missing_template_ref.append(int(unit_id_int))
                    continue
                transform = _find_transform_message_from_decoration_payload(payload)
                if not isinstance(transform, Mapping):
                    skipped_missing_transform.append(int(unit_id_int))

            base_stem = sanitize_file_stem(input_gia.stem) or "gia_decorations"

            # 载体 template/instance 的 ID 必须能转为 int（写回 `.gil` / 导出 `.gia` 会使用 int(...)）
            seed = int(zlib.crc32(str(base_stem).encode("utf-8")) & 0xFFFFFFFF)
            template_prefix = 0x7F000000
            instance_prefix = 0x7E000000
            auto_tpl_candidate_int = int(template_prefix | (seed & 0x00FFFFFF))
            auto_inst_candidate_int = int(instance_prefix | (seed & 0x00FFFFFF))

            preferred_tpl_name = str(plan.decorations_carrier_template_name or "").strip() or f"{base_stem}_装饰物载体模板"
            preferred_inst_name = str(plan.decorations_carrier_instance_name or "").strip() or f"{base_stem}_装饰物组"

            explicit_tpl_id_text = str(plan.decorations_carrier_template_id or "").strip()
            explicit_inst_id_text = str(plan.decorations_carrier_instance_id or "").strip()

            used_tpl_id_ints = _collect_used_numeric_ids(list(existing_template_paths.keys()) + list(imported_template_ids))
            used_inst_id_ints = _collect_used_numeric_ids(list(existing_instance_paths.keys()))

            # --- pick carrier template id ---
            if explicit_tpl_id_text != "":
                carrier_template_id_int = _coerce_positive_int_text(
                    explicit_tpl_id_text, label="decorations_carrier_template_id"
                )
                if str(carrier_template_id_int) in imported_template_ids:
                    raise ValueError(
                        "decorations_carrier_template_id 与本次导入的模板 template_id 冲突："
                        f"{carrier_template_id_int}"
                    )
                existing_tpl_path2 = existing_template_paths.get(str(carrier_template_id_int))
                if existing_tpl_path2 is not None:
                    existing_obj = _read_json(Path(existing_tpl_path2))
                    if not (isinstance(existing_obj, Mapping) and _is_decorations_carrier_template(existing_obj)):
                        raise ValueError(
                            "指定的 decorations_carrier_template_id 已存在，但不是可用的“空模型载体模板”（避免误用普通模板作为载体）："
                            f"template_id={carrier_template_id_int} file={str(existing_tpl_path2)}"
                        )
            else:
                existing_tpl_path3 = existing_template_paths.get(str(auto_tpl_candidate_int))
                if existing_tpl_path3 is not None:
                    existing_obj2 = _read_json(Path(existing_tpl_path3))
                    if isinstance(existing_obj2, Mapping) and _is_decorations_carrier_template(existing_obj2):
                        carrier_template_id_int = int(auto_tpl_candidate_int)
                    else:
                        carrier_template_id_int = _pick_unique_prefixed_id_int(
                            prefix=template_prefix,
                            seed=seed,
                            used=used_tpl_id_ints,
                        )
                else:
                    if auto_tpl_candidate_int in used_tpl_id_ints:
                        carrier_template_id_int = _pick_unique_prefixed_id_int(
                            prefix=template_prefix,
                            seed=seed,
                            used=used_tpl_id_ints,
                        )
                    else:
                        carrier_template_id_int = int(auto_tpl_candidate_int)
                        used_tpl_id_ints.add(int(auto_tpl_candidate_int))

            carrier_template_id_text = str(int(carrier_template_id_int))

            # --- pick carrier instance id ---
            if explicit_inst_id_text != "":
                carrier_instance_id_int = _coerce_positive_int_text(
                    explicit_inst_id_text, label="decorations_carrier_instance_id"
                )
                existing_inst_path2 = existing_instance_paths.get(str(carrier_instance_id_int))
                if existing_inst_path2 is not None:
                    existing_inst_obj = _read_json(Path(existing_inst_path2))
                    if not (isinstance(existing_inst_obj, Mapping) and _is_decorations_carrier_instance(existing_inst_obj)):
                        raise ValueError(
                            "指定的 decorations_carrier_instance_id 已存在，但不是可用的“装饰物载体实体”（避免覆盖普通实体摆放）："
                            f"instance_id={carrier_instance_id_int} file={str(existing_inst_path2)}"
                        )
            else:
                existing_inst_path3 = existing_instance_paths.get(str(auto_inst_candidate_int))
                if existing_inst_path3 is not None:
                    existing_inst_obj2 = _read_json(Path(existing_inst_path3))
                    if isinstance(existing_inst_obj2, Mapping) and _is_decorations_carrier_instance(existing_inst_obj2):
                        carrier_instance_id_int = int(auto_inst_candidate_int)
                    else:
                        carrier_instance_id_int = _pick_unique_prefixed_id_int(
                            prefix=instance_prefix,
                            seed=seed,
                            used=used_inst_id_ints,
                        )
                else:
                    if auto_inst_candidate_int in used_inst_id_ints:
                        carrier_instance_id_int = _pick_unique_prefixed_id_int(
                            prefix=instance_prefix,
                            seed=seed,
                            used=used_inst_id_ints,
                        )
                    else:
                        carrier_instance_id_int = int(auto_inst_candidate_int)
                        used_inst_id_ints.add(int(auto_inst_candidate_int))

            carrier_instance_id_text = str(int(carrier_instance_id_int))

            carrier_instance_name_text = preferred_inst_name or carrier_instance_id_text
            carrier_template_name_text = preferred_tpl_name or carrier_template_id_text

            # --- carrier template: only create when missing ---
            existing_tpl_path = existing_template_paths.get(str(carrier_template_id_text))
            if existing_tpl_path is None:
                carrier_template_obj = {
                    "template_id": str(carrier_template_id_text),
                    "name": str(carrier_template_name_text),
                    "entity_type": "物件",
                    "description": "由 .gia 装饰物导入（合并载体）",
                    "default_graphs": [],
                    "default_variables": [],
                    "default_components": [],
                    "entity_config": {
                        "render": {"model_name": "空模型", "visible": True},
                    },
                    "metadata": {
                        "object_model_name": "空模型",
                        "ugc": {
                            "source": "imported_from_gia_decorations_carrier",
                            "source_gia_file": str(input_gia),
                            "source_gia_bundle_file_path": root_file_path,
                            "source_gia_game_version": root_game_version,
                        },
                    },
                    "graph_variable_overrides": {},
                    "updated_at": "",
                }

                tpl_file_stem = sanitize_file_stem(str(carrier_template_name_text))
                desired_tpl_path = (templates_dir / f"{tpl_file_stem}_{carrier_template_id_text}.json").resolve()
                carrier_template_output_path = desired_tpl_path
                planned_writes.append(Path(carrier_template_output_path))

            # --- carrier instance: must be written/overwritten ---
            existing_inst_path = existing_instance_paths.get(str(carrier_instance_id_text))
            if existing_inst_path is not None and not bool(plan.overwrite):
                raise FileExistsError(
                    f"目标项目存档已存在同 instance_id 的实体摆放（如需覆盖请使用 --overwrite）："
                    f"instance_id={carrier_instance_id_text} file={str(existing_inst_path)}"
                )
            inst_file_stem = sanitize_file_stem(str(carrier_instance_name_text))
            desired_inst_path = (instances_dir / f"{inst_file_stem}_{carrier_instance_id_text}.json").resolve()
            if existing_inst_path is not None and bool(plan.overwrite):
                existing_inst_path_resolved = Path(existing_inst_path).resolve()
                if desired_inst_path != existing_inst_path_resolved:
                    if desired_inst_path.exists():
                        raise FileExistsError(
                            "overwrite 导入需要重命名实体摆放文件，但目标路径已存在："
                            f"src={str(existing_inst_path_resolved)} dst={str(desired_inst_path)}"
                        )
                    planned_instance_renames.append((existing_inst_path_resolved, desired_inst_path))
                carrier_instance_output_path = desired_inst_path
            else:
                carrier_instance_output_path = (
                    Path(existing_inst_path) if existing_inst_path is not None else desired_inst_path
                )

            planned_writes.append(Path(carrier_instance_output_path))
            imported_instance_ids.add(str(carrier_instance_id_text))
            instance_output_path_by_id[str(carrier_instance_id_text)] = Path(carrier_instance_output_path)
        else:
            # decorations_to_template：按被引用 template_id 分组，写入到对应模板的 decorations（以元件为主；不生成实体摆放）。
            if bool(plan.skip_templates):
                raise ValueError("decorations_to_template 模式必须同时导入元件模板（请取消 --skip-templates）")

            if str(plan.decorations_carrier_template_id or "").strip() != "":
                raise ValueError("decorations_to_template 模式不支持 --decorations-carrier-template-id（会写入被引用模板自身）")
            if str(plan.decorations_carrier_template_name or "").strip() != "":
                raise ValueError("decorations_to_template 模式不支持 --decorations-carrier-template-name（会写入被引用模板自身）")
            if str(plan.decorations_carrier_instance_id or "").strip() != "":
                raise ValueError("decorations_to_template 模式不支持 --decorations-carrier-instance-id（不会生成载体实体）")
            if str(plan.decorations_carrier_instance_name or "").strip() != "":
                raise ValueError("decorations_to_template 模式不支持 --decorations-carrier-instance-name（不会生成载体实体）")

            decorations_by_template_id_int: dict[int, list[JsonDict]] = {}
            for unit in list(decorations_units):
                class_int, type_int, which_int, unit_id_int = _extract_graph_unit_class_type_which_id(unit)
                if not (class_int == 1 and type_int == 14 and which_int == 28):
                    continue
                wrapper = unit.get("21")
                payload = wrapper.get("1") if isinstance(wrapper, Mapping) else None
                if not isinstance(payload, Mapping):
                    skipped_missing_template_ref.append(int(unit_id_int))
                    continue

                template_root_id_int = _extract_template_root_id_int_from_decoration_payload(payload)
                if not isinstance(template_root_id_int, int):
                    skipped_missing_template_ref.append(int(unit_id_int))
                    continue

                transform = _find_transform_message_from_decoration_payload(payload)
                if not isinstance(transform, Mapping):
                    skipped_missing_transform.append(int(unit_id_int))
                    transform = {}

                asset_id_int = _coerce_optional_int_like(payload.get("2"))
                if not isinstance(asset_id_int, int):
                    asset_id_int = int(template_root_id_int)

                pos = _extract_vector3(transform.get("1"), default=(0.0, 0.0, 0.0))
                rot = _extract_rotation_deg(transform.get("2"))
                scale = _extract_vector3(transform.get("3"), default=(1.0, 1.0, 1.0))

                raw_unit_name = str(unit.get("3") or "").strip()
                template_id_text = str(template_root_id_int)
                display_name = _resolve_instance_display_name(
                    gia_unit_name=str(raw_unit_name),
                    template_id_text=str(template_id_text),
                )

                deco_item: JsonDict = {
                    "instanceId": f"gia_{int(unit_id_int)}",
                    "displayName": str(display_name or "装饰物"),
                    "isVisible": True,
                    "assetId": int(asset_id_int),
                    "parentId": "GI_RootNode",
                    "transform": {
                        "pos": {"x": float(pos[0]), "y": float(pos[1]), "z": float(pos[2])},
                        "rot": {"x": float(rot[0]), "y": float(rot[1]), "z": float(rot[2])},
                        "scale": {"x": float(scale[0]), "y": float(scale[1]), "z": float(scale[2])},
                        "isLocked": False,
                    },
                    "physics": {
                        "enableCollision": False,
                        "isClimbable": False,
                        "showPreview": False,
                    },
                    "source_gia": {
                        "unit_id_int": int(unit_id_int),
                        "unit_name": str(raw_unit_name),
                        "template_root_id_int": int(template_root_id_int),
                        "asset_id_int": int(asset_id_int),
                        "ugc_scale": [float(scale[0]), float(scale[1]), float(scale[2])],
                    },
                }

                decorations_by_template_id_int.setdefault(int(template_root_id_int), []).append(deco_item)

            # 写入到被引用模板自身
            total_deco = 0
            for template_id_int, deco_list in decorations_by_template_id_int.items():
                total_deco += int(len(deco_list))
                template_id_text = str(int(template_id_int))
                tpl_obj = templates_by_id.get(int(template_id_int))
                if not isinstance(tpl_obj, dict):
                    # 理论上不应发生：preflight 会保证 referenced_template_ids 在本次导入范围内。
                    skipped_missing_template_ref.extend(
                        [int(item.get("source_gia", {}).get("unit_id_int", 0) or 0) for item in deco_list]
                    )
                    continue
                meta = tpl_obj.get("metadata")
                if not isinstance(meta, dict):
                    meta = {}
                    tpl_obj["metadata"] = meta
                common_inspector = meta.get("common_inspector")
                if not isinstance(common_inspector, dict):
                    common_inspector = {}
                    meta["common_inspector"] = common_inspector
                model = common_inspector.get("model")
                if not isinstance(model, dict):
                    model = {}
                    common_inspector["model"] = model
                model["decorations"] = list(deco_list)
                meta["ugc_decorations_source"] = "gia_bundle.field_2"
                decorations_to_template_target_template_ids.add(str(template_id_text))

            imported_decorations_count = int(total_deco)

    # ===== preflight =====
    if len(set(str(p) for p in planned_writes)) != len(planned_writes):
        raise ValueError("导入计划包含重复输出路径（文件名冲突）：请检查清洗规则或输入数据。")

    # 实例引用闭包检查（避免导入后综合校验直接报错）
    if not bool(plan.skip_instances):
        referenced_template_ids: set[str] = set()
        for unit in list(decorations_units):
            class_int, type_int, which_int, _unit_id_int = _extract_graph_unit_class_type_which_id(unit)
            if not (class_int == 1 and type_int == 14 and which_int == 28):
                continue
            wrapper = unit.get("21")
            payload = wrapper.get("1") if isinstance(wrapper, Mapping) else None
            if not isinstance(payload, Mapping):
                continue
            template_root_id_int = _extract_template_root_id_int_from_decoration_payload(payload)
            if isinstance(template_root_id_int, int):
                referenced_template_ids.add(str(template_root_id_int))

        if bool(plan.skip_templates):
            missing = sorted(referenced_template_ids - set(existing_template_paths.keys()))
            if missing:
                raise ValueError(
                    "导入实例但跳过模板时，目标项目存档缺少被引用的模板："
                    + ", ".join(missing[:20])
                    + (" ..." if len(missing) > 20 else "")
                )
        else:
            available = set(existing_template_paths.keys()) | set(imported_template_ids)
            missing2 = sorted(referenced_template_ids - available)
            if missing2:
                raise ValueError(
                    "导入实例时发现引用的模板不在“目标已存在模板 + 本次导入模板”范围内："
                    + ", ".join(missing2[:20])
                    + (" ..." if len(missing2) > 20 else "")
                )

    # ===== rename (overwrite) =====
    # overwrite 模式下，若实例显示名发生变化，需要同步重命名文件名以对齐“文件名=显示名”的资源库约定。
    if planned_instance_renames:
        for src, dst in list(planned_instance_renames):
            src_path = Path(src).resolve()
            dst_path = Path(dst).resolve()
            if src_path == dst_path:
                continue
            if not src_path.is_file():
                raise FileNotFoundError(str(src_path))
            if dst_path.exists():
                raise FileExistsError(f"目标路径已存在，无法重命名：{str(dst_path)}")
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            src_path.rename(dst_path)

    # ===== write =====
    wrote_any_templates = False
    if not bool(plan.skip_templates):
        for template_id_int, template_obj in sorted(templates_by_id.items(), key=lambda kv: int(kv[0])):
            template_id_text = str(template_id_int)
            out_path = template_output_path_by_id.get(template_id_text)
            if out_path is None:
                # fallback（理论上不应发生）
                name_text = str(template_obj.get("name") or "").strip() or f"template_{template_id_text}"
                file_stem = sanitize_file_stem(name_text)
                out_path = (templates_dir / f"{file_stem}_{template_id_text}.json").resolve()
            _write_json(Path(out_path), template_obj)
        wrote_any_templates = True

    # decorations_to_template：decorations 已在前面按 template_id 写入 templates_by_id，随模板一并落盘（无需额外写盘）。
    if carrier_template_obj is not None and carrier_template_output_path is not None:
        _write_json(Path(carrier_template_output_path), carrier_template_obj)
        wrote_any_templates = True

    if wrote_any_templates:
        templates_index_sorted = _build_templates_index_from_disk(project_root=project_root, templates_dir=templates_dir)
        _write_json((templates_dir / "templates_index.json").resolve(), templates_index_sorted)

    wrote_any_instances = False
    if not bool(plan.skip_instances):
        if instances_mode == "instances":
            # 再次遍历 decorations_units 写入实例（避免在内存里长期持有 9k+ 个大对象）
            for unit in list(decorations_units):
                class_int, type_int, which_int, unit_id_int = _extract_graph_unit_class_type_which_id(unit)
                if not (class_int == 1 and type_int == 14 and which_int == 28):
                    continue
                wrapper = unit.get("21")
                payload = wrapper.get("1") if isinstance(wrapper, Mapping) else None
                if not isinstance(payload, Mapping):
                    continue
                template_root_id_int = _extract_template_root_id_int_from_decoration_payload(payload)
                if not isinstance(template_root_id_int, int):
                    continue
                transform = _find_transform_message_from_decoration_payload(payload)
                if not isinstance(transform, Mapping):
                    transform = {}
                pos = _extract_vector3(transform.get("1"), default=(0.0, 0.0, 0.0))
                rot = _extract_rotation_deg(transform.get("2"))
                scale = _extract_vector3(transform.get("3"), default=(1.0, 1.0, 1.0))

                raw_unit_name = str(unit.get("3") or "").strip()
                instance_id_text = str(unit_id_int)
                template_id_text = str(template_root_id_int)
                name_text = _resolve_instance_display_name(
                    gia_unit_name=str(raw_unit_name),
                    template_id_text=str(template_id_text),
                )
                # decorations payload 的 field_2 通常是 assetId（20xxxxxx），不是 template_type_code；
                # entity_type 优先从“被引用模板”的 ugc.type_code 反推，否则回退为默认“物件”。
                template_type_code_int: Optional[int] = None
                imported_tpl_obj = templates_by_id.get(int(template_root_id_int))
                if isinstance(imported_tpl_obj, Mapping):
                    meta = imported_tpl_obj.get("metadata")
                    if isinstance(meta, Mapping):
                        ugc = meta.get("ugc")
                        if isinstance(ugc, Mapping):
                            template_type_code_int = _coerce_optional_int_like(
                                ugc.get("source_template_type_code_int")
                            )
                if template_type_code_int is None:
                    existing_tpl_path = existing_template_paths.get(str(template_id_text))
                    if existing_tpl_path is not None:
                        existing_tpl_obj2 = _read_json(Path(existing_tpl_path))
                        if isinstance(existing_tpl_obj2, Mapping):
                            meta2 = existing_tpl_obj2.get("metadata")
                            if isinstance(meta2, Mapping):
                                ugc2 = meta2.get("ugc")
                                if isinstance(ugc2, Mapping):
                                    template_type_code_int = _coerce_optional_int_like(
                                        ugc2.get("source_template_type_code_int")
                                    )
                entity_type = _default_entity_type_for_template_type_code(template_type_code_int)

                instance_obj: JsonDict = {
                    "instance_id": instance_id_text,
                    "name": str(name_text),
                    "template_id": template_id_text,
                    "position": [pos[0], pos[1], pos[2]],
                    "rotation": [rot[0], rot[1], rot[2]],
                    "override_variables": [],
                    "additional_graphs": [],
                    "additional_components": [],
                    "metadata": {
                        "entity_type": str(entity_type),
                        "is_level_entity": False,
                        "ugc_instance_id_int": int(unit_id_int),
                        "ugc_template_id_int": int(template_root_id_int),
                        # 兼容：历史字段名 ugc_template_type_int（已更名为 ugc_template_type_code_int）
                        "ugc_template_type_int": int(template_type_code_int) if isinstance(template_type_code_int, int) else None,
                        "ugc_template_type_code_int": int(template_type_code_int) if isinstance(template_type_code_int, int) else None,
                        "ugc_scale": [scale[0], scale[1], scale[2]],
                        "ugc_guid_int": 4294967295,
                        "source_gia_unit_name": str(raw_unit_name),
                        "source_gia_file": str(input_gia),
                        "source_gia_bundle_file_path": root_file_path,
                        "source_gia_game_version": root_game_version,
                    },
                    "graph_variable_overrides": {},
                }

                file_stem = sanitize_file_stem(name_text)
                out_path = instance_output_path_by_id.get(instance_id_text)
                if out_path is None:
                    out_path = (instances_dir / f"{file_stem}_{instance_id_text}.json").resolve()
                _write_json(out_path, instance_obj)
            wrote_any_instances = True
        elif instances_mode == "decorations_carrier":
            if carrier_instance_output_path is None:
                raise RuntimeError("decorations_carrier 模式缺少 carrier_instance_output_path（内部错误）")
            if carrier_template_id_text.strip() == "" or carrier_instance_id_text.strip() == "":
                raise RuntimeError("decorations_carrier 模式缺少 carrier_template_id/instance_id（内部错误）")

            decorations: list[JsonDict] = []
            for unit in list(decorations_units):
                class_int, type_int, which_int, unit_id_int = _extract_graph_unit_class_type_which_id(unit)
                if not (class_int == 1 and type_int == 14 and which_int == 28):
                    continue
                wrapper = unit.get("21")
                payload = wrapper.get("1") if isinstance(wrapper, Mapping) else None
                if not isinstance(payload, Mapping):
                    continue
                template_root_id_int = _extract_template_root_id_int_from_decoration_payload(payload)
                if not isinstance(template_root_id_int, int):
                    continue
                asset_id_int = _coerce_optional_int_like(payload.get("2"))
                if not isinstance(asset_id_int, int):
                    asset_id_int = int(template_root_id_int)

                transform = _find_transform_message_from_decoration_payload(payload)
                if not isinstance(transform, Mapping):
                    transform = {}
                pos = _extract_vector3(transform.get("1"), default=(0.0, 0.0, 0.0))
                rot = _extract_rotation_deg(transform.get("2"))
                scale = _extract_vector3(transform.get("3"), default=(1.0, 1.0, 1.0))

                raw_unit_name = str(unit.get("3") or "").strip()
                template_id_text = str(template_root_id_int)
                display_name = _resolve_instance_display_name(
                    gia_unit_name=str(raw_unit_name),
                    template_id_text=str(template_id_text),
                )
                decorations.append(
                    {
                        "instanceId": f"gia_{int(unit_id_int)}",
                        "displayName": str(display_name or "装饰物"),
                        "isVisible": True,
                        "assetId": int(asset_id_int),
                        "parentId": "GI_RootNode",
                        "transform": {
                            "pos": {"x": float(pos[0]), "y": float(pos[1]), "z": float(pos[2])},
                            "rot": {"x": float(rot[0]), "y": float(rot[1]), "z": float(rot[2])},
                            "scale": {"x": float(scale[0]), "y": float(scale[1]), "z": float(scale[2])},
                            "isLocked": False,
                        },
                        "physics": {
                            "enableCollision": False,
                            "isClimbable": False,
                            "showPreview": False,
                        },
                        "source_gia": {
                            "unit_id_int": int(unit_id_int),
                            "unit_name": str(raw_unit_name),
                            "template_root_id_int": int(template_root_id_int),
                            "asset_id_int": int(asset_id_int),
                        },
                    }
                )

            imported_decorations_count = int(len(decorations))
            carrier_instance_obj: JsonDict = {
                "instance_id": str(carrier_instance_id_text),
                "name": str(carrier_instance_name_text),
                "template_id": str(carrier_template_id_text),
                "position": [0.0, 0.0, 0.0],
                "rotation": [0.0, 0.0, 0.0],
                "scale": [1.0, 1.0, 1.0],
                "override_variables": [],
                "additional_graphs": [],
                "additional_components": [],
                "metadata": {
                    "entity_type": "物件",
                    "is_level_entity": False,
                    "common_inspector": {"model": {"decorations": decorations}},
                    "ugc_decorations_source": "gia_bundle.field_2",
                    "source_gia_file": str(input_gia),
                    "source_gia_bundle_file_path": root_file_path,
                    "source_gia_game_version": root_game_version,
                },
                "graph_variable_overrides": {},
            }
            _write_json(Path(carrier_instance_output_path), carrier_instance_obj)
            wrote_any_instances = True
        else:
            # decorations_to_template：不生成实体摆放文件（decorations 已按 template_id 写入对应模板）。
            wrote_any_instances = False

        if wrote_any_instances:
            instances_index_sorted = _build_instances_index_from_disk(project_root=project_root, instances_dir=instances_dir)
            _write_json((instances_dir / "instances_index.json").resolve(), instances_index_sorted)

    return {
        "input_gia_file": str(input_gia),
        "project_archive": str(project_root),
        "gia_bundle_file_path": root_file_path,
        "gia_game_version": root_game_version,
        "instances_mode": str(instances_mode),
        "imported_templates_count": int(len(imported_template_ids)),
        "imported_instances_count": int(len(imported_instance_ids)),
        "imported_decorations_count": int(imported_decorations_count),
        "decorations_to_template_target_templates_count": int(len(decorations_to_template_target_template_ids))
        if instances_mode == "decorations_to_template"
        else 0,
        "decorations_carrier_template_id": str(carrier_template_id_text) if instances_mode == "decorations_carrier" else "",
        "decorations_carrier_instance_id": str(carrier_instance_id_text)
        if instances_mode == "decorations_carrier"
        else "",
        "templates_dir": str(templates_dir),
        "instances_dir": str(instances_dir),
        "skipped_instance_unit_ids_missing_template_ref": skipped_missing_template_ref,
        "skipped_instance_unit_ids_missing_transform": skipped_missing_transform,
        "templates_index_file": str((templates_dir / "templates_index.json").resolve()) if bool(wrote_any_templates) else "",
        "instances_index_file": str((instances_dir / "instances_index.json").resolve())
        if (not bool(plan.skip_instances) and bool(wrote_any_instances))
        else "",
    }


__all__ = [
    "ImportGiaTemplatesAndInstancesPlan",
    "run_import_gia_templates_and_instances_to_project_archive",
]

