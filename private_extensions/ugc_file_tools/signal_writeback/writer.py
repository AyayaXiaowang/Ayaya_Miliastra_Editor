from __future__ import annotations

import base64
import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from ugc_file_tools.decode_gil import decode_bytes_to_python
from ugc_file_tools.gil_dump_codec.gil_container import (
    build_gil_file_bytes_from_payload,
    read_gil_container_spec,
    read_gil_payload_bytes,
)
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message
from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import (
    binary_data_text_to_numeric_message,
    numeric_message_to_binary_data_text,
)
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.wire import replace_length_delimited_fields_payload_bytes_in_message_bytes
from ugc_file_tools.writeback_defaults import default_signal_template_gil_path

from . import helpers as h
from .template_cache import load_cached_signal_node_def_templates, save_cached_signal_node_def_templates


def add_signals_to_gil(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    template_gil_file_path: Optional[Path],
    spec_json_path: Path,
    bootstrap_template_gil_file_path: Optional[Path],
    param_build_mode: str,
    emit_reserved_placeholder_signal: bool = True,
) -> Dict[str, Any]:
    mode = str(param_build_mode or "").strip().lower()
    if mode not in ("semantic", "template"):
        raise ValueError(f"unsupported param_build_mode: {param_build_mode!r}")

    base_raw = h._dump_gil_to_raw_json_object(Path(input_gil_file_path))

    base_payload_root = h._get_payload_root(base_raw)

    # --- 选择“信号模板 .gil” ---
    # 说明：
    # - 写回仍然依赖一个“无参数信号”的 node_def 样本作为基底；
    # - 当用户未显式提供 template_gil 时，优先尝试从 base/boot/default 中自动挑一个可用样本，
    #   以减少对外部模板路径的硬依赖。
    resolved_input_gil = Path(input_gil_file_path).resolve()
    resolved_bootstrap_gil = Path(bootstrap_template_gil_file_path).resolve() if bootstrap_template_gil_file_path else None
    default_template_gil = default_signal_template_gil_path()

    template_payload_root: Dict[str, Any] | None
    template_send_def: Dict[str, Any]
    template_listen_def: Dict[str, Any]
    template_server_def: Dict[str, Any]
    template_source_hint: str

    if template_gil_file_path is not None:
        explicit = Path(template_gil_file_path).resolve()
        if not explicit.is_file():
            raise FileNotFoundError(str(explicit))
        template_raw = h._dump_gil_to_raw_json_object(explicit)
        template_payload_root = h._get_payload_root(template_raw)
        base_defs = h._try_choose_base_signal_node_def_templates_from_template_payload(template_payload_root)
        if base_defs is None:
            raise ValueError("template 中未找到“无参数信号”，无法选择基础 node_def 模板")
        template_send_def, template_listen_def, template_server_def = base_defs
        template_source_hint = str(explicit.resolve())
        save_cached_signal_node_def_templates(
            send_def=template_send_def,
            listen_def=template_listen_def,
            send_to_server_def=template_server_def,
            source_hint=template_source_hint,
        )
    else:
        # 自动候选：base → bootstrap → 内置默认模板
        candidates: List[Path] = [resolved_input_gil]
        if resolved_bootstrap_gil is not None:
            candidates.append(resolved_bootstrap_gil)
        if default_template_gil.is_file():
            candidates.append(default_template_gil.resolve())

        template_payload_root = None
        template_send_def = {}
        template_listen_def = {}
        template_server_def = {}
        template_source_hint = ""
        seen: set[str] = set()
        for p in candidates:
            rp = Path(p).resolve()
            rp_key = rp.as_posix()
            if rp_key in seen:
                continue
            seen.add(rp_key)
            if not rp.is_file():
                continue

            candidate_raw = base_raw if rp == resolved_input_gil else h._dump_gil_to_raw_json_object(rp)
            candidate_payload_root = base_payload_root if rp == resolved_input_gil else h._get_payload_root(candidate_raw)

            base_defs = h._try_choose_base_signal_node_def_templates_from_template_payload(candidate_payload_root)
            if base_defs is None:
                continue

            template_payload_root = candidate_payload_root
            template_send_def, template_listen_def, template_server_def = base_defs
            template_source_hint = str(rp.resolve())
            save_cached_signal_node_def_templates(
                send_def=template_send_def,
                listen_def=template_listen_def,
                send_to_server_def=template_server_def,
                source_hint=template_source_hint,
            )
            break

        if template_payload_root is None:
            cached = load_cached_signal_node_def_templates()
            if cached is not None:
                template_payload_root = None
                template_send_def, template_listen_def, template_server_def = cached
                template_source_hint = "<cache>"
            else:
                hint_default = str(default_template_gil.resolve()) if default_template_gil.exists() else "<missing>"
                raise ValueError(
                    "未找到可用的信号模板 .gil（需要包含至少一个“无参数信号”作为 node_def 基底）。\n"
                    f"- base: {str(resolved_input_gil)}\n"
                    f"- bootstrap: {str(resolved_bootstrap_gil) if resolved_bootstrap_gil is not None else '<none>'}\n"
                    f"- default: {hint_default}\n"
                    "请显式提供 template_gil_file_path，或使用包含“无参数信号”的 base/模板存档。"
                )

    bootstrap_section10: Dict[str, Any] | None = None
    if bootstrap_template_gil_file_path is not None:
        bootstrap_raw = h._dump_gil_to_raw_json_object(Path(bootstrap_template_gil_file_path))
        bootstrap_payload_root = h._get_payload_root(bootstrap_raw)
        bootstrap_candidate = bootstrap_payload_root.get("10")
        if not isinstance(bootstrap_candidate, dict):
            raise ValueError("bootstrap template 缺少 root4/10（期望为 dict）。")
        bootstrap_section10 = bootstrap_candidate

    def _default_section10_meta() -> Dict[str, Any]:
        # 对齐编辑器样本（例如“仅仅一个信号.gil”）：root4/10/3
        return {"1": 2, "2": {"1": "复合节点"}}

    # --- 对齐“结构体导入”的 bootstrap 逻辑：只补齐 root4/10 必要结构，不替换整个 payload，也不拷贝模板内已有信号 ---
    base_section10_candidate = base_payload_root.get("10")
    if not isinstance(base_section10_candidate, dict):
        # 对齐编辑器行为：当用户在“完全空存档”里首次创建信号时，会自动生成 root4/10 段。
        # 因此这里允许在缺失 root4/10 时从零初始化（无需 bootstrap）。
        base_section10_candidate = {}
        base_payload_root["10"] = base_section10_candidate

        # 不拷贝 bootstrap/template 内已有的信号表；node_defs 也从空开始，完全由本脚本生成信号相关 node_def。
        base_section10_candidate["2"] = []

        if bootstrap_section10 is not None and isinstance(bootstrap_section10.get("3"), dict):
            base_section10_candidate["3"] = copy.deepcopy(bootstrap_section10.get("3"))
        elif (
            template_payload_root is not None
            and isinstance(template_payload_root.get("10"), dict)
            and isinstance(template_payload_root.get("10", {}).get("3"), dict)
        ):
            base_section10_candidate["3"] = copy.deepcopy(template_payload_root.get("10", {}).get("3"))
        else:
            base_section10_candidate["3"] = _default_section10_meta()

        # 经验：样本中该字段恒为 1（即使没有任何节点图也为 1）
        base_section10_candidate["7"] = 1

        # 10/5：信号系统注册
        # 信号注册段（section10/5）：
        # - 真源/示范存档中通常仅包含：
        #   - "2": node_def meta index（3 个/信号：发送/监听/向服务器发送）
        #   - "3": signal entries
        # - 不要强行写入额外的 flag 字段（例如 "1"），避免与真源 schema 口径不一致导致导入/校验异常。
        base_section10_candidate["5"] = {"2": [], "3": []}
    else:
        # base 已有 root4/10：如 node_defs 缺失/为空，可从 bootstrap 补齐
        if bootstrap_section10 is not None:
            node_defs_candidate = base_section10_candidate.get("2")
            if (not isinstance(node_defs_candidate, list) or not node_defs_candidate) and isinstance(bootstrap_section10.get("2"), list):
                bootstrap_node_defs = bootstrap_section10.get("2") or []
                if isinstance(bootstrap_node_defs, list) and bootstrap_node_defs:
                    base_section10_candidate["2"] = copy.deepcopy(bootstrap_node_defs)
            if "3" not in base_section10_candidate and "3" in bootstrap_section10:
                base_section10_candidate["3"] = copy.deepcopy(bootstrap_section10.get("3"))

        # 对齐编辑器样本：root4/10/3 与 root4/10/7 在“仅创建信号、无节点图”时也存在
        if "3" not in base_section10_candidate:
            if (
                template_payload_root is not None
                and isinstance(template_payload_root.get("10"), dict)
                and isinstance(template_payload_root.get("10", {}).get("3"), dict)
            ):
                base_section10_candidate["3"] = copy.deepcopy(template_payload_root.get("10", {}).get("3"))
            else:
                base_section10_candidate["3"] = _default_section10_meta()
        if not isinstance(base_section10_candidate.get("7"), int):
            base_section10_candidate["7"] = 1

    base_section10 = h._ensure_path_dict(base_payload_root, "10")

    # 读取 spec
    spec_object = json.loads(Path(spec_json_path).read_text(encoding="utf-8"))
    signal_specs = h._parse_signal_specs_from_json(spec_object)
    if not signal_specs:
        raise ValueError("spec has no signals")
    # 对齐真源样本：写回时按 signal_name 做稳定排序，确保 signal_index/node_def_id 分配顺序一致、可复现。
    # 注：信号去重/修复逻辑仍以“原存档已有 entries”为主；这里只约束“新增信号”的写回顺序。
    signal_specs = sorted(
        list(signal_specs),
        key=lambda spec: str(spec.get("signal_name") or spec.get("name") or "").strip(),
    )

    # ===== 从 template 提取基础 node_def；参数口根据模式选择 template 克隆 or semantic 构造 =====
    send_param_item_template_by_type_id: Dict[int, Dict[str, Any]] = {}
    listen_param_port_template_by_type_id: Optional[Dict[int, Dict[str, Any]]] = None
    server_param_item_template_by_type_id: Dict[int, Dict[str, Any]] = {}
    if mode == "template":
        if template_payload_root is None:
            raise ValueError(
                "param_build_mode=template 需要可用的 template payload（用于提取参数端口样本）。"
                "当前模板来源为 cache-only，无法提取参数端口模板。请改用 param_build_mode=semantic 或显式提供 template_gil。"
            )
        (
            send_param_item_template_by_type_id,
            listen_param_port_template_by_type_id,
            server_param_item_template_by_type_id,
        ) = h._collect_param_templates_from_template_payload(template_payload_root)

    # ===== 目标存档当前状态（会在“现有信号自愈清理”后重算）=====
    existing_signal_names: set[str] = set()
    existing_node_def_ids: List[int] = []
    existing_node_def_id_set: set[int] = set()

    next_node_def_id = 0
    next_port_index = 0
    next_signal_index_int: int | None = None

    template_signal_entry_by_name: Dict[str, Dict[str, Any]] = {}
    template_node_defs_by_id: Dict[int, Dict[str, Any]] = {}
    if template_payload_root is not None:
        for _entry in h._extract_signal_entries_from_payload_root(template_payload_root):
            if not isinstance(_entry, dict):
                continue
            _name = str(_entry.get("3") or "").strip()
            if _name == "":
                continue
            if _name not in template_signal_entry_by_name:
                template_signal_entry_by_name[_name] = _entry
        template_node_defs_by_id = h._index_node_defs_by_id(template_payload_root)

    # ===== 需要写入的容器结构 =====
    node_defs_list = h._ensure_path_list(base_section10, "2")

    # 兼容：部分真源/历史产物在 dump-json 阶段会把 `root4/10/5`（信号注册段 message）
    # 误判为 bytes/packed stream，从而被桥接层输出为 "<binary_data> .."（str）。
    # 写回侧需要可写 dict；这里做一次“显式按 message 解码”的纠正，尽量保留原有信号表。
    section5_value = base_section10.get("5")
    if isinstance(section5_value, str):
        text = str(section5_value).strip()
        if text == "":
            base_section10["5"] = {}
        elif text.startswith("<binary_data>"):
            decoded_section5 = binary_data_text_to_numeric_message(text)
            if not isinstance(decoded_section5, dict):
                raise ValueError("root4/10/5 decoded from <binary_data> is not dict")
            base_section10["5"] = dict(decoded_section5)
        else:
            raise ValueError(f"root4/10/5 expected dict or <binary_data>, got str: {text!r}")
    elif isinstance(section5_value, list):
        if len(section5_value) == 1 and isinstance(section5_value[0], dict):
            base_section10["5"] = section5_value[0]
        else:
            raise ValueError(f"root4/10/5 expected dict, got list len={len(section5_value)}")

    section5 = h._ensure_path_dict(base_section10, "5")
    # 对齐真源样本：signals 段不包含 field_1(varint)；若历史工具写入过则移除，避免触发真源侧额外校验分支。
    if "1" in section5:
        section5.pop("1", None)
    node_def_meta_list = h._ensure_path_list(section5, "2")
    signal_entry_list = h._ensure_path_list(section5, "3")

    added_signals: List[Dict[str, Any]] = []
    did_bulk_clone_from_template = False

    def _decode_server_meta_from_entry(entry: Mapping[str, Any]) -> Dict[str, Any] | None:
        raw_server_meta = entry.get("7")
        if isinstance(raw_server_meta, Mapping):
            return dict(raw_server_meta)
        if isinstance(raw_server_meta, str) and raw_server_meta.startswith("<binary_data>"):
            decoded = h.binary_data_text_to_decoded_field_map(raw_server_meta)
            f1 = h._extract_nested_int(decoded, ["field_1", "int"])
            if not isinstance(f1, int):
                f1 = h._extract_nested_int(decoded, ["field_1"])
            f2 = h._extract_nested_int(decoded, ["field_2", "int"])
            if not isinstance(f2, int):
                f2 = h._extract_nested_int(decoded, ["field_2"])
            f3 = h._extract_nested_int(decoded, ["field_3", "int"])
            if not isinstance(f3, int):
                f3 = h._extract_nested_int(decoded, ["field_3"])
            f5 = h._extract_nested_int(decoded, ["field_5", "int"])
            if not isinstance(f5, int):
                f5 = h._extract_nested_int(decoded, ["field_5"])
            if isinstance(f1, int) and isinstance(f2, int) and isinstance(f3, int) and isinstance(f5, int):
                return {"1": int(f1), "2": int(f2), "3": int(f3), "5": int(f5)}
        return None

    def _extract_signal_node_def_ids_from_entry(entry: Mapping[str, Any]) -> tuple[int | None, int | None, int | None]:
        send_id = h._extract_nested_int(entry, ["1", "5"])
        listen_id = h._extract_nested_int(entry, ["2", "5"])
        server_id = h._extract_nested_int(entry, ["7", "5"])
        if not isinstance(server_id, int):
            server_meta_dict = _decode_server_meta_from_entry(entry)
            server_id = int(server_meta_dict["5"]) if isinstance(server_meta_dict, dict) and isinstance(server_meta_dict.get("5"), int) else None
        return (
            int(send_id) if isinstance(send_id, int) else None,
            int(listen_id) if isinstance(listen_id, int) else None,
            int(server_id) if isinstance(server_id, int) else None,
        )

    def _extract_signal_param_definition_texts(entry: Mapping[str, Any]) -> List[str]:
        """
        兼容两种历史形态：
        - 写回链路：`<binary_data>...`（hex 文本）
        - pyugc 解析链路：base64 文本（可能是 4 或 4@data）
        """
        result: List[str] = []
        value = entry.get("4")
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip() != "":
                    result.append(item.strip())
        elif isinstance(value, str) and value.strip() != "":
            result.append(value.strip())

        single = entry.get("4@data")
        if isinstance(single, str) and single.strip() != "":
            result.append(single.strip())

        deduped: List[str] = []
        seen: set[str] = set()
        for text in result:
            key = str(text)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(key)
        return deduped

    def _decode_signal_param_definition_text(binary_text: str) -> Mapping[str, Any] | None:
        text = str(binary_text or "").strip()
        if text == "":
            return None
        if text.startswith("<binary_data>"):
            try:
                decoded = h.binary_data_text_to_decoded_field_map(text)
            except Exception:
                return None
            return decoded if isinstance(decoded, Mapping) else None

        # pyugc 常见的 base64 形态（无 `<binary_data>` 前缀）
        try:
            padding = "=" * ((4 - (len(text) % 4)) % 4)
            raw_bytes = base64.b64decode(text + padding)
            decoded2 = decode_bytes_to_python(raw_bytes)
        except Exception:
            return None
        return decoded2 if isinstance(decoded2, Mapping) else None

    def _signal_entry_has_missing_send_to_server_port_index(entry: Mapping[str, Any]) -> bool:
        for binary_text in _extract_signal_param_definition_texts(entry):
            decoded = _decode_signal_param_definition_text(binary_text)
            if not isinstance(decoded, Mapping):
                return True
            field6 = h._extract_nested_int(decoded, ["field_6", "int"])
            if not isinstance(field6, int):
                field6 = h._extract_nested_int(decoded, ["field_6"])
            if not isinstance(field6, int):
                return True
        return False

    def _is_placeholder_signal_name(name: str) -> bool:
        text = str(name or "").strip()
        if text == "":
            return True
        if not text.startswith("信号_"):
            return False
        suffix = text[len("信号_") :]
        return suffix == "" or suffix[0].isdigit()

    # ===== 现有信号自愈清理：剔除“缺 field_6”的损坏项 + 去重（按 signal_index / signal_name）=====
    requested_signal_name_set: set[str] = set()
    for _spec in signal_specs:
        _name = str(_spec.get("signal_name") or _spec.get("name") or "").strip()
        if _name:
            requested_signal_name_set.add(_name)

    sanitized_existing_signals: List[Dict[str, Any]] = []
    if signal_entry_list:
        signal_candidates: List[Dict[str, Any]] = []
        for original_index, entry in enumerate(list(signal_entry_list)):
            if not isinstance(entry, dict):
                continue
            signal_name = str(entry.get("3") or "").strip()
            signal_index_value = entry.get("6")
            existing_signal_index_int = int(signal_index_value) if isinstance(signal_index_value, int) else None
            send_id, listen_id, server_id = _extract_signal_node_def_ids_from_entry(entry)
            has_missing_field6 = _signal_entry_has_missing_send_to_server_port_index(entry)
            malformed = (
                has_missing_field6
                or not isinstance(existing_signal_index_int, int)
                or not isinstance(send_id, int)
                or not isinstance(listen_id, int)
                or not isinstance(server_id, int)
            )
            signal_candidates.append(
                {
                    "order": int(original_index),
                    "entry": entry,
                    "name": signal_name,
                    "index": existing_signal_index_int,
                    "send_id": send_id,
                    "listen_id": listen_id,
                    "server_id": server_id,
                    "placeholder": _is_placeholder_signal_name(signal_name),
                    "malformed": bool(malformed),
                    "missing_field6": bool(has_missing_field6),
                }
            )

        keep: Dict[int, bool] = {int(i): True for i in range(len(signal_candidates))}

        # 1) 先剔除损坏项（缺 field_6 / 元字段不完整）
        for i, item in enumerate(signal_candidates):
            if bool(item.get("malformed")):
                keep[int(i)] = False
                sanitized_existing_signals.append(
                    {
                        "action": "drop_malformed",
                        "signal_name": str(item.get("name") or ""),
                        "signal_index_int": item.get("index"),
                        "missing_field6": bool(item.get("missing_field6")),
                    }
                )

        # 2) 再按 signal_index 去重：仅在 after_game(0x4000/0x4080) 口径下启用。
        #
        # 重要：你提供的“编辑器侧可用样本”（0x6000/0x6080 段）中，signal_index(field_6) 并非全局唯一：
        # - 例如无参信号 idx=2，单参标量信号也可能为 idx=2。
        # 因此在 0x6000/0x6080 口径下 **禁止** 按 index 去重，否则会误删合法信号 entry。
        scope_mask = 0xFF800000
        known_prefixes = {0x40000000, 0x40800000, 0x60000000, 0x60800000}
        prefixes_in_use: set[int] = set()
        for item in signal_candidates:
            send_id = item.get("send_id")
            if isinstance(send_id, int):
                prefixes_in_use.add(int(send_id) & int(scope_mask))
        prefixes_in_use = {int(p) for p in prefixes_in_use if int(p) in known_prefixes}

        dedupe_by_index_enabled = bool(prefixes_in_use) and all(int(p) in (0x40000000, 0x40800000) for p in prefixes_in_use)
        if dedupe_by_index_enabled:
            by_index: Dict[int, List[int]] = {}
            for i, item in enumerate(signal_candidates):
                if not keep.get(int(i), False):
                    continue
                sig_idx = item.get("index")
                if not isinstance(sig_idx, int):
                    continue
                by_index.setdefault(int(sig_idx), []).append(int(i))

            for sig_idx, ids in by_index.items():
                if len(ids) <= 1:
                    continue

                def _score(candidate_id: int) -> tuple[int, int]:
                    item = signal_candidates[int(candidate_id)]
                    score = 0
                    if str(item.get("name") or "") in requested_signal_name_set:
                        score += 100
                    if not bool(item.get("placeholder")):
                        score += 10
                    if str(item.get("name") or "") != "":
                        score += 1
                    # 次级排序：更早出现者优先
                    return (int(score), -int(item.get("order") or 0))

                keep_id = max(ids, key=_score)
                for drop_id in ids:
                    if int(drop_id) == int(keep_id):
                        continue
                    keep[int(drop_id)] = False
                    item = signal_candidates[int(drop_id)]
                    sanitized_existing_signals.append(
                        {
                            "action": "drop_duplicate_signal_index",
                            "signal_name": str(item.get("name") or ""),
                            "signal_index_int": int(sig_idx),
                        }
                    )

        # 3) 按 signal_name 去重：优先保留“spec 中声明的名字”/非占位
        by_name: Dict[str, List[int]] = {}
        for i, item in enumerate(signal_candidates):
            if not keep.get(int(i), False):
                continue
            signal_name = str(item.get("name") or "")
            if signal_name == "":
                continue
            by_name.setdefault(signal_name, []).append(int(i))

        for signal_name, ids in by_name.items():
            if len(ids) <= 1:
                continue

            def _score_by_name(candidate_id: int) -> tuple[int, int]:
                item = signal_candidates[int(candidate_id)]
                score = 0
                if str(item.get("name") or "") in requested_signal_name_set:
                    score += 100
                if not bool(item.get("placeholder")):
                    score += 10
                return (int(score), -int(item.get("order") or 0))

            keep_id = max(ids, key=_score_by_name)
            for drop_id in ids:
                if int(drop_id) == int(keep_id):
                    continue
                keep[int(drop_id)] = False
                item = signal_candidates[int(drop_id)]
                sanitized_existing_signals.append(
                    {
                        "action": "drop_duplicate_signal_name",
                        "signal_name": str(signal_name),
                        "signal_index_int": item.get("index"),
                    }
                )

        cleaned_entries = [signal_candidates[i]["entry"] for i in range(len(signal_candidates)) if keep.get(int(i), False)]
        if len(cleaned_entries) != len(signal_entry_list):
            signal_entry_list[:] = list(cleaned_entries)

    # ===== 清理后重算状态 =====
    existing_signal_names = {
        str(entry.get("3") or "").strip()
        for entry in h._extract_signal_entries_from_payload_root(base_payload_root)
        if isinstance(entry, Mapping)
    }
    existing_node_def_ids = h._collect_existing_node_def_ids(base_payload_root)
    existing_node_def_id_set = {int(v) for v in existing_node_def_ids if isinstance(v, int)}

    # ===== 信号编号口径（node_def_id / signal_index）=====
    # 说明：不同真源/版本存在多套口径；写回侧必须尽量“跟随 base”。
    # - 编辑器侧常见（你提供的多份可用样本）：信号 node_def_id 位于 0x6000xxxx/0x6080xxxx 段，且 send/listen/server 为三连号。
    # - 也存在另一套口径：0x4000xxxx/0x4080xxxx 段（三连号）。
    #
    # 当 base `.gil` 完全没有任何信号时：默认选择 0x6000/0x6080 这套口径（与编辑器样本一致）。
    signal_scope_mask = 0xFF800000
    known_signal_scope_prefixes = {0x40000000, 0x40800000, 0x60000000, 0x60800000}
    existing_signal_node_def_ids: List[int] = []

    # 说明：
    # - 历史上我们对“base 同时存在多套号段”采取 fail-fast（直接抛错），以避免误写导致运行时不可用；
    # - 但在真实可用存档中已观测到“不同信号 entry 使用不同号段前缀（0x4000 与 0x6000 共存）”的情况；
    # - 因此这里改为：允许跨 entry 混用；但若单条 entry 内部出现多前缀，则仍视为高风险损坏并抛错。
    #
    # 同时，我们需要为“新增信号”选择一套前缀继续分配：优先跟随 base 中占比最高的前缀；若并列则按固定偏好排序。
    scope_prefix_counts_by_entry: Dict[int, int] = {}
    for _entry in h._extract_signal_entries_from_payload_root(base_payload_root):
        if not isinstance(_entry, Mapping):
            continue
        _send_id, _listen_id, _server_id = _extract_signal_node_def_ids_from_entry(_entry)
        entry_prefixes: set[int] = set()
        for _v in (_send_id, _listen_id, _server_id):
            if isinstance(_v, int) and int(_v) > 0:
                v_int = int(_v)
                existing_signal_node_def_ids.append(v_int)
                p = int(v_int) & int(signal_scope_mask)
                if int(p) in known_signal_scope_prefixes:
                    entry_prefixes.add(int(p))
        if len(entry_prefixes) > 1:
            raise ValueError(
                "base `.gil` 的同一条信号 entry 同时引用了多套号段前缀（疑似已损坏/混写）："
                + ", ".join(f"0x{int(x):08X}" for x in sorted(entry_prefixes))
            )
        if len(entry_prefixes) == 1:
            only_prefix = int(next(iter(entry_prefixes)))
            scope_prefix_counts_by_entry[only_prefix] = int(scope_prefix_counts_by_entry.get(only_prefix, 0) + 1)

    scope_prefixes_in_use = {int(p) for p in scope_prefix_counts_by_entry.keys() if int(p) in known_signal_scope_prefixes}
    _prefix_prefer_rank = {
        0x40000000: 3,
        0x40800000: 2,
        0x60000000: 1,
        0x60800000: 0,
    }
    if scope_prefix_counts_by_entry:
        preferred_signal_scope_prefix = int(
            max(
                scope_prefix_counts_by_entry.items(),
                key=lambda kv: (int(kv[1]), int(_prefix_prefer_rank.get(int(kv[0]), -1))),
            )[0]
        )
    else:
        # 当 base `.gil` 完全没有任何信号时：默认选择 0x6000/0x6080 这套口径（与编辑器样本一致）。
        preferred_signal_scope_prefix = 0x60000000

    if not bool(scope_prefix_counts_by_entry):
        signal_scope_prefix_choice_reason = "empty_base_default"
    elif len(scope_prefixes_in_use) <= 1:
        signal_scope_prefix_choice_reason = "follow_base"
    else:
        signal_scope_prefix_choice_reason = "majority_in_base"

    next_node_def_id = h._choose_next_node_def_id(
        existing_node_def_ids,
        preferred_scope_prefix=int(preferred_signal_scope_prefix),
    )
    next_port_index = h._choose_next_port_index(base_payload_root)

    # signal_index：真源可玩样本中更稳定的口径是“业务信号从 8 起递增（8/9/10…）”，并不依赖参数个数。
    #
    # 重要：在 0x6000/0x6080 号段下仍存在一个保留位占位无参信号（常见名：`新建的没有参数的信号`），
    # 其 signal_index 固定为 2（同时占用 node_def_id = prefix+4/+5/+6）。该占位信号不参与递增分配。
    existing_indices = [
        int(v)
        for v in h._collect_existing_signal_indices(base_payload_root)
        if isinstance(v, int) and int(v) >= 0
    ]
    next_signal_index_int = int(max(existing_indices, default=7) + 1)
    if int(next_signal_index_int) < 8:
        next_signal_index_int = 8

    # ===== 编辑器样本兼容：0x6000 段信号表需要“占位无参信号”作为基底 =====
    # 你提供的多份“正确可用”样本中均存在：
    # - signal_name="新建的没有参数的信号"
    # - send/listen/server id = 0x60000004/0x60000005/0x60000006（或 client 前缀 0x6080）
    # 若写回侧在空 base 上直接把第一条业务信号写成 0x60000004 三连号，会产出“看起来对但运行时不可用”的 .gil。
    bootstrap_empty_signal_name = "新建的没有参数的信号"
    should_bootstrap_empty_signal = (
        (not bool(existing_signal_names))
        and int(preferred_signal_scope_prefix) in (0x60000000, 0x60800000)
        and bool(signal_specs)
    )
    reserve_placeholder_slot_without_emitting = False
    if should_bootstrap_empty_signal:
        # 强制占位信号排到第一条，确保其拿到 0x60000004 三连号与第一块端口索引。
        placeholder_spec: Dict[str, Any] = {"signal_name": str(bootstrap_empty_signal_name), "params": []}
        cleaned_specs: List[Dict[str, Any]] = []
        for s in list(signal_specs):
            if not isinstance(s, Mapping):
                continue
            n = str(s.get("signal_name") or s.get("name") or "").strip()
            if n == str(bootstrap_empty_signal_name):
                continue
            cleaned_specs.append(dict(s))
        if bool(emit_reserved_placeholder_signal):
            signal_specs = [placeholder_spec] + cleaned_specs
        else:
            # 用户要求“不写入占位信号”时：不把该信号写入 signal entries / node_defs，
            # 但仍会在后续分配阶段预留掉“占位信号本应占用的 1 组三连号 node_def_id + 1 个端口块”，
            # 确保第一条业务信号不会误占用保留位槽（以及端口块号段保持与旧口径一致）。
            signal_specs = cleaned_specs
            reserve_placeholder_slot_without_emitting = bool(cleaned_specs)

    # ===== 端口索引占用集合（用于“块分配 + 避免碰撞”）=====
    # 说明：
    # - `.gil` 的 signal 参数端口索引可能仅出现在 signal entries 的参数定义里（field_4/5/6），
    #   不一定能从 node_defs 的可读树形结构中稳定抽取（例如 param items 可能是 `<binary_data>`）。
    # - 因此这里同时扫描：
    #   - node_defs 中可见的 port_index candidates
    #   - signal entries 的 param role indices（send/listen/server_send）
    used_ports: set[int] = set()
    base_node_defs_by_id = h._index_node_defs_by_id(base_payload_root)
    for node_def in base_node_defs_by_id.values():
        for p in h._collect_port_index_candidates_from_node_def(node_def):
            if isinstance(p, int):
                used_ports.add(int(p))
    for entry in h._extract_signal_entries_from_payload_root(base_payload_root):
        if not isinstance(entry, Mapping):
            continue
        for binary_text in _extract_signal_param_definition_texts(entry):
            decoded = _decode_signal_param_definition_text(binary_text)
            if not isinstance(decoded, Mapping):
                continue
            for field_name in ("field_4", "field_5", "field_6"):
                v = h._extract_nested_int(decoded, [str(field_name), "int"])
                if not isinstance(v, int):
                    v = h._extract_nested_int(decoded, [str(field_name)])
                if isinstance(v, int) and int(v) >= 0:
                    used_ports.add(int(v))
    if used_ports:
        safe_next = int(max(used_ports)) + 1
        if int(safe_next) > int(next_port_index):
            next_port_index = int(safe_next)

    # 当 base `.gil` 的 section10 内完全没有 node_defs 时，`_choose_next_port_index` 会回退到 1。
    # 这在“空存档作为 base、但用户显式提供了 template_gil（真源/参考存档）”的场景下很容易造成：
    # - 新增信号的 node_def 端口索引从 1 起分配；
    # - 而参考样本/真源通常已有大量 node_defs，信号端口索引落在更高的号段（例如 300+），
    #   最终表现为 NodeGraph 的 META.compositePinIndex 与真源口径不一致，导入/运行仍可能失败。
    #
    # 因此：当 base 没有任何 node_defs，且我们确实有可用的 template_send_def 时，
    # 尝试用模板里“发送信号”的 signal_name_port_index 推断一个更贴近真源的 next_port_index baseline。
    #
    # 约束：
    # - 只在 base 无 node_defs 时生效（避免污染正常存档的增量写回）；并且只会“抬高” next_port_index，不会降低。
    if not bool(base_node_defs_by_id):
        inferred_signal_name_port_index: int | None = None

        # 优先：从 template_payload_root 的“所有信号 send node_def”里取最小的 signal_name_port_index。
        # 这样推断得到的 baseline 更接近“真源 base（尚未写入信号前）”的 next_port_index（通常为 min_port-2）。
        # 例如：模板内已有多条信号时，取 min 能稳定得到“第一条信号”附近的号段，而不是取最后一条导致整体抬高。
        if template_payload_root is not None:
            template_node_defs_by_id_for_ports = h._index_node_defs_by_id(template_payload_root)
            for entry in h._extract_signal_entries_from_payload_root(template_payload_root):
                if not isinstance(entry, Mapping):
                    continue
                send_id = h._extract_nested_int(entry, ["1", "5"])
                if not isinstance(send_id, int):
                    continue
                node_def_obj = template_node_defs_by_id_for_ports.get(int(send_id))
                if not isinstance(node_def_obj, dict):
                    continue
                ports_106 = node_def_obj.get("106")
                ports_list: List[Dict[str, Any]] = []
                if isinstance(ports_106, list):
                    ports_list = [p for p in ports_106 if isinstance(p, dict)]
                elif isinstance(ports_106, dict):
                    ports_list = [ports_106]
                if not ports_list:
                    continue
                port_index_value = ports_list[0].get("8")
                if not isinstance(port_index_value, int):
                    continue
                if int(port_index_value) < 2:
                    continue
                if inferred_signal_name_port_index is None or int(port_index_value) < int(inferred_signal_name_port_index):
                    inferred_signal_name_port_index = int(port_index_value)

        # 次选：用“无参信号模板”的 send_def 推断（更宽松，支持 template_payload_root=None 的 cache-only 场景）。
        if inferred_signal_name_port_index is None:
            ports_106 = template_send_def.get("106")
            ports_list2: List[Dict[str, Any]] = []
            if isinstance(ports_106, list):
                ports_list2 = [p for p in ports_106 if isinstance(p, dict)]
            elif isinstance(ports_106, dict):
                ports_list2 = [ports_106]
            if ports_list2:
                port_index_value2 = ports_list2[0].get("8")
                if isinstance(port_index_value2, int) and int(port_index_value2) >= 2:
                    inferred_signal_name_port_index = int(port_index_value2)

        if inferred_signal_name_port_index is not None:
            inferred_baseline = int(inferred_signal_name_port_index) - 2
            if inferred_baseline > int(next_port_index):
                next_port_index = int(inferred_baseline)
        # 对齐真源常见号段（关键）：当 base `.gil` 里没有 node_defs 时，端口索引的“起点”在不同口径中差异很大。
        #
        # 已观测到的真源/可玩样本（简化表述）：
        # - 0x6000/0x6080（编辑器常见信号号段）：发送信号的 signal_name 端口常落在 44x 段（例如 441），
        #   对应端口块 baseline≈423（send_signal_name=baseline+2）。
        # - 0x4000/0x4080（after_game 常见信号号段）：发送信号的 signal_name 端口常落在 30x 段（例如 302），
        #   对应端口块 baseline≈300。
        #
        # 这里做一个“只抬高不降低”的最小保底，避免空 base 退化到 1/140 号段导致
        # NodeGraph 的 compositePinIndex 口径与真源偏差过大（编辑器可能宽松，但运行时可能更严格）。
        if int(preferred_signal_scope_prefix) in (0x60000000, 0x60800000):
            min_baseline = 423
        elif int(preferred_signal_scope_prefix) in (0x40000000, 0x40800000):
            min_baseline = 300
        else:
            min_baseline = 140

        if int(next_port_index) < int(min_baseline):
            next_port_index = int(min_baseline)

    # 重要（GIL vs GIA 编号差异）：
    # 不要直接克隆 template 中的 signal entries / node_defs（尤其是 signal_index 与 node_def_id）。
    #
    # 背景：
    # - `.gia` 自包含信号 bundle 常见分配：signal_index 从 1 起、node_def_id 从 0x40000031 起；
    # - 可玩真源 `.gil`（after_game 导出）常见分配：signal_index 从 8 起递增、node_def_id 位于 0x4000xxxx/0x4080xxxx 段（三连号）。
    #
    # 若写回侧把 template（或历史产物）里的编号直接整段克隆到 `.gil`，很容易出现：
    # - signal_index 与 base 口径不一致（例如在 after_game 口径中把 1/2/3 写入）
    # - 或 node_def_id 号段不一致（例如 0x4000 vs 0x6000 混写）
    # 最终表现为“编辑器能渲染但运行时分发口径不一致/无法开始游戏”。
    #
    # 因此这里禁用“按 template 同名整段克隆”的优化，仅允许使用 template 作为结构模板（node_def 形状/参数口样本）。
    did_bulk_clone_from_template = False

    # ===== 预留“占位无参信号”的槽位（不写入实际信号 entry）=====
    # 当 base 没有任何信号且选择 0x6000/0x6080 口径时，历史逻辑会先写入一个占位无参信号，
    # 以占用 1 组 node_def_id（三连号）与 1 个端口块（width=16）。当调用方明确要求“不写入占位信号”时，
    # 这里改为“只预留槽位、不写入 entry”，以消除产物噪音同时保持编号/端口号段稳定。
    if bool(reserve_placeholder_slot_without_emitting):
        reserved_send_id = int(next_node_def_id)
        reserved_listen_id = int(next_node_def_id + 1)
        reserved_server_id = int(next_node_def_id + 2)
        existing_node_def_id_set.update({reserved_send_id, reserved_listen_id, reserved_server_id})
        next_node_def_id = int(next_node_def_id + 3)

        reserved_block_width = 16  # 占位无参信号：块宽 16（=16 + 3*0）
        port_block = int(next_port_index)
        while any((port_block + i) in used_ports for i in range(int(reserved_block_width))):
            port_block += int(reserved_block_width)
        for i in range(int(reserved_block_width)):
            used_ports.add(int(port_block + i))
        next_port_index = int(port_block + reserved_block_width)

        # 对齐“仅预留占位槽但不写入占位 entry”的口径：
        # - 业务信号 signal_index 不应从 8 起（会与真源/成功样本口径冲突）。
        # - 已观测的“校验成功”样本中，业务信号会右对齐到 11（最多占用 8~11 四个槽位）：
        #   - 写入 2 条业务信号：10/11
        #   - 写入 3 条业务信号：9/10/11
        #   - 写入 4 条业务信号：8/9/10/11
        #   - 写入 1 条业务信号：11
        if isinstance(next_signal_index_int, int):
            planned_business_signal_count = 0
            for _spec in list(signal_specs):
                if not isinstance(_spec, Mapping):
                    continue
                _name = str(_spec.get("signal_name") or _spec.get("name") or "").strip()
                if _name == "" or _name == str(bootstrap_empty_signal_name):
                    continue
                if _name in existing_signal_names:
                    continue
                planned_business_signal_count += 1

            desired_start = int(next_signal_index_int)
            if int(planned_business_signal_count) > 0:
                desired_start = int(12 - int(planned_business_signal_count))
                if int(desired_start) < 8:
                    desired_start = 8

            if int(next_signal_index_int) < int(desired_start):
                next_signal_index_int = int(desired_start)

    for spec in ([] if did_bulk_clone_from_template else signal_specs):
        signal_name = str(spec.get("signal_name") or spec.get("name") or "").strip()
        if signal_name == "":
            raise ValueError("signal spec missing signal_name")
        if signal_name in existing_signal_names:
            continue

        params_value = spec.get("params") or []
        if not isinstance(params_value, list):
            raise TypeError("signal spec params must be list")

        params: List[Dict[str, Any]] = []
        for item in params_value:
            if not isinstance(item, Mapping):
                continue
            param_name = str(item.get("param_name") or item.get("name") or "").strip()
            if param_name == "":
                raise ValueError(f"param missing name in signal {signal_name!r}")
            type_id = h._parse_type_id(item.get("type_id") if "type_id" in item else item.get("type"))
            param_spec: Dict[str, Any] = {"param_name": str(param_name), "type_id": int(type_id)}
            if "struct_id" in item:
                param_spec["struct_id"] = item.get("struct_id")
            if "dict_key_type" in item:
                param_spec["dict_key_type"] = item.get("dict_key_type")
            if "dict_value_type" in item:
                param_spec["dict_value_type"] = item.get("dict_value_type")
            if "dict_key_type_id" in item:
                param_spec["dict_key_type_id"] = item.get("dict_key_type_id")
            if "dict_value_type_id" in item:
                param_spec["dict_value_type_id"] = item.get("dict_value_type_id")
            params.append(param_spec)

        # 注意：即使 template 中存在同名信号，也不要整段克隆其 signal_index/node_def_id。
        # template 在这里仅用于结构模板与参数口样本（shape/template-mode）。
        template_entry = template_signal_entry_by_name.get(str(signal_name))

        # allocate ids/index（始终按当前 base `.gil` 的现状重新分配；不复用 template 的同名 id/index）
        send_node_def_id: int
        listen_node_def_id: int
        server_node_def_id: int
        signal_index_int: int

        send_node_def_id = int(next_node_def_id)
        listen_node_def_id = int(next_node_def_id + 1)
        server_node_def_id = int(next_node_def_id + 2)
        next_node_def_id += 3
        existing_node_def_id_set.update({send_node_def_id, listen_node_def_id, server_node_def_id})

        # meta objects
        send_meta_dict = h._build_node_def_meta_dict(node_def_id_int=send_node_def_id, scope_code_int=20000)
        listen_meta_dict = h._build_node_def_meta_dict(node_def_id_int=listen_node_def_id, scope_code_int=20000)
        server_meta_dict = h._build_node_def_meta_dict(node_def_id_int=server_node_def_id, scope_code_int=20002)

        send_meta_binary = h._build_node_def_meta_binary_text(node_def_id_int=send_node_def_id, scope_code_int=20000)
        server_meta_binary = h._build_node_def_meta_binary_text(node_def_id_int=server_node_def_id, scope_code_int=20002)

        # allocate port indices by block (对齐 `.gia` 自包含信号 bundle 的“端口块分配”口径)
        #
        # 端口块布局（offset 相对 port_block）：
        # - send:   flow_in=+0, flow_out=+1, signal_name=+2
        # - listen: flow=+3, signal_name=+4, event_src_entity=+5, event_src_guid=+6, signal_src_entity=+7
        # - server: flow_in=+8, flow_out=+9, extra=+10, signal_name=+11
        # - params: 从 +12 起按 3 连号（send/listen/server）
        #
        # 块宽：16 + 3*N（保留 4 个 padding 端口，对齐真源/导入分配习惯，避免后续端口号段漂移）。
        param_count = len(params)
        is_bootstrap_placeholder_signal = (
            signal_name == str(bootstrap_empty_signal_name)
            and int(param_count) == 0
            and int(preferred_signal_scope_prefix) in (0x60000000, 0x60800000)
        )
        if is_bootstrap_placeholder_signal:
            signal_index_int = 2
        else:
            if not isinstance(next_signal_index_int, int):
                raise RuntimeError("next_signal_index_int 未初始化（内部错误）")
            signal_index_int = int(next_signal_index_int)
            next_signal_index_int += 1
        group_param_ports = h._should_group_signal_param_ports(params)
        block_width = 16 + max(int(param_count), 0) * 3

        port_block = int(next_port_index)
        while any((port_block + i) in used_ports for i in range(int(block_width))):
            port_block += int(block_width)
        for i in range(int(block_width)):
            used_ports.add(int(port_block + i))
        next_port_index = int(port_block + block_width)

        send_flow_in = int(port_block + 0)
        send_flow_out = int(port_block + 1)
        send_signal_name_port = int(port_block + 2)

        listen_flow = int(port_block + 3)
        listen_signal_name_port = int(port_block + 4)
        listen_event_source_entity = int(port_block + 5)
        listen_event_source_guid = int(port_block + 6)
        listen_signal_source_entity = int(port_block + 7)

        server_flow_in = int(port_block + 8)
        server_flow_out = int(port_block + 9)
        server_extra_port = int(port_block + 10)
        server_signal_name_port = int(port_block + 11)

        # allocate param port indices
        # - scalar-only params: 按 param 三连交错（send/listen/server）
        # - non-scalar params: 真源样本更常见“按角色分块”（send*N, listen*N, server*N）
        allocated_params: List[Dict[str, Any]] = []
        listen_param_ports: List[Dict[str, Any]] = []
        send_param_port_texts: List[str] = []
        server_param_port_texts: List[str] = []
        signal_param_definition_texts: List[str] = []

        next_param_port = int(port_block + 12)
        for param_ordinal, param in enumerate(params):
            if not isinstance(param, Mapping):
                continue
            param_name = str(param.get("param_name") or "").strip()
            type_id_value = param.get("type_id")
            if param_name == "" or not isinstance(type_id_value, int):
                raise ValueError("param spec requires param_name/type_id")
            type_id = int(type_id_value)

            if bool(group_param_ports):
                send_port = int(next_param_port + int(param_ordinal))
                listen_port = int(next_param_port + int(param_count) + int(param_ordinal))
                server_port = int(next_param_port + 2 * int(param_count) + int(param_ordinal))
            else:
                send_port = int(next_param_port + 3 * int(param_ordinal))
                listen_port = int(send_port + 1)
                server_port = int(send_port + 2)

            if mode == "template":
                template_param_item_decoded = send_param_item_template_by_type_id.get(int(type_id))
                if not isinstance(template_param_item_decoded, dict):
                    raise ValueError(f"缺少发送信号参数端口模板：type_id={type_id}")
                send_param_port_texts.append(
                    h._build_param_item_binary_text_from_template(
                        template_decoded=template_param_item_decoded,
                        param_name=param_name,
                        port_index_int=send_port,
                    )
                )
                template_server_param_item_decoded = server_param_item_template_by_type_id.get(int(type_id))
                if not isinstance(template_server_param_item_decoded, dict):
                    raise ValueError(f"缺少向服务器发送信号参数端口模板：type_id={type_id}")
                server_param_port_texts.append(
                    h._build_param_item_binary_text_from_template(
                        template_decoded=template_server_param_item_decoded,
                        param_name=param_name,
                        port_index_int=server_port,
                    )
                )
            else:
                send_param_port_texts.append(
                    h._build_param_item_binary_text_from_param_spec(
                        param_spec=param,
                        port_index_int=send_port,
                        param_ordinal=int(param_ordinal),
                    )
                )
                server_param_port_texts.append(
                    h._build_param_item_binary_text_from_param_spec(
                        param_spec=param,
                        port_index_int=server_port,
                        param_ordinal=int(param_ordinal),
                        for_server_node=True,
                    )
                )

            listen_param_ports.append(
                {
                    **dict(param),
                    "param_name": str(param_name),
                    "type_id": int(type_id),
                    "port_index": int(listen_port),
                }
            )
            signal_param_definition_texts.append(
                h._build_signal_param_definition_binary_text(
                    param_name=param_name,
                    type_id_int=int(type_id),
                    send_port_index=send_port,
                    listen_port_index=listen_port,
                    send_to_server_port_index=server_port,
                )
            )
            allocated_params.append(
                {
                    "param_name": param_name,
                    "type_id": int(type_id),
                    "port_index_by_role": {
                        "send": send_port,
                        "listen": listen_port,
                        "send_to_server": server_port,
                    },
                }
            )

        # build node defs
        new_send_def = h._reset_send_node_def_for_new_signal(
            template_send_def=template_send_def,
            signal_index_int=signal_index_int,
            node_def_id_int=send_node_def_id,
            signal_name=signal_name,
            listen_meta_dict=listen_meta_dict,
            server_meta_binary_text=server_meta_binary,
            flow_in_port_index=send_flow_in,
            flow_out_port_index=send_flow_out,
            signal_name_port_index=send_signal_name_port,
            send_param_port_texts=send_param_port_texts,
        )
        new_listen_def = h._reset_listen_node_def_for_new_signal(
            template_listen_def=template_listen_def,
            listen_param_port_template_by_type_id=listen_param_port_template_by_type_id,
            signal_index_int=signal_index_int,
            node_def_id_int=listen_node_def_id,
            signal_name=signal_name,
            send_meta_binary_text=send_meta_binary,
            server_meta_binary_text=server_meta_binary,
            flow_port_index=listen_flow,
            signal_name_port_index=listen_signal_name_port,
            fixed_output_port_indices=(
                listen_event_source_entity,
                listen_event_source_guid,
                listen_signal_source_entity,
            ),
            params=listen_param_ports,
        )
        new_server_def = h._reset_send_to_server_node_def_for_new_signal(
            template_server_def=template_server_def,
            signal_index_int=signal_index_int,
            node_def_id_int=server_node_def_id,
            signal_name=signal_name,
            listen_meta_dict=listen_meta_dict,
            send_meta_binary_text=send_meta_binary,
            flow_in_port_index=server_flow_in,
            flow_out_port_index=server_flow_out,
            extra_port_index=server_extra_port,
            signal_name_port_index=server_signal_name_port,
            server_param_port_texts=server_param_port_texts,
        )

        # append node defs
        node_defs_list.append({"1": new_send_def})
        node_defs_list.append({"1": new_listen_def})
        node_defs_list.append({"1": new_server_def})

        # append meta index
        node_def_meta_list.append(dict(send_meta_dict))
        node_def_meta_list.append(dict(listen_meta_dict))
        node_def_meta_list.append(dict(server_meta_dict))

        # append signal entry
        new_signal_entry: Dict[str, Any] = {
            "1": dict(send_meta_dict),
            "2": dict(listen_meta_dict),
            "3": str(signal_name),
            "6": int(signal_index_int),
            "7": numeric_message_to_binary_data_text(server_meta_dict),
        }
        if signal_param_definition_texts:
            new_signal_entry["4"] = list(signal_param_definition_texts)
        signal_entry_list.append(new_signal_entry)

        existing_signal_names.add(signal_name)
        added_signals.append(
            {
                "signal_name": signal_name,
                "signal_index_int": signal_index_int,
                "node_def_ids": {
                    "send": send_node_def_id,
                    "listen": listen_node_def_id,
                    "send_to_server": server_node_def_id,
                },
                "params": allocated_params,
            }
        )

    # ===== 写盘：wire-level 仅替换必要段（field10=NodeGraphs/Signals），避免整份 payload 重编码漂移 =====
    section10_obj = base_payload_root.get("10")
    if not isinstance(section10_obj, dict):
        raise ValueError("payload_root['10'] must be dict after signal writeback")

    base_payload_bytes = read_gil_payload_bytes(Path(input_gil_file_path))
    patched_payload_bytes = replace_length_delimited_fields_payload_bytes_in_message_bytes(
        message_bytes=base_payload_bytes,
        payload_bytes_by_field_number={10: encode_message(dict(section10_obj))},
    )
    container_spec = read_gil_container_spec(Path(input_gil_file_path))
    output_bytes = build_gil_file_bytes_from_payload(payload_bytes=patched_payload_bytes, container_spec=container_spec)
    # 约定：
    # - 若 output 仅为文件名（basename），则强制输出到 ugc_file_tools/out/（避免污染样本目录）
    # - 若 output 显式带目录（相对/绝对均可），则尊重调用方路径（便于 tests/tmp_path 等场景隔离落盘）
    raw_output_path = Path(output_gil_file_path)
    output_path = (
        resolve_output_file_path_in_out_dir(raw_output_path)
        if (not raw_output_path.is_absolute() and raw_output_path.parent == Path("."))
        else raw_output_path.resolve()
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output_bytes)

    return {
        "input_gil": str(Path(input_gil_file_path).resolve()),
        "bootstrap_template_gil": str(Path(bootstrap_template_gil_file_path).resolve())
        if bootstrap_template_gil_file_path is not None
        else "",
        "template_gil": str(template_source_hint),
        "param_build_mode": str(mode),
        "emit_reserved_placeholder_signal": bool(emit_reserved_placeholder_signal),
        "signal_scope_prefix_choice_reason": str(signal_scope_prefix_choice_reason),
        "signal_scope_prefixes_in_use_hex": [f"0x{int(x):08X}" for x in sorted(scope_prefixes_in_use)],
        "signal_scope_prefix_counts_by_entry_hex": {
            f"0x{int(k):08X}": int(v)
            for k, v in sorted(scope_prefix_counts_by_entry.items(), key=lambda kv: int(kv[0]))
        },
        "preferred_signal_scope_prefix_int": int(preferred_signal_scope_prefix),
        "preferred_signal_scope_prefix_hex": f"0x{int(preferred_signal_scope_prefix):08X}",
        "spec_json": str(Path(spec_json_path).resolve()),
        "output_gil": str(output_path),
        "added_signals": added_signals,
        "sanitized_existing_signals": list(sanitized_existing_signals),
    }



