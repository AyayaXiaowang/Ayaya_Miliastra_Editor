from __future__ import annotations

import runpy
import time
import zlib
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from ugc_file_tools.fs_naming import sanitize_file_stem
from ugc_file_tools.gia.container import unwrap_gia_container, wrap_gia_container
from ugc_file_tools.gia.varbase_semantics import decoded_field_map_to_numeric_message
from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_field_map, encode_message
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.repo_paths import repo_root

from ugc_file_tools.node_graph_semantics.var_base import map_server_port_type_to_var_type_id as _map_server_port_type_to_var_type_id


@dataclass(frozen=True, slots=True)
class BasicStructPyRecord:
    """代码级基础结构体（*.py）记录（用于 UI 列表与导出）。"""

    struct_id_str: str  # 来自 STRUCT_ID（10 位纯数字字符串）
    struct_name: str  # 来自 STRUCT_PAYLOAD.struct_name/name
    py_path: Path
    scope: str  # "shared" | "project"
    payload: Dict[str, Any]


@dataclass(frozen=True, slots=True)
class ExportBasicStructsGiaPlan:
    """
    将项目存档（共享根 + 项目根）的“基础结构体（*.py）”导出为 `.gia`。

    说明：
    - 输出为 GraphUnit(StructureDefinition) 的 Root 容器（可包含多条结构体定义）。
    - 当前仅导出结构体定义本身（不附带额外引用/节点）。
    """

    project_archive_path: Path | None = None
    output_gia_file_name_in_out: str = "基础结构体.gia"
    # Root.gameVersion：默认会优先从 template_gia 推断；若无法推断则回退到该值。
    game_version: str = "6.3.0"

    selected_struct_ids: Sequence[str] | None = None
    output_user_dir: Path | None = None

    template_gia: Path | None = None

    # `.gia` 里的 struct_id_int 需要落在真源可导入的常见槽位范围，否则可能被忽略。
    # - "auto": 若 STRUCT_ID 已在范围内则保留；否则为本次导出的结构体自动分配新的 1077936xxx id。
    # - "use_struct_id": 直接使用代码级 STRUCT_ID（仅用于调试/对照；不保证真源可导入）。
    struct_id_strategy: str = "auto"

    # 用于 Root.filePath 的 UID（与真源样本一致为整数；默认 0）。
    export_uid: int = 0


_INGAME_STRUCT_ID_MIN = 1077936000
_INGAME_STRUCT_ID_MAX = 1077937000
_BEYOND_LOCAL_EXPORT_DIR = (Path.home() / "AppData" / "LocalLow" / "miHoYo" / "原神" / "BeyondLocal" / "Beyond_Local_Export").resolve()


def _allocate_export_file_guid(*, file_name: str) -> int:
    """
    Root.filePath 中的“文件 GUID”段（样本中常见 1073742011 / 1073742031 ...）：
    - 与 GraphUnit.Id 无关，仅用于导出标记字符串；
    - 这里用 CRC32 做稳定分配，落在 0x40000000 段附近。
    """
    name = str(file_name or "").strip() or "structs.gia"
    crc32 = zlib.crc32(name.encode("utf-8")) & 0xFFFFFFFF
    base = 1073742000
    span = 4096
    return int(base + (crc32 % span))


def _try_extract_export_tag_parts_from_gia(template_gia_path: Path) -> tuple[int, int] | None:
    """
    从模板 `.gia` 的 Root.filePath(field_3) 中提取：
    - uid（第一段）
    - file_guid（第三段）

    真源样本（结构体6个/两个结构体一起等）形如：
      "{uid}-{timestamp}-{file_guid}-\\\\{file_name}.gia"

    说明：
    - timestamp 没必要复用（导出时用当前时间即可）；
    - uid/file_guid 可能被真源校验（尤其是 uid，真源样本不是 0）。
    """
    proto_bytes = unwrap_gia_container(Path(template_gia_path).resolve(), check_header=False)
    root_fields, consumed = decode_message_to_field_map(
        data_bytes=proto_bytes,
        start_offset=0,
        end_offset=len(proto_bytes),
        remaining_depth=8,
    )
    if consumed != len(proto_bytes):
        raise ValueError("protobuf 解析未消费完整字节流（导出 tag 模板 .gia）")
    root_msg = decoded_field_map_to_numeric_message(root_fields)
    tag = root_msg.get("3")
    if not isinstance(tag, str):
        return None
    text = str(tag).strip()
    if text == "":
        return None
    parts = text.split("-", 3)
    if len(parts) < 3:
        return None
    uid_text = parts[0].strip()
    file_guid_text = parts[2].strip()
    if (not uid_text.isdigit()) or (not file_guid_text.isdigit()):
        return None
    uid = int(uid_text)
    file_guid = int(file_guid_text)
    if uid <= 0 or file_guid <= 0:
        return None
    return uid, file_guid


