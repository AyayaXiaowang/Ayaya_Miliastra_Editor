from __future__ import annotations

import json
import re
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ugc_file_tools.gil_dump_codec.protobuf_like import format_binary_data_hex_text
from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import binary_data_text_to_numeric_message
from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import numeric_message_to_binary_data_text

JsonDict = Dict[str, Any]
Vec3 = Tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class TemplateDecorationRecord:
    """
    从模板 JSON 的 `metadata.common_inspector.model.decorations` 提取到的“装饰物定义”。

    目标：在 `.gil` 写回阶段，将其编码回 payload_root['27']（root27）：
    - root27.1：装饰物定义（meta 40/50/502 = parent_template_id）
    - root27.2：装饰物挂载（meta 40/50/502 = parent_instance_id，field12.1 引用 root27.1 的 def_id）

    说明：
    - 这不是“实体摆放 root5/1”的实例；装饰物属于元件模板/元件实例的附属结构，落在独立段。
    """

    def_id_int: int
    parent_template_id_int: int
    asset_id_int: int
    name: str
    position: Vec3
    rotation: Vec3
    scale: Vec3
    source_template_json_file: Path
    source_decoration_index: int
    source_decoration_instance_id: str
    source_parent_id: str


def _iter_template_config_files(project_root: Path) -> List[Path]:
    directory = (Path(project_root).resolve() / "元件库").resolve()
    if not directory.is_dir():
        return []
    files: List[Path] = []
    for p in sorted(directory.glob("*.json"), key=lambda x: x.as_posix()):
        if p.name == "templates_index.json":
            continue
        files.append(p.resolve())
    return files


def _resolve_included_template_files(*, project_root: Path, include_files: List[Path]) -> List[Path]:
    templates_dir = (Path(project_root).resolve() / "元件库").resolve()
    if not templates_dir.is_dir():
        raise FileNotFoundError(f"项目存档缺少 元件库/ 目录：{str(templates_dir)}")

    out: List[Path] = []
    seen: set[str] = set()
    for idx, raw in enumerate(list(include_files or [])):
        p = Path(raw).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"include_template_json_files[{idx}] 不存在：{str(p)}")
        if p.suffix.lower() != ".json":
            raise ValueError(f"include_template_json_files[{idx}] 不是 .json：{str(p)}")
        if p.name == "templates_index.json":
            continue
        try:
            p.relative_to(templates_dir)
        except ValueError:
            raise ValueError(
                f"include_template_json_files[{idx}] 必须位于项目存档 元件库/ 下：{str(p)} (root={str(templates_dir)})"
            )
        k = str(p).casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(p)
    out.sort(key=lambda x: x.as_posix().casefold())
    return out


_GIA_INSTANCE_ID_RE = re.compile(r"^(?:gia_)?(\d+)$", flags=re.IGNORECASE)
_SHAPE_INSTANCE_ID_RE = re.compile(r"^shape_(\d+)$", flags=re.IGNORECASE)


def _coerce_instance_id_int(value: object) -> Optional[int]:
    if isinstance(value, int):
        return int(value)
    if isinstance(value, str):
        text = str(value or "").strip()
        if text == "":
            return None
        m = _GIA_INSTANCE_ID_RE.match(text)
        if not m:
            return None
        digits = m.group(1)
        if digits == "":
            return None
        if not digits.isdigit():
            return None
        return int(digits)
    return None


def _coerce_shape_instance_id_int(value: object) -> Optional[int]:
    """
    兼容 shape-editor 导出的 decorations instanceId：shape_<n>

    约定：将 shape_<n> 映射到 0x40000000 + n（与真源常见 decorations unit_id 段位一致）。
    - shape_1 -> 1073741825 (0x40000001)
    """
    if isinstance(value, str):
        text = str(value or "").strip()
        if text == "":
            return None
        m = _SHAPE_INSTANCE_ID_RE.match(text)
        if not m:
            return None
        digits = m.group(1)
        if digits == "" or not digits.isdigit():
            return None
        suffix = int(digits)
        if suffix <= 0:
            return None
        return int(0x40000000 + int(suffix))
    return None


def _read_float_from_mapping(mapping_obj: object, key: str, default_value: float) -> float:
    if not isinstance(mapping_obj, Mapping):
        return float(default_value)
    v = mapping_obj.get(key)
    if isinstance(v, (int, float)):
        return float(v)
    return float(default_value)


def _read_vec3_from_mapping(mapping_obj: object, *, keys_xyz: Tuple[str, str, str], default_value: float) -> Tuple[float, float, float]:
    kx, ky, kz = keys_xyz
    return (
        _read_float_from_mapping(mapping_obj, kx, default_value),
        _read_float_from_mapping(mapping_obj, ky, default_value),
        _read_float_from_mapping(mapping_obj, kz, default_value),
    )


