from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import ugc_file_tools.struct_def_writeback as struct_writer
from ugc_file_tools.gil_dump_codec.gil_container import build_gil_file_bytes_from_payload, read_gil_container_spec
from ugc_file_tools.gil_dump_codec.protobuf_like import (
    encode_message,
    format_binary_data_hex_text,
    parse_binary_data_hex_text,
)
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir

from .basic_py_blob import (
    _build_decoded_blob_from_basic_struct_py,
    _decode_struct_template_to_decoded_field_map,
    _find_basic_template_blob_text,
)
from .node_defs import ensure_struct_node_defs, choose_template_struct_id_for_node_defs
from .paths import collect_basic_struct_py_files_in_scope, iter_struct_decoded_files
from .types import StructImportOptions


def _load_struct_decoded_file(path: Path) -> Tuple[int, str, Dict[str, Any]]:
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("struct decoded file root is not dict")
    struct_id_int = obj.get("struct_id_int")
    struct_name = obj.get("struct_name")
    decoded = obj.get("decoded")
    if not isinstance(struct_id_int, int):
        raise ValueError("struct_id_int missing/invalid")
    if not isinstance(struct_name, str):
        raise ValueError("struct_name missing/invalid")
    if not isinstance(decoded, dict):
        raise ValueError("decoded missing/invalid")
    return int(struct_id_int), str(struct_name), decoded


def _collect_existing_struct_ids(struct_blob_list: Sequence[Any]) -> Dict[int, int]:
    """
    返回 mapping: struct_id -> index_in_struct_blob_list
    """
    mapping: Dict[int, int] = {}
    for index, entry in enumerate(struct_blob_list):
        blob_bytes: bytes | None = None
        if isinstance(entry, str) and entry.startswith("<binary_data>"):
            blob_bytes = parse_binary_data_hex_text(entry)
        elif isinstance(entry, Mapping):
            blob_bytes = encode_message(dict(entry))
        else:
            continue
        struct_id_int = struct_writer._decode_struct_id_from_blob_bytes(blob_bytes)
        mapping[int(struct_id_int)] = int(index)
    return mapping