def _try_load_struct_related_ids_from_gia(template_gia_path: Path) -> List[Dict[str, Any]]:
    """
    真源结构体 `.gia` 的 GraphUnit.relatedIds(field_2) 在“单结构体/多结构体”文件里都存在，
    且结构体 GraphUnit 的 relatedIds 与具体 struct_id 无关（通常为 AffiliatedNode=23 的一组固定 ID）。

    为避免手工猜测 ID，直接从模板 `.gia`（默认 `builtin_resources/gia_templates/struct_defs_6.gia`）中提取一份并复用到所有导出结构体上。
    """
    proto_bytes = unwrap_gia_container(Path(template_gia_path).resolve(), check_header=False)
    root_fields, consumed = decode_message_to_field_map(
        data_bytes=proto_bytes,
        start_offset=0,
        end_offset=len(proto_bytes),
        remaining_depth=16,
    )
    if consumed != len(proto_bytes):
        raise ValueError("protobuf 解析未消费完整字节流（结构体 relatedIds 模板 .gia）")
    root_msg = decoded_field_map_to_numeric_message(root_fields)

    graph = root_msg.get("1")
    graph_units: List[Dict[str, Any]] = []
    if isinstance(graph, dict):
        graph_units = [dict(graph)]
    elif isinstance(graph, list):
        graph_units = [dict(u) for u in graph if isinstance(u, dict)]

    for unit in graph_units:
        # Which.StructureDefinition = 29
        if int(unit.get("5") or 0) != 29:
            continue
        related = unit.get("2")
        if isinstance(related, list):
            return [dict(x) for x in related if isinstance(x, dict)]
        if isinstance(related, dict):
            return [dict(related)]
        return []
    return []


def _replace_ints_deep(obj: object, *, old: int, new: int) -> object:
    """
    深度替换 numeric_message（encode_message 输入）中的 int 值：
    - dict/list 递归遍历
    - int 且 value==old -> new

    注意：不要用于替换 GraphUnit.id.id 等“结构性 ID”，这里只用于把“模板结构体 id”替换为“导出结构体 id”。
    """
    if isinstance(obj, int):
        return int(new) if int(obj) == int(old) else int(obj)
    if isinstance(obj, list):
        return [_replace_ints_deep(x, old=int(old), new=int(new)) for x in obj]
    if isinstance(obj, dict):
        return {k: _replace_ints_deep(v, old=int(old), new=int(new)) for k, v in obj.items()}
    return obj


def _load_struct_accessory_groups_from_template_gia(template_gia_path: Path) -> List[Dict[str, Any]]:
    """
    从模板结构体 `.gia` 中抽取“每个结构体对应的 9 个 accessories GraphUnit（which=12）”分组信息。

    真源样本规律（可解码验证）：
    - 每个 StructureDefinition GraphUnit 都有 9 个 relatedIds（AffiliatedNode id）
    - 每个结构体对应 9 个 accessories GraphUnit（id 与 relatedIds 对齐）
    - accessories 内部会嵌入 struct_id（不只是 GraphUnit.relatedIds），必须整体替换，否则真源无法加载

    返回：[{"template_struct_id": int, "related_ids": [...], "accessories": [graph_unit, ...]}, ...]
    - 会过滤掉“relatedIds 组里包含 relatedIds_len!=1 的 accessory”的特殊分组（例如模板中某些 shared 组），
      因为这类组会额外依赖其它 struct_def，容易导致单结构体导出缺依赖而无法加载。
    """
    template_gia_path = Path(template_gia_path).resolve()
    if not template_gia_path.is_file():
        raise FileNotFoundError(str(template_gia_path))

    proto_bytes = unwrap_gia_container(template_gia_path, check_header=False)
    root_fields, consumed = decode_message_to_field_map(
        data_bytes=proto_bytes,
        start_offset=0,
        end_offset=len(proto_bytes),
        remaining_depth=16,
    )
    if consumed != len(proto_bytes):
        raise ValueError("protobuf 解析未消费完整字节流（结构体模板 .gia）")
    root_msg = decoded_field_map_to_numeric_message(root_fields)

    graph_units_raw = root_msg.get("1")
    if isinstance(graph_units_raw, dict):
        graph_units = [graph_units_raw]
    elif isinstance(graph_units_raw, list):
        graph_units = [u for u in graph_units_raw if isinstance(u, dict)]
    else:
        graph_units = []

    accessories_raw = root_msg.get("2")
    accessories: List[Dict[str, Any]] = []
    if isinstance(accessories_raw, list):
        accessories = [u for u in accessories_raw if isinstance(u, dict)]
    elif isinstance(accessories_raw, dict):
        accessories = [accessories_raw]

    accessory_by_id: Dict[int, Dict[str, Any]] = {}
    for u in accessories:
        uid = u.get("1")
        if not isinstance(uid, dict):
            continue
        gid = uid.get("4")
        if isinstance(gid, int):
            accessory_by_id[int(gid)] = u

    groups: List[Dict[str, Any]] = []
    for gu in graph_units:
        if int(gu.get("5") or 0) != 29:
            continue
        gid_msg = gu.get("1")
        if not isinstance(gid_msg, dict):
            continue
        template_struct_id = gid_msg.get("4")
        if not isinstance(template_struct_id, int):
            continue

        # schema: [(index_1based, var_type_int, field_name), ...]
        schema: List[tuple[int, int, str]] = []
        wrapper = gu.get("22")
        if isinstance(wrapper, dict):
            struct_def = wrapper.get("1")
            if isinstance(struct_def, dict):
                generic_field = struct_def.get("1")
                if isinstance(generic_field, dict):
                    vardefs = generic_field.get("3")
                    if isinstance(vardefs, dict):
                        vardefs = [vardefs]
                    if isinstance(vardefs, list):
                        for v in vardefs:
                            if not isinstance(v, dict):
                                continue
                            idx = v.get("503")
                            vt = v.get("502")
                            name = v.get("5")
                            if not isinstance(idx, int) or not isinstance(vt, int) or not isinstance(name, str):
                                continue
                            schema.append((int(idx), int(vt), str(name)))
        schema.sort(key=lambda x: int(x[0]))
        if not schema:
            continue

        related_ids = gu.get("2")
        if not isinstance(related_ids, list) or len(related_ids) != 9:
            continue
        aff_ids: List[int] = []
        related_ids_out: List[Dict[str, Any]] = []
        for rid in related_ids:
            if not isinstance(rid, dict):
                continue
            aff_id = rid.get("4")
            if not isinstance(aff_id, int):
                continue
            aff_ids.append(int(aff_id))
            related_ids_out.append(dict(rid))
        if len(aff_ids) != 9:
            continue

        units: List[Dict[str, Any]] = []
        ok = True
        for aid in aff_ids:
            tpl = accessory_by_id.get(int(aid))
            if not isinstance(tpl, dict):
                ok = False
                break
            # 过滤掉“relatedIds!=1”的特殊组，避免隐式依赖其它 struct_def
            rel = tpl.get("2")
            rel_len = len(rel) if isinstance(rel, list) else (1 if isinstance(rel, dict) else 0)
            if rel_len != 1:
                ok = False
                break
            units.append(tpl)
        if not ok:
            continue

        groups.append(
            {
                "template_struct_id": int(template_struct_id),
                "related_ids": list(related_ids_out),
                "accessories": [dict(u) for u in units],
                "schema": list(schema),
            }
        )

    if not groups:
        raise ValueError(f"模板 .gia 未找到可用的结构体 accessories 分组：{str(template_gia_path)}")
    return groups