def _extract_decorations_list(template_obj: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    meta = template_obj.get("metadata")
    if not isinstance(meta, Mapping):
        return []
    common_inspector = meta.get("common_inspector")
    if not isinstance(common_inspector, Mapping):
        return []
    model = common_inspector.get("model")
    if not isinstance(model, Mapping):
        return []
    decorations = model.get("decorations")
    if not isinstance(decorations, list) or not decorations:
        return []
    out: List[Mapping[str, Any]] = []
    for item in decorations:
        if isinstance(item, Mapping):
            out.append(item)
    return out


def _extract_decorations_list_from_shape_editor_instance_obj(instance_obj: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    """
    shape-editor 导出的实体摆放 InstanceConfig：decorations 常见落点在
    `metadata.shape_editor.canvas_payload.common_inspector.model.decorations`（注意：canvas_payload 内没有 metadata）。
    """
    meta = instance_obj.get("metadata")
    if not isinstance(meta, Mapping):
        return []
    shape_editor = meta.get("shape_editor") or meta.get("shapeEditor")
    if not isinstance(shape_editor, Mapping):
        return []
    canvas_payload = shape_editor.get("canvas_payload") or shape_editor.get("canvasPayload")
    if not isinstance(canvas_payload, Mapping):
        return []
    common_inspector = canvas_payload.get("common_inspector") or canvas_payload.get("commonInspector")
    if not isinstance(common_inspector, Mapping):
        return []
    model = common_inspector.get("model")
    if not isinstance(model, Mapping):
        return []
    decorations = model.get("decorations")
    if not isinstance(decorations, list) or not decorations:
        return []
    out: List[Mapping[str, Any]] = []
    for item in decorations:
        if isinstance(item, Mapping):
            out.append(item)
    return out


def _try_extract_parent_template_id_int(template_obj: Mapping[str, Any]) -> Optional[int]:
    meta = template_obj.get("metadata")
    if isinstance(meta, Mapping):
        ugc = meta.get("ugc")
        if isinstance(ugc, Mapping) and isinstance(ugc.get("source_template_root_id_int"), int):
            return int(ugc.get("source_template_root_id_int"))
    template_id_text = str(template_obj.get("template_id") or "").strip()
    if template_id_text.isdigit():
        return int(template_id_text)
    return None


def extract_template_decoration_records_from_template_obj(
    *,
    template_obj: Mapping[str, Any],
    template_json_file: Path,
    parent_template_id_int: int | None = None,
) -> List[TemplateDecorationRecord]:
    """
    从单个模板 JSON 对象抽取 decorations 记录。
    """
    parent_template_id = int(parent_template_id_int) if isinstance(parent_template_id_int, int) else None
    if parent_template_id is None:
        parent_template_id = _try_extract_parent_template_id_int(template_obj)
    if parent_template_id is None:
        return []

    decorations = _extract_decorations_list(template_obj)
    if not decorations:
        return []

    out: List[TemplateDecorationRecord] = []
    seen_def_ids: set[int] = set()

    for idx, deco in enumerate(decorations):
        if not isinstance(deco, Mapping):
            continue

        source_gia = deco.get("source_gia")
        def_id_int = None
        if isinstance(source_gia, Mapping) and isinstance(source_gia.get("unit_id_int"), int):
            def_id_int = int(source_gia.get("unit_id_int"))
        if def_id_int is None:
            def_id_int = _coerce_instance_id_int(deco.get("instanceId"))
        if def_id_int is None:
            continue
        if int(def_id_int) in seen_def_ids:
            continue

        asset_id_int = None
        if isinstance(deco.get("assetId"), int):
            asset_id_int = int(deco.get("assetId"))
        elif isinstance(source_gia, Mapping) and isinstance(source_gia.get("asset_id_int"), int):
            asset_id_int = int(source_gia.get("asset_id_int"))
        if asset_id_int is None:
            continue

        unit_name = ""
        if isinstance(source_gia, Mapping) and isinstance(source_gia.get("unit_name"), str):
            unit_name = str(source_gia.get("unit_name") or "").strip()
        if unit_name == "":
            unit_name = str(deco.get("displayName") or "").strip()
        if unit_name == "":
            unit_name = f"decor_{int(def_id_int)}"

        transform = deco.get("transform")
        if not isinstance(transform, Mapping):
            transform = {}

        pos = _read_vec3_from_mapping(transform.get("pos"), keys_xyz=("x", "y", "z"), default_value=0.0)
        rot = _read_vec3_from_mapping(transform.get("rot"), keys_xyz=("x", "y", "z"), default_value=0.0)
        scale = _read_vec3_from_mapping(transform.get("scale"), keys_xyz=("x", "y", "z"), default_value=1.0)

        source_instance_id_text = str(deco.get("instanceId") or "").strip()
        parent_id_text = str(deco.get("parentId") or "").strip()

        out.append(
            TemplateDecorationRecord(
                def_id_int=int(def_id_int),
                parent_template_id_int=int(parent_template_id),
                asset_id_int=int(asset_id_int),
                name=str(unit_name),
                position=(float(pos[0]), float(pos[1]), float(pos[2])),
                rotation=(float(rot[0]), float(rot[1]), float(rot[2])),
                scale=(float(scale[0]), float(scale[1]), float(scale[2])),
                source_template_json_file=Path(template_json_file).resolve(),
                source_decoration_index=int(idx),
                source_decoration_instance_id=source_instance_id_text,
                source_parent_id=parent_id_text,
            )
        )
        seen_def_ids.add(int(def_id_int))

    return out


def extract_template_decoration_records_from_instance_obj(
    *,
    instance_obj: Mapping[str, Any],
    instance_json_file: Path,
    parent_template_id_int: int,
) -> List[TemplateDecorationRecord]:
    """
    从“实体摆放 InstanceConfig(JSON)”抽取 decorations records。

    用途：
    - 常规口径：`metadata.common_inspector.model.decorations`
    - shape-editor 口径：`metadata.shape_editor.canvas_payload.common_inspector.model.decorations`
      为了在游戏内可见，需要把这些 decorations 写回到 `.gil` 的 root27（attachments 挂到 parent_instance）。

    说明：
    - def_id_int 优先使用：source_gia.unit_id_int / gia_<digits>（可稳定对齐真源）
    - 对于 shape-editor 的 `shape_<n>`：为避免跨实例冲突，按 (instance_json_file, instanceId, idx) 做 crc32，映射到 0x40000000|low24
      （同一实例内若仍撞车则顺序 bump）。
    """
    decorations = _extract_decorations_list(instance_obj)
    if not decorations:
        decorations = _extract_decorations_list_from_shape_editor_instance_obj(instance_obj)
    if not decorations:
        return []

    parent_template_id = int(parent_template_id_int)

    out: List[TemplateDecorationRecord] = []
    seen_def_ids: set[int] = set()

    for idx, deco in enumerate(list(decorations)):
        if not isinstance(deco, Mapping):
            continue

        source_gia = deco.get("source_gia") or {}
        if not isinstance(source_gia, Mapping):
            source_gia = {}

        source_instance_id_text = str(deco.get("instanceId") or "").strip()
        parent_id_text = str(deco.get("parentId") or "").strip()

        def_id_int: int | None = None
        if isinstance(source_gia.get("unit_id_int"), int):
            def_id_int = int(source_gia.get("unit_id_int"))
        if def_id_int is None:
            def_id_int = _coerce_instance_id_int(source_instance_id_text)
        if def_id_int is None:
            # shape-editor / 其它非数值 instanceId：生成稳定的 0x40000000 段位 ID，避免跨实例冲突
            key_text = f"{str(Path(instance_json_file).resolve())}:{source_instance_id_text}:{int(idx)}"
            h24 = int(zlib.crc32(key_text.encode("utf-8")) & 0x00FFFFFF)
            if h24 == 0:
                h24 = 1
            def_id_int = int(0x40000000 | int(h24))

        asset_id_int = deco.get("assetId")
        if not isinstance(asset_id_int, int) or int(asset_id_int) <= 0:
            raise ValueError(f"instance decorations[{idx}].assetId 缺失或非法：{asset_id_int!r} (file={str(Path(instance_json_file).resolve())})")

        display_name = str(deco.get("displayName") or "").strip()
        if display_name == "":
            display_name = str(source_gia.get("unit_name") or "").strip() or f"decor_{int(def_id_int)}"

        transform = deco.get("transform") or {}
        if not isinstance(transform, Mapping):
            transform = {}
        pos = _read_vec3_from_mapping(transform.get("pos"), keys_xyz=("x", "y", "z"), default_value=0.0)
        rot = _read_vec3_from_mapping(transform.get("rot"), keys_xyz=("x", "y", "z"), default_value=0.0)
        scale = _read_vec3_from_mapping(transform.get("scale"), keys_xyz=("x", "y", "z"), default_value=1.0)

        # 同一 instance 内 def_id 不应重复；若发生碰撞，顺序 bump（保持在 0x40000000 段位）。
        candidate = int(def_id_int)
        while candidate in seen_def_ids:
            low24 = int(candidate) & 0x00FFFFFF
            low24 = (int(low24) + 1) & 0x00FFFFFF
            if low24 == 0:
                low24 = 1
            candidate = int(0x40000000 | int(low24))
        def_id_int = int(candidate)
        seen_def_ids.add(int(def_id_int))

        out.append(
            TemplateDecorationRecord(
                def_id_int=int(def_id_int),
                parent_template_id_int=int(parent_template_id),
                asset_id_int=int(asset_id_int),
                name=str(display_name),
                position=(float(pos[0]), float(pos[1]), float(pos[2])),
                rotation=(float(rot[0]), float(rot[1]), float(rot[2])),
                scale=(float(scale[0]), float(scale[1]), float(scale[2])),
                source_template_json_file=Path(instance_json_file).resolve(),
                source_decoration_index=int(idx),
                source_decoration_instance_id=str(source_instance_id_text),
                source_parent_id=str(parent_id_text),
            )
        )

    return list(out)


def apply_instance_decorations_writeback_to_payload_root(
    *,
    payload_root: JsonDict,
    parent_instance_id_int: int,
    decoration_records: List[TemplateDecorationRecord],
) -> Dict[str, Any]:
    """
    将“实例级 decorations records”写回到 payload_root['27']（root27）。

    与 `apply_template_decorations_writeback_to_payload_root` 的差异：
    - attachments 仅挂到给定的 parent_instance_id_int（而不是按 template_id 反查所有父实例）。
    """
    records = list(decoration_records or [])
    if not records:
        return {
            "decorations_total": 0,
            "definitions_added": 0,
            "definitions_updated": 0,
            "attachments_added": 0,
            "attachments_updated": 0,
        }

    def _vec3_as_binary_data_text(vec: Vec3, *, empty_if_zero: bool) -> str:
        x, y, z = vec
        if empty_if_zero and float(x) == 0.0 and float(y) == 0.0 and float(z) == 0.0:
            # 参考样本：零旋转常见为 `<binary_data> `（empty bytes）。
            return format_binary_data_hex_text(b"")
        msg: JsonDict = {}
        if float(x) != 0.0:
            msg["1"] = float(x)
        if float(y) != 0.0:
            msg["2"] = float(y)
        if float(z) != 0.0:
            msg["3"] = float(z)
        return str(numeric_message_to_binary_data_text(msg))

    def _build_vec3_message_omit_zeros(x: float, y: float, z: float) -> JsonDict:
        msg: JsonDict = {}
        if float(x) != 0.0:
            msg["1"] = float(x)
        if float(y) != 0.0:
            msg["2"] = float(y)
        if float(z) != 0.0:
            msg["3"] = float(z)
        return msg

    def _write_root27_attachment_entry_root5_style(entry: JsonDict, *, rec: TemplateDecorationRecord, parent_id_int: int) -> None:
        """
        root27.2 attachment 的 root5-style（对齐 `tmp_shape_editor_instance_decorations.gil` 观测样本）：
        - root27 仅写 `2`（attachments），不写 `1`（definitions）
        - entry['12'] 固定为 `<binary_data> `（empty bytes），不写 `{1: def_id}` 引用
        - transform：
          - pos：vec3 dict（省略 0 值字段）
          - rot：`<binary_data> ...`（nested message bytes；零旋转为 empty bytes）
          - scale：vec3 dict（必须显式写入 x/y/z；缺失会退化为 0 而不是 1）
        """
        entry["2"] = int(rec.asset_id_int)

        meta_list = _ensure_path_list_allow_scalar(entry, "4")
        _upsert_meta_name(meta_list, rec.name)
        _upsert_meta_parent_id_int(meta_list, int(parent_id_int))

        sections = _ensure_path_list_allow_scalar(entry, "5")
        seg_transform = _find_or_create_section(sections, 1)
        seg_transform["11"] = {
            "1": _build_vec3_message_omit_zeros(rec.position[0], rec.position[1], rec.position[2]),
            "2": _vec3_as_binary_data_text(rec.rotation, empty_if_zero=True),
            "3": _build_vec3_message(rec.scale[0], rec.scale[1], rec.scale[2]),
        }

        seg_flags = _find_or_create_section(sections, 5)
        seg_flags["15"] = {"1": 1, "2": 1}

        seg_unknown = _find_or_create_section(sections, 2)
        seg_unknown["12"] = format_binary_data_hex_text(b"")

        # root5-style：field12 保持 empty bytes。
        entry["12"] = format_binary_data_hex_text(b"")

    root27_value = payload_root.get("27")
    root27_msg = _coerce_section_message(root27_value)
    if root27_msg is None:
        root27_msg = {}
    payload_root["27"] = root27_msg

    list2 = _ensure_path_list_allow_scalar(root27_msg, "2")

    pid = int(parent_instance_id_int)

    # root5-style：先移除当前 parent_id 旧挂载，再整批重建（支持删除/重排，避免累积重复）。
    removed_entries: List[JsonDict] = []
    kept_entries: List[Any] = []
    for it in list2:
        if not isinstance(it, dict):
            kept_entries.append(it)
            continue
        meta_list = _ensure_path_list_allow_scalar(it, "4")
        parent0 = _extract_meta_parent_id_int(meta_list)
        if isinstance(parent0, int) and int(parent0) == int(pid):
            removed_entries.append(it)
            continue
        kept_entries.append(it)
    list2[:] = list(kept_entries)

    # 复用旧 id（稳定）：按 id 升序复用到新条目；不够则继续分配。
    reused_ids: List[int] = []
    for it in removed_entries:
        eid = it.get("1")
        if isinstance(eid, int):
            reused_ids.append(int(eid))
    reused_ids.sort()

    used_ids: set[int] = set()
    # id 空间与 root27.1(defs)/root27.2(atts) 共用；为稳妥起见把 defs/atts 的 id 都加入 used_ids。
    defs_value0 = root27_msg.get("1")
    defs_items0: List[Any]
    if isinstance(defs_value0, list):
        defs_items0 = list(defs_value0)
    elif defs_value0 is None:
        defs_items0 = []
    else:
        defs_items0 = [defs_value0]
    for it in defs_items0:
        if isinstance(it, dict) and isinstance(it.get("1"), int):
            used_ids.add(int(it.get("1")))
    for it in list2:
        if isinstance(it, dict) and isinstance(it.get("1"), int):
            used_ids.add(int(it.get("1")))

    # 参考样本：首个 attachment id 常见为 0x40000001（1073741825）；避免从 0x40000000 起步。
    next_id = int(max(used_ids) + 1) if used_ids else 1073741825
    if int(next_id) < 1073741825:
        next_id = 1073741825

    def _alloc_new_id() -> int:
        nonlocal next_id
        while int(next_id) in used_ids:
            next_id += 1
        out_id = int(next_id)
        used_ids.add(int(out_id))
        next_id += 1
        return int(out_id)

    attachments_added = 0
    attachments_updated = 0
    attachment_ids: List[int] = []

    for rec in records:
        if reused_ids:
            eid = int(reused_ids.pop(0))
            if eid in used_ids:
                eid = int(_alloc_new_id())
            else:
                used_ids.add(int(eid))
        else:
            eid = int(_alloc_new_id())
        new_entry: JsonDict = {"1": int(eid)}
        _write_root27_attachment_entry_root5_style(new_entry, rec=rec, parent_id_int=int(pid))
        list2.append(new_entry)
        attachments_added += 1
        attachment_ids.append(int(eid))

    return {
        "decorations_total": len(records),
        "definitions_added": 0,
        "definitions_updated": 0,
        "attachments_added": int(attachments_added),
        "attachments_updated": int(attachments_updated),
        # root5-style: 父实例需要在 root4/5/1 meta(id=40).50.501 写入 attachment_id 的 varint stream。
        # 这里返回 ids，供调用方补齐父实例引用（对齐真源样本）。
        "attachment_ids": list(attachment_ids),
    }


def scan_template_decoration_records(
    *,
    project_root: Path,
    include_template_json_files: List[Path] | None = None,
) -> List[TemplateDecorationRecord]:
    project_root = Path(project_root).resolve()

    template_files: List[Path]
    if include_template_json_files is not None:
        template_files = _resolve_included_template_files(project_root=project_root, include_files=list(include_template_json_files))
    else:
        template_files = _iter_template_config_files(project_root)

    out: List[TemplateDecorationRecord] = []
    for template_file in template_files:
        obj = json.loads(Path(template_file).read_text(encoding="utf-8"))
        if not isinstance(obj, Mapping):
            continue
        out.extend(
            extract_template_decoration_records_from_template_obj(
                template_obj=obj,
                template_json_file=Path(template_file).resolve(),
                parent_template_id_int=None,
            )
        )

    # 稳定去重：以 def_id_int 为主键；若冲突且关键字段不一致则 fail-fast。
    dedup: Dict[int, TemplateDecorationRecord] = {}
    for it in out:
        prev = dedup.get(int(it.def_id_int))
        if prev is None:
            dedup[int(it.def_id_int)] = it
            continue
        if int(prev.parent_template_id_int) != int(it.parent_template_id_int) or int(prev.asset_id_int) != int(it.asset_id_int):
            raise ValueError(
                "模板 decorations def_id 冲突（不同模板/资源复用导致主键不唯一）。"
                f"def_id={int(it.def_id_int)} prev_template={int(prev.parent_template_id_int)} new_template={int(it.parent_template_id_int)}"
            )

    return list(dedup.values())


def _ensure_path_dict(root: JsonDict, key: str) -> JsonDict:
    value = root.get(key)
    if isinstance(value, dict):
        return value
    if value is None:
        new_value: JsonDict = {}
        root[key] = new_value
        return new_value
    raise ValueError(f"expected dict at key={key!r}, got {type(value).__name__}")


def _ensure_path_list_allow_scalar(root: JsonDict, key: str) -> List[Any]:
    value = root.get(key)
    if isinstance(value, list):
        return value
    if value is None:
        new_value: List[Any] = []
        root[key] = new_value
        return new_value
    root[key] = [value]
    return root[key]


def _coerce_section_message(value: Any) -> Optional[JsonDict]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.startswith("<binary_data>"):
        msg = binary_data_text_to_numeric_message(value, max_depth=16)
        if not isinstance(msg, dict):
            raise TypeError(f"binary_data_text_to_numeric_message returned {type(msg).__name__}")
        return dict(msg)
    return None


def _coerce_repeated_message_item_to_dict(item: Any) -> Optional[JsonDict]:
    """
    dump-json 中 repeated message 的元素可能是：
    - dict（已解码）
    - "<binary_data> ..."（未解码的 message bytes）
    """
    if isinstance(item, dict):
        return item
    if isinstance(item, str) and item.startswith("<binary_data>"):
        msg = binary_data_text_to_numeric_message(item, max_depth=16)
        if isinstance(msg, dict):
            return dict(msg)
    return None


def _extract_template_id_int_from_instance_record(record: JsonDict) -> Optional[int]:
    v2 = record.get("2")
    if isinstance(v2, dict) and isinstance(v2.get("1"), int):
        return int(v2.get("1"))
    if isinstance(v2, list) and v2 and isinstance(v2[0], dict) and isinstance(v2[0].get("1"), int):
        return int(v2[0].get("1"))
    return None


def _extract_instance_id_int_from_instance_record(record: JsonDict) -> Optional[int]:
    v1 = record.get("1")
    if isinstance(v1, int):
        return int(v1)
    if isinstance(v1, list) and v1 and isinstance(v1[0], int):
        return int(v1[0])
    return None


def collect_parent_instance_ids_by_template_id_from_payload_root(payload_root: JsonDict) -> Dict[int, List[int]]:
    """
    从 `.gil` payload_root 中收集“父实例ID”：用于 root27.2 的 meta 40/50/502。

    经验：父实例可能出现在多个段（至少包含 root5 与 root8），两者都按 record['2']['1'] 作为 template_id。
    """
    collected: Dict[int, set[int]] = {}
    for section_key in ("5", "8"):
        section_msg = _coerce_section_message(payload_root.get(section_key))
        if section_msg is None:
            continue
        entries = _ensure_path_list_allow_scalar(section_msg, "1")
        for rec in entries:
            if not isinstance(rec, dict):
                continue
            template_id_int = _extract_template_id_int_from_instance_record(rec)
            if not isinstance(template_id_int, int):
                continue
            instance_id_int = _extract_instance_id_int_from_instance_record(rec)
            if not isinstance(instance_id_int, int):
                continue
            collected.setdefault(int(template_id_int), set()).add(int(instance_id_int))

    return {tid: sorted(list(ids)) for tid, ids in collected.items()}


def _try_extract_meta_name(meta_list: List[Any]) -> str:
    for item in list(meta_list):
        msg = _coerce_repeated_message_item_to_dict(item)
        if not isinstance(msg, dict):
            continue
        if msg.get("1") != 1:
            continue
        v11 = msg.get("11")
        if isinstance(v11, dict) and isinstance(v11.get("1"), str):
            return str(v11.get("1")).strip()
        if isinstance(v11, str):
            return str(v11).strip()
    return ""


def _upsert_meta_name(meta_list: List[Any], name: str) -> None:
    name = str(name or "").strip()
    if name == "":
        return
    for idx, item in enumerate(list(meta_list)):
        msg = _coerce_repeated_message_item_to_dict(item)
        if not isinstance(msg, dict):
            continue
        if msg.get("1") != 1:
            continue
        # 若原本为 bytes message，这里替换为 dict 以便后续可继续 patch（最终编码结果一致）。
        meta_list[idx] = msg
        msg["11"] = {"1": str(name)}
        return
    meta_list.insert(0, {"1": 1, "11": {"1": str(name)}})


def _extract_meta_parent_id_int(meta_list: List[Any]) -> Optional[int]:
    for item in list(meta_list):
        msg = _coerce_repeated_message_item_to_dict(item)
        if not isinstance(msg, dict):
            continue
        if msg.get("1") != 40:
            continue
        v50 = msg.get("50")
        if isinstance(v50, dict) and isinstance(v50.get("502"), int):
            return int(v50.get("502"))
        if isinstance(v50, str) and v50.startswith("<binary_data>"):
            msg50 = binary_data_text_to_numeric_message(v50, max_depth=16)
            if isinstance(msg50, dict) and isinstance(msg50.get("502"), int):
                return int(msg50.get("502"))
    return None


def _upsert_meta_parent_id_int(meta_list: List[Any], parent_id_int: int) -> None:
    for idx, item in enumerate(list(meta_list)):
        msg = _coerce_repeated_message_item_to_dict(item)
        if not isinstance(msg, dict):
            continue
        if msg.get("1") != 40:
            continue
        meta_list[idx] = msg
        v50 = msg.get("50")
        if isinstance(v50, str) and v50.startswith("<binary_data>"):
            msg50 = binary_data_text_to_numeric_message(v50, max_depth=16)
            v50 = dict(msg50) if isinstance(msg50, dict) else {}
        if not isinstance(v50, dict):
            v50 = {}
        msg["50"] = v50
        v50["502"] = int(parent_id_int)
        return
    meta_list.append({"1": 40, "50": {"502": int(parent_id_int)}})


def _upsert_meta40_field50_501_varint_stream(meta_list: List[Any], attachment_ids: List[int]) -> bool:
    """
    对齐观测样本：父实例 meta(id=40).field50 为 nested message，其中：
    - field501 为 packed varint stream，存放 root27.2 attachment_id 列表。

    注意：meta_list 的元素可能是 dict 或 `<binary_data> ...`（未解码 message bytes），需兼容。
    """
    ids = [int(x) for x in list(attachment_ids or []) if isinstance(x, int)]
    if not ids:
        return False

    from ugc_file_tools.gil_dump_codec.protobuf_like import encode_varint

    raw = b"".join(encode_varint(int(x)) for x in sorted(set(ids)))
    blob = format_binary_data_hex_text(raw)

    item40: Optional[JsonDict] = None
    item40_idx: Optional[int] = None
    for idx, item in enumerate(list(meta_list)):
        msg = _coerce_repeated_message_item_to_dict(item)
        if not isinstance(msg, dict):
            continue
        if msg.get("1") != 40:
            continue
        meta_list[idx] = msg
        item40 = msg
        item40_idx = int(idx)
        break
    if item40 is None:
        item40 = {"1": 40}
        meta_list.append(item40)
        item40_idx = int(len(meta_list) - 1)

    field50 = item40.get("50")
    if isinstance(field50, str) and field50.startswith("<binary_data>"):
        msg50 = binary_data_text_to_numeric_message(field50, max_depth=16)
        field50 = dict(msg50) if isinstance(msg50, dict) else {}
    if not isinstance(field50, dict):
        field50 = {}
    item40["50"] = field50

    prev = field50.get("501")
    field50["501"] = str(blob)

    # 将 meta40 写回 list（确保替换已解码 item 的情况生效）
    if isinstance(item40_idx, int) and 0 <= int(item40_idx) < len(meta_list):
        meta_list[int(item40_idx)] = item40

    return prev != field50.get("501")


def _find_or_create_section(section_list: List[Any], section_id_int: int) -> JsonDict:
    for item in section_list:
        if not isinstance(item, dict):
            continue
        if item.get("1") == int(section_id_int):
            return item
    new_item: JsonDict = {"1": int(section_id_int)}
    section_list.append(new_item)
    return new_item


def _build_vec3_message(x: float, y: float, z: float) -> JsonDict:
    return {"1": float(x), "2": float(y), "3": float(z)}


def _vec3_as_message_or_empty_bytes(x: float, y: float, z: float, *, empty_if_zero: bool) -> JsonDict | str:
    if bool(empty_if_zero) and float(x) == 0.0 and float(y) == 0.0 and float(z) == 0.0:
        # 观测样例：模板/元件 decorations 的 position/rotation 在全零时常写为 empty bytes（而不是显式 {1:0,2:0,3:0}）。
        return format_binary_data_hex_text(b"")
    return _build_vec3_message(float(x), float(y), float(z))


def _write_root27_definition_entry(entry: JsonDict, rec: TemplateDecorationRecord) -> None:
    entry["1"] = int(rec.def_id_int)
    entry["2"] = int(rec.asset_id_int)
    entry["3"] = 1

    meta_list = _ensure_path_list_allow_scalar(entry, "4")
    _upsert_meta_name(meta_list, rec.name)
    _upsert_meta_parent_id_int(meta_list, int(rec.parent_template_id_int))

    sections = _ensure_path_list_allow_scalar(entry, "5")
    seg_transform = _find_or_create_section(sections, 1)
    seg_transform["11"] = {
        "1": _vec3_as_message_or_empty_bytes(rec.position[0], rec.position[1], rec.position[2], empty_if_zero=True),
        "2": _vec3_as_message_or_empty_bytes(rec.rotation[0], rec.rotation[1], rec.rotation[2], empty_if_zero=True),
        "3": _build_vec3_message(rec.scale[0], rec.scale[1], rec.scale[2]),
    }

    seg_flags = _find_or_create_section(sections, 5)
    seg_flags["15"] = {"1": 1, "2": 1}

    seg_unknown = _find_or_create_section(sections, 2)
    seg_unknown["12"] = format_binary_data_hex_text(b"")

    entry["11"] = format_binary_data_hex_text(b"")


def _write_root27_attachment_entry(entry: JsonDict, *, rec: TemplateDecorationRecord, parent_instance_id_int: int) -> None:
    entry["2"] = int(rec.asset_id_int)

    meta_list = _ensure_path_list_allow_scalar(entry, "4")
    _upsert_meta_name(meta_list, rec.name)
    _upsert_meta_parent_id_int(meta_list, int(parent_instance_id_int))

    sections = _ensure_path_list_allow_scalar(entry, "5")
    seg_transform = _find_or_create_section(sections, 1)
    seg_transform["11"] = {
        "1": _vec3_as_message_or_empty_bytes(rec.position[0], rec.position[1], rec.position[2], empty_if_zero=True),
        "2": _vec3_as_message_or_empty_bytes(rec.rotation[0], rec.rotation[1], rec.rotation[2], empty_if_zero=True),
        "3": _build_vec3_message(rec.scale[0], rec.scale[1], rec.scale[2]),
    }

    seg_flags = _find_or_create_section(sections, 5)
    seg_flags["15"] = {"1": 1, "2": 1}

    seg_unknown = _find_or_create_section(sections, 2)
    seg_unknown["12"] = format_binary_data_hex_text(b"")

    entry["12"] = {"1": int(rec.def_id_int)}


def apply_template_decorations_writeback_to_payload_root(
    *,
    payload_root: JsonDict,
    decoration_records: List[TemplateDecorationRecord],
) -> Dict[str, Any]:
    """
    将 decorations 写回到 payload_root['27']（root27）。

    策略：
    - root27.1：按 def_id_int upsert；meta 502 写 parent_template_id_int。
    - root27.2：按 (parent_instance_id_int, def_id_int) upsert；meta 502 写 parent_instance_id_int。
      parent_instance_id_int 从 payload_root 的 root5/root8 里按 template_id 反查。

    额外补丁（对齐“元件挂装饰物”真源样例）：
    - root22：当存在 decorations 时，确保包含 `ModelDisplay/PropertyAttachArchetypeModel` 等声明（否则编辑器侧可能不渲染）。
    - 模板 entry（root4/4/1）：meta(id=40).field50.501 写入 def_id 的 packed varint stream（definitions 引用表）。
    - 父实例 entry（root5/root8）：meta(id=40).field50.501 写入 attachment_id 的 packed varint stream（attachments 引用表）。
    """
    records = list(decoration_records or [])
    if not records:
        return {
            "decorations_total": 0,
            "definitions_added": 0,
            "definitions_updated": 0,
            "attachments_added": 0,
            "attachments_updated": 0,
        }

    def _ensure_root22_decorations_support(payload_root_obj: JsonDict) -> bool:
        """
        观测样例：
        - 无 decorations：root22.1="PropertyTransform", root22.2="<binary_data> 01"
        - 有 decorations：root22.1=["PropertyTransform","ModelDisplay","PropertyAttachArchetypeModel"],
          root22.2="<binary_data> 01 01 01"
        """
        root22_msg = _coerce_section_message(payload_root_obj.get("22"))
        if root22_msg is None:
            root22_msg = {}
        payload_root_obj["22"] = root22_msg

        required = ["PropertyTransform", "ModelDisplay", "PropertyAttachArchetypeModel"]

        cur1 = root22_msg.get("1")
        names: List[str] = []
        if isinstance(cur1, str) and str(cur1).strip() != "":
            names = [str(cur1).strip()]
        elif isinstance(cur1, list):
            for it in cur1:
                if isinstance(it, str) and str(it).strip() != "":
                    names.append(str(it).strip())

        # 保序去重：先保留已有，再补齐 required
        seen: set[str] = set()
        names2: List[str] = []
        for it in names + required:
            if it in seen:
                continue
            seen.add(it)
            names2.append(it)

        root22_msg["1"] = list(names2)
        root22_msg["2"] = format_binary_data_hex_text(b"\x01" * int(len(names2)))
        return True

    _ensure_root22_decorations_support(payload_root)

    parents_by_template = collect_parent_instance_ids_by_template_id_from_payload_root(payload_root)

    root27_value = payload_root.get("27")
    root27_msg = _coerce_section_message(root27_value)
    if root27_msg is None:
        root27_msg = {}
    payload_root["27"] = root27_msg

    list1 = _ensure_path_list_allow_scalar(root27_msg, "1")
    list2 = _ensure_path_list_allow_scalar(root27_msg, "2")

    # === ID 分配（0x40000000 段位） ===
    # 经验：同一 `.gil` 内其它段也可能占用 0x400000xx（例如 UI/布局索引等），因此 attachment_id 需避开全局已用值。
    ID_MIN = 0x40000000
    ID_MAX = 0x40FFFFFF

    def _collect_used_ids_in_id_space(obj: object, out: set[int]) -> None:
        if isinstance(obj, bool):
            return
        if isinstance(obj, int):
            v = int(obj)
            if ID_MIN <= v <= ID_MAX:
                out.add(v)
            return
        if isinstance(obj, list):
            for it in obj:
                _collect_used_ids_in_id_space(it, out)
            return
        if isinstance(obj, dict):
            for v in obj.values():
                _collect_used_ids_in_id_space(v, out)
            return

    used_ids: set[int] = set()
    _collect_used_ids_in_id_space(payload_root, used_ids)
    for rec in records:
        used_ids.add(int(rec.def_id_int))

    def _first_int(value: object) -> Optional[int]:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return int(value)
        if isinstance(value, list) and value and isinstance(value[0], int) and not isinstance(value[0], bool):
            return int(value[0])
        return None

    def_by_id: Dict[int, JsonDict] = {}
    for it in list1:
        if not isinstance(it, dict):
            continue
        eid = _first_int(it.get("1"))
        if isinstance(eid, int):
            def_by_id[int(eid)] = it

    attachment_by_key: Dict[Tuple[int, int], JsonDict] = {}
    for it in list2:
        if not isinstance(it, dict):
            continue
        meta_list = _ensure_path_list_allow_scalar(it, "4")
        parent_id = _extract_meta_parent_id_int(meta_list)
        ref = it.get("12")
        def_id = _first_int(ref.get("1")) if isinstance(ref, dict) else _first_int(ref)
        if isinstance(parent_id, int) and isinstance(def_id, int):
            attachment_by_key[(int(parent_id), int(def_id))] = it

    # next id for new attachment entries
    next_id = int(0x40000002)
    while int(next_id) in used_ids:
        next_id += 1
    if int(next_id) > ID_MAX:
        raise ValueError(f"attachment_id 可用空间耗尽：next_id={int(next_id)}")

    def _alloc_new_id() -> int:
        nonlocal next_id
        while int(next_id) in used_ids:
            next_id += 1
        if int(next_id) > ID_MAX:
            raise ValueError(f"attachment_id 可用空间耗尽：next_id={int(next_id)}")
        out_id = int(next_id)
        used_ids.add(int(out_id))
        next_id += 1
        return int(out_id)

    definitions_added = 0
    definitions_updated = 0
    attachments_added = 0
    attachments_updated = 0
    parents_touched: set[int] = set()
    templates_touched: Dict[int, set[int]] = {}

    for rec in records:
        def_entry = def_by_id.get(int(rec.def_id_int))
        if def_entry is None:
            def_entry = {}
            list1.append(def_entry)
            def_by_id[int(rec.def_id_int)] = def_entry
            definitions_added += 1
        else:
            definitions_updated += 1

        _write_root27_definition_entry(def_entry, rec)
        templates_touched.setdefault(int(rec.parent_template_id_int), set()).add(int(rec.def_id_int))

        parent_instance_ids = parents_by_template.get(int(rec.parent_template_id_int)) or []
        for parent_instance_id_int in list(parent_instance_ids):
            key = (int(parent_instance_id_int), int(rec.def_id_int))
            attach_entry = attachment_by_key.get(key)
            if attach_entry is None:
                attach_entry = {"1": int(_alloc_new_id())}
                list2.append(attach_entry)
                attachment_by_key[key] = attach_entry
                attachments_added += 1
            else:
                attachments_updated += 1

            _write_root27_attachment_entry(attach_entry, rec=rec, parent_instance_id_int=int(parent_instance_id_int))
            parents_touched.add(int(parent_instance_id_int))

    # === 同步父实例引用：meta(id=40).field50.501 ===
    # 背景：root27.2 的挂载记录存在还不够，父实例需要显式持有 attachment_id 列表（packed varint stream）。
    # 观测：父实例可能在 root5 或 root8；两者都按 record['1'] 为 instance_id。
    parents_patched = 0
    if parents_touched:
        parent_entry_by_id: Dict[int, JsonDict] = {}
        for section_key in ("5", "8"):
            sec_value = payload_root.get(section_key)
            sec_msg = _coerce_section_message(sec_value)
            if sec_msg is None:
                continue
            payload_root[section_key] = sec_msg
            recs = _ensure_path_list_allow_scalar(sec_msg, "1")
            for rec in recs:
                if not isinstance(rec, dict):
                    continue
                iid = _extract_instance_id_int_from_instance_record(rec)
                if isinstance(iid, int):
                    parent_entry_by_id[int(iid)] = rec

        # 收集每个 parent 的 attachment_id 列表（以 root27.2 为准，避免覆盖时漏掉既有挂载）。
        attachment_ids_by_parent: Dict[int, List[int]] = {int(pid): [] for pid in parents_touched}
        for att in list2:
            if not isinstance(att, dict):
                continue
            aid = _first_int(att.get("1"))
            if not isinstance(aid, int):
                continue
            meta_list = _ensure_path_list_allow_scalar(att, "4")
            pid = _extract_meta_parent_id_int(meta_list)
            if not isinstance(pid, int) or int(pid) not in attachment_ids_by_parent:
                continue
            attachment_ids_by_parent[int(pid)].append(int(aid))

        for pid, ids in attachment_ids_by_parent.items():
            parent_entry = parent_entry_by_id.get(int(pid))
            if not isinstance(parent_entry, dict):
                continue
            meta_list_parent = _ensure_path_list_allow_scalar(parent_entry, "5")
            changed = _upsert_meta40_field50_501_varint_stream(meta_list_parent, [int(x) for x in ids if isinstance(x, int)])
            if changed:
                parents_patched += 1

    # === 同步模板引用：meta(id=40).field50.501（def_id packed varints）===
    templates_patched = 0
    if templates_touched:
        templates_section = _coerce_section_message(payload_root.get("4"))
        if isinstance(templates_section, dict):
            payload_root["4"] = templates_section
            tpl_entries = _ensure_path_list_allow_scalar(templates_section, "1")
            tpl_entry_by_id: Dict[int, JsonDict] = {}
            for e in tpl_entries:
                if not isinstance(e, dict):
                    continue
                tid0 = _first_int(e.get("1"))
                if isinstance(tid0, int):
                    tpl_entry_by_id[int(tid0)] = e

            for tpl_id_int, def_ids_set in templates_touched.items():
                tpl_entry = tpl_entry_by_id.get(int(tpl_id_int))
                if not isinstance(tpl_entry, dict):
                    continue
                meta_list_tpl = _ensure_path_list_allow_scalar(tpl_entry, "6")
                changed = _upsert_meta40_field50_501_varint_stream(
                    meta_list_tpl,
                    sorted([int(x) for x in def_ids_set if isinstance(x, int)]),
                )
                if changed:
                    templates_patched += 1

    return {
        "decorations_total": len(records),
        "definitions_added": int(definitions_added),
        "definitions_updated": int(definitions_updated),
        "attachments_added": int(attachments_added),
        "attachments_updated": int(attachments_updated),
        "parents_with_attachments_touched": int(len(parents_touched)),
        "parents_field50_501_patched": int(parents_patched),
        "templates_with_definitions_touched": int(len(templates_touched)),
        "templates_field50_501_patched": int(templates_patched),
    }


def extract_template_decoration_records_from_root27_definitions_in_payload_root(*, payload_root: JsonDict) -> List[TemplateDecorationRecord]:
    """
    从 `.gil` 当前 payload_root 的 root27.1(definitions) 反解出 decorations records。

    用途：
    - 当同一次写回中新增/覆盖了实例(root5/1)，模板阶段可能无法反查到“新实例ID”，导致 root27.2 未挂载；
      在实例写回阶段可基于“已经写入的 root27.1(defs)”补齐 root27.2(atts)。
    - 该函数只做“从现有 defs 反推 records”，不依赖项目存档的模板 JSON 输入。
    """
    if not isinstance(payload_root, dict):
        raise TypeError(f"payload_root must be dict, got {type(payload_root).__name__}")

    root27_msg = _coerce_section_message(payload_root.get("27"))
    if root27_msg is None:
        return []

    defs_value = root27_msg.get("1")
    def _ensure_list_allow_scalar(value: object) -> List[object]:
        if isinstance(value, list):
            return list(value)
        if value is None:
            return []
        return [value]

    defs: List[JsonDict] = [d for d in _ensure_list_allow_scalar(defs_value) if isinstance(d, dict)]
    if not defs:
        return []

    def _first_int(value: object) -> Optional[int]:
        if isinstance(value, int):
            return int(value)
        if isinstance(value, list) and value and isinstance(value[0], int):
            return int(value[0])
        return None

    def _read_vec3(value: object, *, default_value: float) -> Vec3:
        if isinstance(value, dict):
            x = value.get("1")
            y = value.get("2")
            z = value.get("3")
            return (
                float(x) if isinstance(x, (int, float)) else float(default_value),
                float(y) if isinstance(y, (int, float)) else float(default_value),
                float(z) if isinstance(z, (int, float)) else float(default_value),
            )
        if isinstance(value, str) and value.startswith("<binary_data>"):
            msg = binary_data_text_to_numeric_message(value, max_depth=16)
            if isinstance(msg, dict):
                x = msg.get("1")
                y = msg.get("2")
                z = msg.get("3")
                return (
                    float(x) if isinstance(x, (int, float)) else float(default_value),
                    float(y) if isinstance(y, (int, float)) else float(default_value),
                    float(z) if isinstance(z, (int, float)) else float(default_value),
                )
        return (float(default_value), float(default_value), float(default_value))

    out: List[TemplateDecorationRecord] = []
    dummy_source_file = Path("__root27_defs__")
    for def_entry in defs:
        def_id_int = _first_int(def_entry.get("1"))
        asset_id_int = _first_int(def_entry.get("2"))
        if not isinstance(def_id_int, int) or not isinstance(asset_id_int, int):
            continue

        meta_list = _ensure_list_allow_scalar(def_entry.get("4"))
        name = _try_extract_meta_name(meta_list)
        if name == "":
            name = f"decor_{int(def_id_int)}"
        parent_template_id_int = _extract_meta_parent_id_int(meta_list)
        if not isinstance(parent_template_id_int, int):
            continue

        pos: Vec3 = (0.0, 0.0, 0.0)
        rot: Vec3 = (0.0, 0.0, 0.0)
        scale: Vec3 = (1.0, 1.0, 1.0)

        sections = _ensure_list_allow_scalar(def_entry.get("5"))
        seg_transform = next((s for s in sections if isinstance(s, dict) and s.get("1") == 1), None)
        if isinstance(seg_transform, dict) and isinstance(seg_transform.get("11"), dict):
            container = seg_transform.get("11")
            pos = _read_vec3(container.get("1"), default_value=0.0)
            rot = _read_vec3(container.get("2"), default_value=0.0)
            scale = _read_vec3(container.get("3"), default_value=1.0)

        out.append(
            TemplateDecorationRecord(
                def_id_int=int(def_id_int),
                parent_template_id_int=int(parent_template_id_int),
                asset_id_int=int(asset_id_int),
                name=str(name),
                position=pos,
                rotation=rot,
                scale=scale,
                source_template_json_file=dummy_source_file,
                source_decoration_index=-1,
                source_decoration_instance_id="",
                source_parent_id="",
            )
        )

    return out


__all__ = [
    "TemplateDecorationRecord",
    "extract_template_decoration_records_from_template_obj",
    "extract_template_decoration_records_from_instance_obj",
    "extract_template_decoration_records_from_root27_definitions_in_payload_root",
    "scan_template_decoration_records",
    "collect_parent_instance_ids_by_template_id_from_payload_root",
    "apply_instance_decorations_writeback_to_payload_root",
    "apply_template_decorations_writeback_to_payload_root",
]