def import_struct_definitions_from_project_archive_to_gil(
    *,
    project_archive_path: Path,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    options: StructImportOptions,
) -> Dict[str, Any]:
    # 工程化护栏：若存在 genshin-ts 导出的 VarType 报告，则对齐校验本地映射表，避免漂移。
    from ugc_file_tools.struct_type_id_registry import validate_struct_type_id_registry_against_genshin_ts_or_raise

    validate_struct_type_id_registry_against_genshin_ts_or_raise()
    project_path = Path(project_archive_path).resolve()
    input_path = Path(input_gil_file_path).resolve()
    # 统一输出到 out/，调用方只允许传入文件名（basename）。
    # 这样可以彻底避免传入 out/xxx 导致 out/out/... 的路径漂移。
    output_name = Path(str(output_gil_file_path)).name
    output_path = resolve_output_file_path_in_out_dir(Path(output_name))
    if not project_path.is_dir():
        raise FileNotFoundError(str(project_path))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    mode = str(options.mode or "").strip().lower()
    if mode not in {"merge", "overwrite"}:
        raise ValueError(f"unsupported mode: {mode!r}")

    wanted_struct_ids = [str(x or "").strip() for x in list(getattr(options, "include_struct_ids", None) or [])]
    wanted_struct_ids = [x for x in wanted_struct_ids if x]

    decoded_files = iter_struct_decoded_files(project_path)
    basic_struct_py_files: List[Path] = []
    use_py_fallback = False
    if wanted_struct_ids:
        # 显式选择：强制走代码级结构体写回（按 STRUCT_ID 过滤），避免 decoded-json 与选择粒度不一致导致“选了但没生效”。
        decoded_files = []
        basic_struct_py_files = collect_basic_struct_py_files_in_scope(project_path)
        if not basic_struct_py_files:
            raise ValueError("已选择写回结构体（按 STRUCT_ID 过滤），但当前作用域未发现任何基础结构体 .py。")

        import runpy

        by_id: Dict[str, Path] = {}
        for p in basic_struct_py_files:
            env = runpy.run_path(str(p))
            sid = env.get("STRUCT_ID")
            if isinstance(sid, str) and sid.strip():
                by_id[str(sid).strip()] = Path(p)

        missing = sorted(list(set(wanted_struct_ids) - set(by_id.keys())), key=lambda t: t.casefold())
        if missing:
            raise ValueError(f"选择的结构体不存在于当前作用域（共享+项目）：{missing}")
        basic_struct_py_files = [by_id[sid] for sid in wanted_struct_ids]
        use_py_fallback = True
    else:
        if not decoded_files:
            basic_struct_py_files = collect_basic_struct_py_files_in_scope(project_path)
            use_py_fallback = bool(basic_struct_py_files)
    if not decoded_files and not use_py_fallback:
        raise ValueError(
            "项目存档缺少可写回的基础结构体定义：\n"
            f"- decoded-json：{str(project_path / '管理配置/结构体定义/原始解析')}\n"
            f"- code-level：{str(project_path / '管理配置/结构体定义/基础结构体')}\n"
            "请先通过“读取 .gil”生成 decoded-json，或在基础结构体目录下提供 STRUCT_ID/STRUCT_PAYLOAD 的 .py 定义。"
        )

    raw_dump_object = struct_writer._dump_gil_to_raw_json_object(input_path)
    payload_root = raw_dump_object.get("4")
    if not isinstance(payload_root, dict):
        raise ValueError("DLL dump-json 缺少根字段 '4'（期望为 dict）。")

    node_graph_root = struct_writer._ensure_path_dict(payload_root, "10")
    struct_blob_list = struct_writer._ensure_path_list_allow_scalar(node_graph_root, "6")
    if not struct_blob_list:
        # 理论上可以从零构建，但目前依赖模板；直接报错更安全
        raise ValueError("目标 .gil 的 root4/10/6 为空，无法导入结构体（缺少模板）。")

    node_defs = node_graph_root.get("2")
    if not isinstance(node_defs, list):
        raise ValueError("root4/10/2 缺失或不是 list，无法写入结构体节点定义注册。")

    existing_struct_id_to_index = _collect_existing_struct_ids(struct_blob_list)
    template_struct_id = choose_template_struct_id_for_node_defs(
        node_defs=node_defs,
        existing_struct_ids=list(existing_struct_id_to_index.keys()),
    )
    existing_node_type_ids = struct_writer._collect_existing_node_type_ids(node_defs)
    next_node_type_id = (max(existing_node_type_ids) + 1) if existing_node_type_ids else 1610612740

    # 基础结构体（code-level）需要额外的 internal_id 分配与 blob 模板
    existing_internal_ids = struct_writer._collect_existing_struct_internal_ids(struct_blob_list)
    next_internal_id = (max(existing_internal_ids) + 2) if existing_internal_ids else 2
    template_decoded: Dict[str, Any] | None = None
    if use_py_fallback:
        template_blob_text = _find_basic_template_blob_text(struct_blob_list)
        template_decoded = _decode_struct_template_to_decoded_field_map(blob_text=template_blob_text)

    added: List[int] = []
    replaced: List[int] = []
    skipped: List[int] = []

    if decoded_files:
        for decoded_file in decoded_files:
            struct_id_int, struct_name, decoded_blob = _load_struct_decoded_file(decoded_file)
            _ = struct_name
            # decoded-json 是 decode_gil 的输出，可能包含非法的 field_0（通常等价于 bytes `00 00`）。
            # 在重编码前需归一化，否则 encoder 会因 field_number=0 抛错。
            struct_writer._sanitize_decoded_invalid_field0_message_nodes(decoded_blob)
            # 将 decoded -> bytes -> <binary_data>
            dump_json_message = struct_writer._decoded_field_map_to_dump_json_message(decoded_blob)
            blob_bytes = encode_message(dump_json_message)
            blob_text = format_binary_data_hex_text(blob_bytes)

            existing_index = existing_struct_id_to_index.get(int(struct_id_int))
            if existing_index is not None:
                if mode == "merge":
                    skipped.append(int(struct_id_int))
                else:
                    struct_blob_list[int(existing_index)] = blob_text
                    replaced.append(int(struct_id_int))
            else:
                struct_blob_list.append(blob_text)
                existing_struct_id_to_index[int(struct_id_int)] = len(struct_blob_list) - 1
                added.append(int(struct_id_int))

            next_node_type_id = ensure_struct_node_defs(
                node_defs=node_defs,
                struct_id=int(struct_id_int),
                template_struct_id=int(template_struct_id),
                next_node_type_id=int(next_node_type_id),
            )

            struct_writer._ensure_struct_visible_in_tabs(
                payload_root,
                struct_id_int=int(struct_id_int),
                template_struct_id_int=int(template_struct_id),
            )
    else:
        if template_decoded is None:
            raise RuntimeError("internal error: use_py_fallback but template_decoded is None")

        import runpy

        def _decode_struct_name_from_blob_text(blob_text: str) -> str:
            blob_bytes = parse_binary_data_hex_text(blob_text)
            from ugc_file_tools.decode_gil import decode_bytes_to_python

            decoded = decode_bytes_to_python(blob_bytes)
            if not isinstance(decoded, Mapping):
                return ""
            wrapper = decoded.get("field_1")
            if not isinstance(wrapper, Mapping):
                return ""
            msg = wrapper.get("message")
            if not isinstance(msg, Mapping):
                return ""
            name_node = msg.get("field_501")
            return str(struct_writer._get_utf8_from_text_node(name_node) or "").strip()

        # 代码级结构体写回时，不使用项目存档中的 STRUCT_ID（它是 Graph_Generater 资源 ID，不等价于真源可导入的 struct_id）。
        # 策略：优先按 struct_name 复用/覆盖已有 struct_id；若不存在则在真源约束范围内分配新的 struct_id。
        existing_struct_name_to_id_and_index: Dict[str, Tuple[int, int]] = {}
        existing_struct_ids_list: List[int] = []
        for index, entry in enumerate(struct_blob_list):
            blob_text = None
            if isinstance(entry, str) and entry.startswith("<binary_data>"):
                blob_text = entry
            elif isinstance(entry, Mapping):
                blob_text = format_binary_data_hex_text(encode_message(dict(entry)))
            if not blob_text:
                continue
            sid = struct_writer._decode_struct_id_from_blob_bytes(parse_binary_data_hex_text(blob_text))
            existing_struct_ids_list.append(int(sid))
            name = _decode_struct_name_from_blob_text(blob_text)
            if name:
                existing_struct_name_to_id_and_index[str(name)] = (int(sid), int(index))

        reserved_ids = struct_writer._collect_reserved_struct_ids_from_payload_root(payload_root)
        reserved_pool = [int(v) for v in reserved_ids if isinstance(v, int)]

        def _allocate_next_struct_id() -> int:
            used = set(int(v) for v in existing_struct_ids_list if isinstance(v, int))
            for candidate in reserved_pool:
                if int(candidate) not in used:
                    return int(candidate)
            # fallback：从现有最大值往后找，但强制保持在真源常见范围
            sid = int(struct_writer._choose_next_struct_id(existing_struct_ids_list))
            if sid < 1077936000:
                sid = 1077936000
            while sid in used:
                sid += 1
            if sid > 1077937000:
                raise ValueError(f"无法分配新的 struct_id（已超出可用范围）：{sid}")
            return int(sid)

        # ===== 为“字段 entry 原型”选择更完整的模板 =====
        # base（只有两个结构体）不包含 struct_all_supported，无法提供全类型字段原型；
        # 这会导致我们在复杂字段（列表/向量/配置ID 等）的 default/message 结构上走兜底构造，从而真源导入失败。
        #
        # 策略：从工具默认的“结构体字段原型 seed .gil”中挑一个 type_id 覆盖最多的结构体作为“字段原型源”。
        from ugc_file_tools.writeback_defaults import default_struct_template_gil_hint_path

        hint_gil_path = default_struct_template_gil_hint_path()
        if not hint_gil_path.is_file():
            raise FileNotFoundError(
                f"缺少基础结构体字段原型模板：{str(hint_gil_path)}。"
                "请确保 ugc_file_tools/builtin_resources/seeds/struct_def_exemplars.gil 存在。"
            )

        hint_dump_object = struct_writer._dump_gil_to_raw_json_object(hint_gil_path)
        hint_payload_root = hint_dump_object.get("4")
        if not isinstance(hint_payload_root, dict):
            raise ValueError("struct template hint dump-json 缺少根字段 '4'（期望为 dict）。")
        hint_node_graph_root = struct_writer._ensure_path_dict(hint_payload_root, "10")
        hint_struct_blob_list = struct_writer._ensure_path_list_allow_scalar(hint_node_graph_root, "6")
        if not hint_struct_blob_list:
            raise ValueError("struct template hint 的 root4/10/6 为空，无法作为字段原型模板。")

        def _count_type_ids_in_decoded_struct(decoded: Mapping[str, Any]) -> int:
            wrapper = decoded.get("field_1")
            if not isinstance(wrapper, Mapping):
                return 0
            struct_msg = wrapper.get("message")
            if not isinstance(struct_msg, Mapping):
                return 0
            seen: set[int] = set()
            for e2 in struct_writer._iter_field_entries(struct_msg):
                _k, fm = struct_writer._decode_field_entry(e2)
                if not isinstance(fm, Mapping):
                    continue
                t502 = fm.get("field_502")
                if isinstance(t502, Mapping) and isinstance(t502.get("int"), int):
                    seen.add(int(t502["int"]))
            return len(seen)

        best_decoded: Dict[str, Any] | None = None
        best_score = -1
        for entry in hint_struct_blob_list:
            blob_text = None
            if isinstance(entry, str) and entry.startswith("<binary_data>"):
                blob_text = entry
            elif isinstance(entry, Mapping):
                blob_text = format_binary_data_hex_text(encode_message(dict(entry)))
            if not blob_text:
                continue
            decoded = _decode_struct_template_to_decoded_field_map(blob_text=blob_text)
            score = _count_type_ids_in_decoded_struct(decoded)
            if score > best_score:
                best_score = score
                best_decoded = decoded

        if best_decoded is None or best_score <= 0:
            raise ValueError("无法从 struct template hint 中找到可用字段原型结构体（type_id 覆盖为空）。")

        # ===== 预扫描：分配 struct_id，并构建“Graph_Generater STRUCT_ID → 真源 struct_id”映射 =====
        items: List[Tuple[Path, str, Dict[str, Any], str, int]] = []
        # (py_path, source_struct_id_str, payload_raw, struct_name, target_struct_id_int)
        source_id_to_target_struct_id: Dict[str, int] = {}
        for py_path in basic_struct_py_files:
            env = runpy.run_path(str(py_path))
            source_struct_id = str(env.get("STRUCT_ID") or "").strip()
            payload_raw = env.get("STRUCT_PAYLOAD")
            if not isinstance(payload_raw, dict):
                raise ValueError(f"STRUCT_PAYLOAD missing/invalid: {str(py_path)}")

            # 以 payload 内名称为唯一匹配键（对齐局内存档结构体导入器）
            struct_name_text = str(payload_raw.get("struct_name") or payload_raw.get("name") or "").strip()
            if struct_name_text == "":
                raise ValueError(f"STRUCT_PAYLOAD.name/struct_name 为空：{str(py_path)}")

            existing = existing_struct_name_to_id_and_index.get(struct_name_text)
            if existing is not None:
                target_struct_id_int, _existing_index = existing
                if mode == "merge":
                    skipped.append(int(target_struct_id_int))
                    continue
                struct_id_int = int(target_struct_id_int)
                # overwrite：复用已存在的 internal_id（若缺失则分配新的）
            else:
                struct_id_int = _allocate_next_struct_id()
                existing_struct_ids_list.append(int(struct_id_int))

            if source_struct_id == "":
                raise ValueError(f"STRUCT_ID 为空，无法建立结构体引用映射：{str(py_path)}")
            source_id_to_target_struct_id[str(source_struct_id)] = int(struct_id_int)
            items.append((Path(py_path), str(source_struct_id), payload_raw, str(struct_name_text), int(struct_id_int)))

        # 结构体引用 id（ugc_ref_id_int）必须全局唯一
        existing_ref_ids = struct_writer._collect_existing_struct_ref_ids(struct_blob_list)
        next_ref_id = (max(existing_ref_ids) + 1) if existing_ref_ids else 1073742000

        def _allocate_next_struct_ref_id() -> int:
            nonlocal next_ref_id
            value = int(next_ref_id)
            next_ref_id += 1
            return int(value)

        for py_path, _source_id, payload_raw, struct_name_text, struct_id_int in items:
            _ = py_path
            _ = _source_id
            # 分配 internal_id：避免与现有重复（按样本习惯 +2 递增）
            struct_internal_id_int = int(next_internal_id)
            next_internal_id += 2

            decoded_blob = _build_decoded_blob_from_basic_struct_py(
                struct_id_int=int(struct_id_int),
                struct_name=str(struct_name_text),
                struct_payload=payload_raw,
                template_decoded=template_decoded,
                struct_internal_id_int=int(struct_internal_id_int),
                field_prototypes_source_decoded=best_decoded,
                source_id_to_target_struct_id=source_id_to_target_struct_id,
                allocate_next_struct_ref_id=_allocate_next_struct_ref_id,
            )
            struct_writer._sanitize_decoded_invalid_field0_message_nodes(decoded_blob)
            dump_json_message = struct_writer._decoded_field_map_to_dump_json_message(decoded_blob)
            blob_bytes = encode_message(dump_json_message)
            blob_text = format_binary_data_hex_text(blob_bytes)

            existing_index = existing_struct_id_to_index.get(int(struct_id_int))
            if existing_index is not None:
                if mode == "merge":
                    skipped.append(int(struct_id_int))
                    continue
                struct_blob_list[int(existing_index)] = blob_text
                replaced.append(int(struct_id_int))
            else:
                struct_blob_list.append(blob_text)
                existing_struct_id_to_index[int(struct_id_int)] = len(struct_blob_list) - 1
                added.append(int(struct_id_int))

            next_node_type_id = ensure_struct_node_defs(
                node_defs=node_defs,
                struct_id=int(struct_id_int),
                template_struct_id=int(template_struct_id),
                next_node_type_id=int(next_node_type_id),
            )
            # 注意：代码级结构体（.py）写回目前不写回 root4/6/* 页签注册。
            # 原因：页签注册结构在不同真源版本/存档形态下约束更强，写错会直接导致导入失败；
            # 而“仅写回 root4/10/6 + root4/10/2”在局内存档结构体链路中已验证可导入。

    payload_bytes = encode_message(payload_root)
    container_spec = read_gil_container_spec(input_path)
    output_bytes = build_gil_file_bytes_from_payload(payload_bytes=payload_bytes, container_spec=container_spec)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output_bytes)

    return {
        "project_archive": str(project_path),
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "mode": mode,
        "template_struct_id_for_node_defs": int(template_struct_id),
        "decoded_files_count": len(decoded_files),
        "added_struct_ids": sorted(added),
        "replaced_struct_ids": sorted(replaced),
        "skipped_struct_ids": sorted(skipped),
    }