def _iter_basic_struct_py_files_in_project(project_archive_path: Path) -> List[Path]:
    directory = Path(project_archive_path) / "管理配置" / "结构体定义" / "基础结构体"
    if not directory.is_dir():
        return []
    files = sorted(
        [
            p
            for p in directory.rglob("*.py")
            if p.is_file()
            and p.suffix.lower() == ".py"
            and p.name != "__init__.py"
            and (not p.name.startswith("_"))
            and p.parent.name != "__pycache__"
        ],
        key=lambda p: p.as_posix().casefold(),
    )
    return files


def _iter_basic_struct_py_files_in_shared_root() -> List[Path]:
    directory = repo_root() / "assets" / "资源库" / "共享" / "管理配置" / "结构体定义" / "基础结构体"
    if not directory.is_dir():
        return []
    files = sorted(
        [
            p
            for p in directory.rglob("*.py")
            if p.is_file()
            and p.suffix.lower() == ".py"
            and p.name != "__init__.py"
            and (not p.name.startswith("_"))
            and p.parent.name != "__pycache__"
        ],
        key=lambda p: p.as_posix().casefold(),
    )
    return files


def _collect_basic_struct_py_files_in_scope(project_archive_path: Path | None) -> List[Path]:
    """
    对齐 Graph_Generater 的基础结构体作用域：
    - 共享根 + 当前项目存档根
    - 同 STRUCT_ID：项目覆盖共享
    """
    shared_files = _iter_basic_struct_py_files_in_shared_root()
    project_files = _iter_basic_struct_py_files_in_project(project_archive_path) if project_archive_path else []

    by_id: Dict[str, Path] = {}
    for p in shared_files:
        env = runpy.run_path(str(p))
        sid = env.get("STRUCT_ID")
        if isinstance(sid, str) and sid.strip():
            by_id[str(sid).strip()] = Path(p)
    for p in project_files:
        env = runpy.run_path(str(p))
        sid = env.get("STRUCT_ID")
        if isinstance(sid, str) and sid.strip():
            by_id[str(sid).strip()] = Path(p)
    return sorted(by_id.values(), key=lambda p: p.as_posix().casefold())


def collect_basic_struct_py_records(*, project_archive_path: Path | None) -> List[BasicStructPyRecord]:
    """收集基础结构体定义（共享根 + 项目根；同 STRUCT_ID 项目覆盖共享）。"""
    shared_files = _iter_basic_struct_py_files_in_shared_root()
    project_files = _iter_basic_struct_py_files_in_project(project_archive_path) if project_archive_path else []

    by_id: Dict[str, BasicStructPyRecord] = {}

    def _load_record(py_path: Path, *, scope: str) -> BasicStructPyRecord | None:
        env = runpy.run_path(str(py_path))
        sid_raw = env.get("STRUCT_ID")
        if sid_raw is None:
            # 允许目录下存在辅助脚本，但必须显式不定义 STRUCT_ID
            return None
        sid = str(sid_raw or "").strip()
        if sid == "":
            raise ValueError(f"STRUCT_ID 为空：{str(py_path)}")
        if not sid.isdigit():
            raise ValueError(f"STRUCT_ID 非法（必须为纯数字字符串）：{str(py_path)} sid={sid!r}")

        payload = env.get("STRUCT_PAYLOAD")
        if not isinstance(payload, dict):
            raise ValueError(f"STRUCT_PAYLOAD 缺失或不是 dict：{str(py_path)}")
        name = str(payload.get("struct_name") or payload.get("name") or "").strip()
        if name == "":
            raise ValueError(f"STRUCT_PAYLOAD.struct_name/name 为空：{str(py_path)}")
        return BasicStructPyRecord(
            struct_id_str=str(sid),
            struct_name=str(name),
            py_path=Path(py_path),
            scope=str(scope),
            payload=dict(payload),
        )

    for p in shared_files:
        record = _load_record(Path(p), scope="shared")
        if record is not None:
            by_id[str(record.struct_id_str)] = record

    for p in project_files:
        record = _load_record(Path(p), scope="project")
        if record is not None:
            by_id[str(record.struct_id_str)] = record

    # 稳定排序：先按 name，再按 id
    return sorted(by_id.values(), key=lambda r: (str(r.struct_name).casefold(), str(r.struct_id_str)))


def _default_template_gia_path() -> Path:
    # 作为 accessories 模板（拼装/拆分/修改结构体）
    return (
        Path(__file__).resolve().parents[1]
        / "builtin_resources"
        / "gia_templates"
        / "struct_defs_6.gia"
    ).resolve()


def _default_template_gia_path_for_structs_count(structs_count: int) -> Path:
    """
    选择“真源可加载”的结构体 `.gia` 作为导出模板（用于：
    - Root.filePath uid/file_guid
    - Root.gameVersion
    - StructureDefinition.relatedIds 以及对应 accessories 分组）

    约定：优先使用 `ugc_file_tools/builtin_resources/gia_templates/` 下的内置模板样本文件。
    """
    assets_dir = (Path(__file__).resolve().parents[1] / "builtin_resources" / "gia_templates").resolve()
    n = int(structs_count)

    if n <= 1:
        # 新版单结构体样本（6.3.0）：优先使用
        p = (assets_dir / "struct_defs_1_modern.gia").resolve()
        if p.is_file():
            return p
        # 旧版单结构体样本
        p2 = (assets_dir / "struct_defs_1_legacy_adventure_level_config.gia").resolve()
        if p2.is_file():
            return p2

    if n == 2:
        p = (assets_dir / "struct_defs_2.gia").resolve()
        if p.is_file():
            return p

    if n == 3:
        p = (assets_dir / "struct_defs_3.gia").resolve()
        if p.is_file():
            return p

    # 默认兜底：6 个结构体模板（包含较多 VarDef/CompositeDef 形态）
    return _default_template_gia_path()


def _try_extract_root_game_version_from_gia(template_gia_path: Path) -> str | None:
    proto_bytes = unwrap_gia_container(Path(template_gia_path).resolve(), check_header=False)
    root_fields, consumed = decode_message_to_field_map(
        data_bytes=proto_bytes,
        start_offset=0,
        end_offset=len(proto_bytes),
        remaining_depth=4,
    )
    if consumed != len(proto_bytes):
        raise ValueError("protobuf 解析未消费完整字节流（提取 gameVersion 模板 .gia）")
    root_msg = decoded_field_map_to_numeric_message(root_fields)
    value = root_msg.get("5")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _build_graph_unit_id(*, class_int: int, type_int: int, id_int: int) -> Dict[str, Any]:
    # GraphUnit.Id: 2 class, 3 type, 4 id
    return {"2": int(class_int), "3": int(type_int), "4": int(id_int)}


def _build_struct_vardef(
    *,
    field_name: str,
    var_type_int: int,
    index_1based: int,
    default_value_obj: object,
    source_id_to_target_struct_id: Mapping[str, int] | None,
) -> Dict[str, Any]:
    """
    StructureDefWrapper.VarDef 的最小可用编码（参考 `struct_defs_6.gia`）。
    - 只保证 type/name/index 可写入并能被解析；复杂类型的 SubType/default 暂保守处理。
    """
    t = int(var_type_int)

    # 结构体引用 id（STRUCT_ID → 导出 id）映射
    sid_map: Dict[str, int] = dict(source_id_to_target_struct_id or {})

    def _normalize_struct_id_ref(value: object) -> int | None:
        # default_value: {"param_type": "结构体", "value": {"structId": "...", ...}}
        if isinstance(value, dict):
            v = value.get("value")
            if isinstance(v, dict):
                sid = str(v.get("structId") or "").strip()
                if sid.isdigit():
                    if sid in sid_map:
                        return int(sid_map[sid])
                    return int(sid)
            sid2 = str(value.get("structId") or "").strip()
            if sid2.isdigit():
                if sid2 in sid_map:
                    return int(sid_map[sid2])
                return int(sid2)
        if isinstance(value, str) and value.strip().isdigit():
            sid3 = str(value).strip()
            if sid3 in sid_map:
                return int(sid_map[sid3])
            return int(sid3)
        return None

    # VarDef.Id: 1 type, 2 subtype
    id_subtype: object = "<binary_data>"
    # VarDef.Content.field_2: message {1:type, 2:subtype}
    content_subtype: object = "<binary_data>"

    # Struct / StructList / Dictionary 需要 subtype message
    if t in {25, 26}:
        ref_struct_id = _normalize_struct_id_ref(default_value_obj)
        if ref_struct_id is None:
            # 没有显式引用时依然需要一个 struct_id（否则真源可能拒绝）
            ref_struct_id = 1077936129
        subtype_msg = {"1": 1, "2": int(ref_struct_id)}  # SubType.xxx=1, xxxx=struct_id
        id_subtype = dict(subtype_msg)
        content_subtype = dict(subtype_msg)
    elif t == 27:
        # Dict subtype: key/value var types + 可选 valueId（当 value 是 struct 时）
        key_type_int = 6
        value_type_int = 6
        value_id_int = 0

        def _normalize_dict_scalar_type_text(text: str) -> str:
            t0 = str(text or "").strip()
            if t0 == "":
                return ""
            # Dict 的 key_type/value_type 常见是英文枚举（String/Int/Bool/...），做一次归一化。
            mapping = {
                "String": "字符串",
                "Str": "字符串",
                "Int": "整数",
                "Integer": "整数",
                "Bool": "布尔值",
                "Boolean": "布尔值",
                "Float": "浮点数",
                "Vector": "三维向量",
                "Vec": "三维向量",
                "GUID": "GUID",
                "Entity": "实体",
                "Faction": "阵营",
                "Configuration": "配置ID",
                "Config": "配置ID",
                "Prefab": "元件ID",
            }
            return mapping.get(t0, t0)

        if isinstance(default_value_obj, dict):
            v = default_value_obj.get("value")
            if isinstance(v, dict):
                kt = str(v.get("key_type") or "").strip()
                vt = str(v.get("value_type") or "").strip()
                if kt:
                    key_type_int = int(_map_server_port_type_to_var_type_id(_normalize_dict_scalar_type_text(kt)))
                if vt:
                    value_type_int = int(_map_server_port_type_to_var_type_id(_normalize_dict_scalar_type_text(vt)))
                if value_type_int in {25, 26}:
                    ref_sid = _normalize_struct_id_ref(v.get("value") or default_value_obj)
                    if ref_sid is not None:
                        value_id_int = int(ref_sid)
        subtype_msg = {"1": 1, "2": 0, "502": int(key_type_int), "503": int(value_type_int), "504": int(value_id_int)}
        id_subtype = dict(subtype_msg)
        content_subtype = dict(subtype_msg)

    # 关键：对齐真源样本（`资产/结构体*.gia`）的 VarDef 编码层级
    # - VarDef.id(field_1): message { field_1=VarType, field_2=subTypeBytesOrMessage }
    # - VarDef.def(field_3): message { field_1=VarType, field_2=message(field_1=VarType, field_2=subTypeBytesOrMessage), field_(10+VarType)=default }
    #
    # 注意：这里 field_3.message.field_2 **只有一层 message**，不能再额外包一层（否则结构会整体错位）。
    id_msg: Dict[str, Any] = {"1": int(t), "2": id_subtype}
    content: Dict[str, Any] = {"1": int(t), "2": {"1": int(t), "2": content_subtype}}

    # Content 默认值字段：field_(10 + VarType)
    value_field_key = str(10 + int(t))

    def _set_empty_bytes_default() -> None:
        content[value_field_key] = "<binary_data>"

    def _set_string_default(text: str) -> None:
        # 样本同时存在：field_16: {"raw_hex": ""} 与 field_16: {"message": {"field_1": {"utf8": ...}}}
        # 在 dump-json 结构里：对齐为 { "1": "xxx" }
        if str(text) == "":
            # 对齐样本：空字符串用空 bytes（避免写出“显式空文本 message”导致真源丢弃/不一致）
            content[value_field_key] = "<binary_data>"
        else:
            content[value_field_key] = {"1": str(text)}

    def _set_int_default(v: int) -> None:
        if int(v) == 0:
            content[value_field_key] = "<binary_data>"
        else:
            content[value_field_key] = {"1": int(v)}

    def _set_bool_default(v: bool) -> None:
        if bool(v) is False:
            content[value_field_key] = "<binary_data>"
        else:
            # 注意：True 不能用 raw_hex=01 直写（真源会拒绝）；用 message.field_1=int(1) 对齐样本。
            content[value_field_key] = {"1": 1}

    # 默认值：按类型写入“最小合法结构”
    if t == 3:
        dv = 0
        if isinstance(default_value_obj, dict):
            raw = default_value_obj.get("value")
            if raw is not None and str(raw).strip().lstrip("-").isdigit():
                dv = int(str(raw).strip())
        _set_int_default(dv)
    elif t == 4:
        dvb = False
        if isinstance(default_value_obj, dict):
            raw = default_value_obj.get("value")
            if isinstance(raw, str):
                dvb = raw.strip().lower() in {"true", "1", "yes"}
            elif isinstance(raw, bool):
                dvb = bool(raw)
        _set_bool_default(dvb)
    elif t == 6:
        text = ""
        if isinstance(default_value_obj, dict):
            raw = default_value_obj.get("value")
            if raw is not None:
                text = str(raw)
        elif default_value_obj is not None:
            text = str(default_value_obj)
        _set_string_default(text)
    elif t in {25, 26}:
        # Struct/StructList 默认值：至少携带 struct_id
        ref_struct_id = _normalize_struct_id_ref(default_value_obj)
        if ref_struct_id is None:
            ref_struct_id = 1077936129
        content[value_field_key] = {"501": int(ref_struct_id)}
    elif t == 27:
        # 空字典：保持空 bytes（避免写错复杂结构导致真源丢弃）
        _set_empty_bytes_default()
    else:
        # 其它类型（包含各种 list/配置ID/向量等）：先写“空/零默认值”
        _set_empty_bytes_default()

    # VarDef: 1 id, 3 def, 5 name, 501 name2, 502 type, 503 index
    name = str(field_name or "").strip()
    if name == "":
        raise ValueError("结构体字段名为空")
    return {
        "1": dict(id_msg),
        "3": dict(content),
        "5": str(name),
        "501": str(name),
        "502": int(t),
        "503": int(index_1based),
    }


def _build_structure_def_message_from_struct_payload(
    *,
    struct_id_int: int,
    struct_index_1based: int,
    struct_name: str,
    struct_payload: Mapping[str, Any],
    source_id_to_target_struct_id: Mapping[str, int] | None,
) -> Dict[str, Any]:
    fields = struct_payload.get("fields")
    if not isinstance(fields, list):
        raise ValueError(f"STRUCT_PAYLOAD.fields 不是 list：struct={struct_name!r}")

    vardefs: List[Dict[str, Any]] = []
    for i, f in enumerate(fields, start=1):
        if not isinstance(f, dict):
            continue
        field_name = str(f.get("field_name") or "").strip()
        param_type = str(f.get("param_type") or "").strip()
        if field_name == "" or param_type == "":
            continue
        var_type_int = int(_map_server_port_type_to_var_type_id(param_type))
        default_value = f.get("default_value")
        vardefs.append(
            _build_struct_vardef(
                field_name=str(field_name),
                var_type_int=int(var_type_int),
                index_1based=int(i),
                default_value_obj=default_value,
                source_id_to_target_struct_id=source_id_to_target_struct_id,
            )
        )

    field_msg: Dict[str, Any] = {
        "1": int(struct_id_int),
        "3": list(vardefs),
        "501": str(struct_name),
        "502": 1,
        "503": int(struct_index_1based),
    }

    # StructureDef: 1 genericField, 2 connectField(same), 3 index, 4 itemCount
    return {
        "1": dict(field_msg),
        "2": dict(field_msg),
        "3": int(struct_index_1based),
        "4": int(len(vardefs)),
    }


def _try_load_accessory_templates_from_gia(template_gia_path: Path) -> Dict[str, Dict[str, Any]]:
    """
    从模板 `.gia` 中提取 accessories 里的三个 GraphUnit（拼装/拆分/修改结构体）作为模板。
    返回：name -> graph_unit_numeric_message
    """
    proto_bytes = unwrap_gia_container(Path(template_gia_path).resolve(), check_header=False)
    root_fields, consumed = decode_message_to_field_map(
        data_bytes=proto_bytes,
        start_offset=0,
        end_offset=len(proto_bytes),
        remaining_depth=16,
    )
    if consumed != len(proto_bytes):
        raise ValueError("protobuf 解析未消费完整字节流（结构体模板 .gia）")
    root_msg = decoded_field_map_to_numeric_message(root_fields)
    accessories = root_msg.get("2")
    if not isinstance(accessories, list):
        return {}

    wanted = {"拼装结构体", "拆分结构体", "修改结构体"}
    out: Dict[str, Dict[str, Any]] = {}
    for unit in accessories:
        if not isinstance(unit, dict):
            continue
        name = str(unit.get("3") or "").strip()
        if name in wanted and name not in out:
            out[name] = dict(unit)
    return out


def _replace_related_struct_ids_in_graph_unit(unit: Dict[str, Any], struct_ids: Sequence[int]) -> Dict[str, Any]:
    """将 GraphUnit.relatedIds(field_2) 替换为结构体 id 列表（Id: class=1, type=15）。"""
    copied = dict(unit)
    copied["2"] = [{"2": 1, "3": 15, "4": int(sid)} for sid in list(struct_ids)]
    return copied


def _allocate_ingame_struct_ids(
    *,
    source_structs: Sequence[Tuple[int, str, Dict[str, Any]]],
    strategy: str,
    used_id_hints: set[int] | None = None,
    prefer_start_from: int | None = None,
) -> List[Tuple[int, int, str, Dict[str, Any]]]:
    """
    返回：[(source_struct_id_int, target_struct_id_int, struct_name, payload), ...]
    """
    mode = str(strategy or "auto").strip().lower()
    if mode not in {"auto", "use_struct_id"}:
        raise ValueError(f"unknown struct_id_strategy: {strategy!r}")

    if mode == "use_struct_id":
        return [(int(sid), int(sid), str(name), dict(payload)) for sid, name, payload in list(source_structs)]

    used: set[int] = set(used_id_hints or set())
    fixed: dict[int, int] = {}
    for source_id, name, payload in list(source_structs):
        _ = name
        _ = payload
        sid = int(source_id)
        if _INGAME_STRUCT_ID_MIN <= sid <= _INGAME_STRUCT_ID_MAX:
            fixed[int(source_id)] = int(sid)
            used.add(int(sid))

    start = int(_INGAME_STRUCT_ID_MIN)
    if prefer_start_from is not None:
        start = max(int(start), int(prefer_start_from))
    next_id = int(start)

    def _alloc_next() -> int:
        nonlocal next_id
        while next_id in used:
            next_id += 1
        if next_id > int(_INGAME_STRUCT_ID_MAX):
            raise ValueError("无法分配新的 struct_id（已超出 1077936000~1077937000 可用范围）")
        value = int(next_id)
        used.add(int(value))
        next_id += 1
        return int(value)

    out: List[Tuple[int, int, str, Dict[str, Any]]] = []
    for source_id, name, payload in list(source_structs):
        src = int(source_id)
        tgt = fixed.get(src)
        if tgt is None:
            tgt = _alloc_next()
        out.append((int(src), int(tgt), str(name), dict(payload)))
    return out


def _collect_struct_slot_ids_from_template_gia(template_gia_path: Path) -> list[int]:
    """
    从模板 `.gia` 的 Root.field_1 中提取单/多 StructureDefinition 的 slot id（GraphUnit.Id.id_int）。
    用于为“新结构体”分配更贴近真源样本的 1077936xxx 槽位（避免从 1077936000 起步造成潜在导入差异）。
    """
    proto_bytes = unwrap_gia_container(Path(template_gia_path).resolve(), check_header=False)
    root_fields, consumed = decode_message_to_field_map(
        data_bytes=proto_bytes,
        start_offset=0,
        end_offset=len(proto_bytes),
        remaining_depth=16,
    )
    if consumed != len(proto_bytes):
        raise ValueError("protobuf 解析未消费完整字节流（结构体 slot 模板 .gia）")
    root_msg = decoded_field_map_to_numeric_message(root_fields)

    graph = root_msg.get("1")
    units: list[dict[str, Any]] = []
    if isinstance(graph, dict):
        units = [dict(graph)]
    elif isinstance(graph, list):
        units = [dict(u) for u in graph if isinstance(u, dict)]

    out: list[int] = []
    for u in units:
        if int(u.get("5") or 0) != 29:
            continue
        gid = u.get("1")
        if not isinstance(gid, dict):
            continue
        sid = gid.get("4")
        if isinstance(sid, int):
            out.append(int(sid))
    return out


def export_basic_structs_to_gia(*, plan: ExportBasicStructsGiaPlan) -> Dict[str, Any]:
    import shutil

    project_archive_path = Path(plan.project_archive_path).resolve() if plan.project_archive_path is not None else None
    if project_archive_path is not None and (not project_archive_path.is_dir()):
        raise FileNotFoundError(str(project_archive_path))

    records = collect_basic_struct_py_records(project_archive_path=project_archive_path)
    if not records:
        raise ValueError("未找到任何基础结构体定义（*.py）")

    selected_ids = plan.selected_struct_ids
    if selected_ids is not None:
        selected_set = {str(s).strip() for s in list(selected_ids) if str(s).strip() != ""}
        if not selected_set:
            raise ValueError("selected_struct_ids 为空（至少需要选择 1 个结构体）")
        records = [r for r in records if str(r.struct_id_str) in selected_set]
        if not records:
            raise ValueError("未匹配到任何选中的结构体（selected_struct_ids）")

    structs_source: List[Tuple[int, str, Dict[str, Any]]] = [
        (int(r.struct_id_str), str(r.struct_name), dict(r.payload)) for r in list(records)
    ]

    # === 选择模板（默认按导出数量选择样本模板）===
    template_gia_path = (
        Path(plan.template_gia).resolve()
        if plan.template_gia is not None
        else _default_template_gia_path_for_structs_count(len(structs_source))
    )
    if not template_gia_path.is_file():
        raise FileNotFoundError(f"结构体导出模板 .gia 不存在：{str(template_gia_path)}")

    # 模板 slot id：用于让“新结构体”的 auto 分配更贴近真源样本（从 max+1 起步，并避开模板已占用槽位）。
    template_struct_slot_ids = _collect_struct_slot_ids_from_template_gia(template_gia_path)
    template_struct_slot_id_set: set[int] = {int(x) for x in template_struct_slot_ids if isinstance(x, int)}
    template_next_start: int | None = (int(max(template_struct_slot_ids)) + 1) if template_struct_slot_ids else None

    # === 分配导出用 struct_id（优先复用模板 slot，避免在 accessories 内漏替换 raw bytes）===
    mode = str(plan.struct_id_strategy or "auto").strip().lower()
    if mode not in {"auto", "use_struct_id"}:
        raise ValueError(f"unknown struct_id_strategy: {plan.struct_id_strategy!r}")

    structs_mapped: List[Tuple[int, int, str, Dict[str, Any]]] = []
    if mode == "use_struct_id":
        structs_mapped = [(sid, sid, name, dict(payload)) for sid, name, payload in list(structs_source)]
    else:
        structs_mapped = _allocate_ingame_struct_ids(
            source_structs=structs_source,
            strategy="auto",
            used_id_hints=set(template_struct_slot_id_set),
            prefer_start_from=template_next_start,
        )

    source_id_to_target_id = {str(src): int(tgt) for (src, tgt, _name, _payload) in list(structs_mapped)}

    units: List[Dict[str, Any]] = []
    accessories_out: List[Dict[str, Any]] = []
    for idx, (_source_struct_id_int, struct_id_int, struct_name, payload) in enumerate(structs_mapped, start=1):
        struct_def = _build_structure_def_message_from_struct_payload(
            struct_id_int=int(struct_id_int),
            struct_index_1based=int(idx),
            struct_name=str(struct_name),
            struct_payload=payload,
            source_id_to_target_struct_id=source_id_to_target_id,
        )

        related_ids_for_this_struct: List[Dict[str, Any]] = []
        unit = {
            "1": _build_graph_unit_id(class_int=1, type_int=15, id_int=int(struct_id_int)),
            "3": str(struct_name),
            "5": 29,  # GraphUnit.Which.StructureDefinition
            "22": {"1": dict(struct_def)},
        }
        if related_ids_for_this_struct:
            unit["2"] = list(related_ids_for_this_struct)
        units.append(unit)

    struct_ids = [int(x[1]) for x in structs_mapped]

    file_name = str(plan.output_gia_file_name_in_out).strip()
    if file_name == "":
        file_name = "基础结构体.gia"
    stem = sanitize_file_stem(Path(file_name).stem)
    output_path = resolve_output_file_path_in_out_dir(Path(f"{stem}.gia"))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = int(time.time())
    uid = int(plan.export_uid)
    file_guid: int | None = None
    if template_gia_path.is_file():
        parts = _try_extract_export_tag_parts_from_gia(template_gia_path)
        if parts is not None:
            template_uid, template_file_guid = parts
            if uid <= 0:
                uid = int(template_uid)
            file_guid = int(template_file_guid)
    if file_guid is None:
        file_guid = _allocate_export_file_guid(file_name=f"{stem}.gia")

    # gameVersion：优先从模板推断（兼容旧默认 6.2.0）
    game_version = str(plan.game_version or "").strip()
    if (game_version == "") or (game_version == "6.2.0"):
        inferred = _try_extract_root_game_version_from_gia(template_gia_path)
        if inferred is not None:
            game_version = str(inferred)
    if game_version == "":
        game_version = "6.3.0"

    root_message: Dict[str, Any] = {
        # 真源差异：单结构体=GraphUnit，多结构体=repeated GraphUnit
        "1": dict(units[0]) if len(units) == 1 else list(units),
        "2": list(accessories_out),
        # 真源样本：分隔符为单个反斜杠（字符串里表现为 "\\")
        "3": f"{int(uid)}-{timestamp}-{int(file_guid)}-\\{stem}.gia",
        "5": str(game_version),
    }
    out_bytes = wrap_gia_container(encode_message(root_message))
    output_path.write_bytes(out_bytes)

    copied_to_user_dir = ""
    copied_file = ""
    # 默认复制到 Beyond_Local_Export（真源导入目录）
    user_dir = Path(plan.output_user_dir).resolve() if plan.output_user_dir is not None else _BEYOND_LOCAL_EXPORT_DIR
    if not user_dir.is_absolute():
        raise ValueError(f"output_user_dir 必须是绝对路径：{str(user_dir)}")
    user_dir.mkdir(parents=True, exist_ok=True)
    copied_path = (user_dir / output_path.name).resolve()
    shutil.copy2(str(output_path), str(copied_path))
    copied_to_user_dir = str(user_dir)
    copied_file = str(copied_path)

    id_map = {int(src): int(tgt) for (src, tgt, _name, _payload) in list(structs_mapped)}
    return {
        "output_gia_file": str(output_path),
        "structs_total": int(len(structs_mapped)),
        "struct_ids": list(struct_ids),  # target ids
        "struct_id_map": dict(id_map),  # source->target
        "accessories_total": int(len(accessories_out)),
        "project_archive_path": str(project_archive_path) if project_archive_path is not None else "",
        "template_gia": str(template_gia_path),
        "copied_to_user_dir": copied_to_user_dir,
        "copied_file": copied_file,
    }

