from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.ui.readable_dump import extract_ui_record_list as _extract_ui_record_list

from ugc_file_tools.gil_dump_codec.protobuf_like import format_binary_data_hex_text, parse_binary_data_hex_text

from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import (
    DEFAULT_CANVAS_SIZE_BY_STATE_INDEX,
    DEFAULT_LIBRARY_ROOT_GUID,
    allocate_next_guid as _allocate_next_guid,
    append_layout_root_guid_to_layout_registry as _append_layout_root_guid_to_layout_registry,
    collect_all_widget_guids as _collect_all_widget_guids,
    decode_varint_stream as _decode_varint_stream,
    dump_gil_to_raw_json_object as _dump_gil_to_raw_json_object,
    find_record_by_guid as _find_record_by_guid,
    get_children_guids_from_parent_record as _get_children_guids_from_parent_record,
    infer_base_layout_guid as _infer_base_layout_guid,
    encode_varint_stream as _encode_varint_stream,
    set_children_guids_to_parent_record as _set_children_guids_to_parent_record,
    set_widget_guid as _set_widget_guid,
    set_widget_name as _set_widget_name,
    set_widget_parent_guid_field504 as _set_widget_parent_guid_field504,
)
from .web_ui_import_bundle import load_ui_control_group_template_json
from .web_ui_import_context import WebUiImportContext
from .web_ui_import_guid_registry import dedup_ui_guid_registry_by_guid, load_ui_guid_registry
from .web_ui_import_layout import should_skip_cloning_base_layout_child
from .web_ui_import_grouping import is_group_container_record_shape

_WEB_UI_IMPORT_SEED_GIL_RELATIVE_PATH: tuple[str, ...] = ("empty_base_samples", "empty_base_with_infra.gil")


def prepare_web_ui_import_context(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    template_json_file_path: Path,
    target_layout_guid: Optional[int],
    new_layout_name: Optional[str],
    base_layout_guid: Optional[int],
    empty_layout: bool,
    clone_children: bool,
    pc_canvas_size: Tuple[float, float],
    mobile_canvas_size: Tuple[float, float],
    ui_guid_registry_file_path: Optional[Path],
) -> Tuple[WebUiImportContext, Dict[str, Any]]:
    input_path = Path(input_gil_file_path).resolve()
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    template_path = Path(template_json_file_path).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))
    if not template_path.is_file():
        raise FileNotFoundError(str(template_path))

    if pc_canvas_size[0] <= 0 or pc_canvas_size[1] <= 0:
        raise ValueError(f"invalid pc_canvas_size: {pc_canvas_size!r}")
    if mobile_canvas_size[0] <= 0 or mobile_canvas_size[1] <= 0:
        raise ValueError(f"invalid mobile_canvas_size: {mobile_canvas_size!r}")

    template_obj = load_ui_control_group_template_json(template_path)
    template_name = str(template_obj.get("template_name") or "").strip()
    template_id = str(template_obj.get("template_id") or "").strip()
    if new_layout_name is None:
        new_layout_name = template_name if template_name != "" else f"web_import_{template_path.stem}"
    new_layout_name = str(new_layout_name or "").strip()
    if new_layout_name == "":
        raise ValueError("new_layout_name 不能为空")

    def _try_parse_canvas_size_key(value: Any) -> Optional[Tuple[float, float]]:
        text = str(value or "").strip().lower()
        if text == "":
            return None
        if "x" not in text:
            return None
        left, right = text.split("x", 1)
        w_text = left.strip()
        h_text = right.strip()
        if not (w_text.isdigit() and h_text.isdigit()):
            return None
        w = float(int(w_text))
        h = float(int(h_text))
        if w <= 0 or h <= 0:
            return None
        return (w, h)

    def _infer_reference_pc_canvas_size_from_widgets(template_obj0: Dict[str, Any]) -> Optional[Tuple[float, float]]:
        widgets0 = template_obj0.get("widgets")
        if not isinstance(widgets0, list) or not widgets0:
            return None
        max_right = 0.0
        max_bottom = 0.0
        has_any = False
        for w in widgets0:
            if not isinstance(w, dict):
                continue
            pos = w.get("position")
            size = w.get("size")
            if (
                isinstance(pos, (list, tuple))
                and len(pos) == 2
                and isinstance(pos[0], (int, float))
                and isinstance(pos[1], (int, float))
                and isinstance(size, (list, tuple))
                and len(size) == 2
                and isinstance(size[0], (int, float))
                and isinstance(size[1], (int, float))
            ):
                left0 = float(pos[0])
                top0 = float(pos[1])
                width0 = float(size[0])
                height0 = float(size[1])
                if width0 <= 0 or height0 <= 0:
                    continue
                # Web 导出：top-left 坐标系
                max_right = max(max_right, left0 + width0)
                max_bottom = max(max_bottom, top0 + height0)
                has_any = True
        if not has_any:
            return None
        # 选择最接近的“常用画布尺寸”（容差 2%），避免极端 bbox 因为阴影外扩略超出。
        candidates: List[Tuple[float, float]] = [
            (1600.0, 900.0),
            (1920.0, 1080.0),
            (1560.0, 720.0),
            (1280.0, 720.0),
        ]
        best: Optional[Tuple[float, float]] = None
        best_score: Optional[float] = None
        for cw, ch in candidates:
            if cw <= 0 or ch <= 0:
                continue
            if max_right > cw * 1.02:
                continue
            if max_bottom > ch * 1.02:
                continue
            # score: area difference (smaller is better)
            score = abs((cw * ch) - (max_right * max_bottom))
            if best is None or best_score is None or score < best_score:
                best = (cw, ch)
                best_score = score
        # 若没有任何候选能容纳 bbox，则回退为 bbox 本身（尽量不误缩放）。
        if best is None:
            bw = max(1.0, float(max_right))
            bh = max(1.0, float(max_bottom))
            return (bw, bh)
        return best

    raw_dump_object = _dump_gil_to_raw_json_object(input_path)
    # -------------------------------------------------------------- 基底兼容：空/极简存档缺失 UI 段
    #
    # 现象：
    # - 部分“空存档/极简存档”没有 root field_9（即 dump['4']['9'] 为 None），因此无法直接提取 UI record_list。
    # - 同类存档也可能缺失 root field_5（实体/自定义变量入口段），导致后续“自动同步自定义变量”失败。
    #
    # 目标：
    # - 允许用户把“空存档”作为基底进行 Web UI 写回：保留其实体/节点图等 payload，
    #   同时从内置样本注入最小 UI 段（layout registry + UI record list），以及可写入的实体变量入口段，
    #   让后续导入/变量同步流程可继续。
    #
    # 约束：
    # - 不做 try/except：结构不符合预期直接抛错（fail-fast）。
    payload_root = raw_dump_object.get("4")
    if not isinstance(payload_root, dict):
        raise ValueError("写回基底 gil payload 缺少根字段 '4'（期望为 dict）。")
    # 兼容：部分 dump/桥接路径可能以 int 键返回 numeric_message；
    # 本模块内部统一按“数值键字符串”处理，避免 `'10' in payload_root` 这类检查误判缺失。
    if any(not isinstance(k, str) for k in payload_root.keys()):
        payload_root = {str(k): v for k, v in dict(payload_root).items()}
        raw_dump_object["4"] = payload_root

    seed_root: Optional[Dict[str, Any]] = None
    bootstrapped_missing_ui_section = False

    def _try_load_min_ui_node9_fixture() -> Optional[Dict[str, Any]]:
        """
        内置最小 UI 段夹具（用于空/极简存档缺失 4/9 时 bootstrap）：
        - 目的：避免运行时读取 seed.gil 的整段 UI（seed 常包含很多演示布局，容易污染用户产物）
        - 内容：仅包含 library_root record + 一个 layout_root 原型 record + 精简 registry
        """
        from ugc_file_tools.repo_paths import ugc_file_tools_builtin_resources_root

        ugc_root = ugc_file_tools_builtin_resources_root()
        fixture_path = (ugc_root / "bootstrap_min_sections" / "min_ui_node9.json").resolve()
        if not fixture_path.is_file():
            return None
        obj = json.loads(fixture_path.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            return None
        node9_obj = obj.get("node9")
        if not isinstance(node9_obj, dict):
            return None
        return dict(node9_obj)

    def _load_seed_root() -> Dict[str, Any]:
        nonlocal seed_root
        if seed_root is not None:
            return seed_root
        from ugc_file_tools.repo_paths import ugc_file_tools_builtin_resources_root

        ugc_root = ugc_file_tools_builtin_resources_root()
        seed_gil_path = (ugc_root / Path(*_WEB_UI_IMPORT_SEED_GIL_RELATIVE_PATH)).resolve()
        if not seed_gil_path.is_file():
            raise FileNotFoundError(str(seed_gil_path))
        # 关键：seed `.gil` 的读取必须是“纯 Python 解码”（numeric_message），不要复用本模块的
        # `_dump_gil_to_raw_json_object`（该函数在测试中会被 monkeypatch，用于模拟 base `.gil` 的 dump 形态）。
        from ugc_file_tools.gil_dump_codec.dump_json_tree import load_gil_payload_as_numeric_message

        seed_root0 = load_gil_payload_as_numeric_message(seed_gil_path, max_depth=64, prefer_raw_hex_for_utf8=False)
        if not isinstance(seed_root0, dict):
            raise TypeError("seed gil payload_root is not dict")
        if any(not isinstance(k, str) for k in seed_root0.keys()):
            seed_root = {str(k): v for k, v in dict(seed_root0).items()}
        else:
            seed_root = seed_root0
        return seed_root

    node9 = payload_root.get("9")
    if node9 is None:
        bootstrapped_missing_ui_section = True
        fixture_node9 = _try_load_min_ui_node9_fixture()
        seed_node9: Optional[Dict[str, Any]] = None
        if fixture_node9 is None:
            seed_node9_obj = _load_seed_root().get("9")
            if not isinstance(seed_node9_obj, dict):
                raise ValueError("seed gil 缺少字段 '4/9'（期望为 dict）。")
            seed_node9 = seed_node9_obj

        # ---------------------------------------------------------- 关键：最小 UI 段注入（避免 seed 污染）
        #
        # 目标：
        # - 让“空存档/极简存档”也具备可写回的 UI 段结构（4/9/501 + 4/9/502）
        # - 但不把 seed 自带的“演示布局/自定义布局_* / GG_CUSTOM_ONLY_GROUPS_*”带进输出产物
        #
        # 做法：
        # - layout registry(4/9/501[0])：只保留两项：
        #   - 一个“布局 root 原型”（优先默认布局 guid=1073741825）
        #   - library_root_guid（末尾固定值 1073741838）
        #   注意：如果 registry 只保留库根，会导致默认布局不在 registry 中（编辑器侧“布局列表形态”与真源不一致），
        #   且更严重的是：库根 record 可能自带 children GUID 列表（来自 seed/夹具），这些 GUID 若与后续新建控件 GUID 撞号，
        #   会让“库根 children”意外指向布局内控件，从而出现“控件看似跑到别的页面/库里”的混乱现象。
        # - ui record list(4/9/502)：只注入两个必要 root record：
        #   - library_root_record（控件组库根）
        #   - 一个“布局 root 原型”（用于 create 新布局时 clone 出 layout root；并强制 empty_layout，不克隆其 children）
        if fixture_node9 is not None:
            node9_copy = copy.deepcopy(fixture_node9)
            fixture_record_list = node9_copy.get("502")
            if isinstance(fixture_record_list, dict):
                fixture_record_list = [fixture_record_list]
                node9_copy["502"] = fixture_record_list
            if not isinstance(fixture_record_list, list):
                raise ValueError("min_ui_node9.json 字段 'node9/502' 结构异常（期望为 list/dict）。")

            fixture_library_root = _find_record_by_guid(fixture_record_list, int(DEFAULT_LIBRARY_ROOT_GUID))
            if fixture_library_root is None:
                raise RuntimeError("min_ui_node9.json 缺少控件组库根 record（1073741838）。")
            # 关键：清空库根 children，避免 seed/夹具携带的“预置 children GUID”与后续分配的 GUID 撞号导致串页/混乱。
            _set_children_guids_to_parent_record(fixture_library_root, [])

            # 选择布局 root 原型 guid：优先默认布局 1073741825；否则选第一个 root record（排除库根）。
            layout_prototype_guid = 1073741825
            if _find_record_by_guid(fixture_record_list, int(layout_prototype_guid)) is None:
                for rec in fixture_record_list:
                    if not isinstance(rec, dict):
                        continue
                    if rec.get("504") is not None:
                        continue
                    gid = rec.get("501")
                    gid_int = int(gid) if isinstance(gid, int) else None
                    if gid_int is None or gid_int <= 0 or gid_int == int(DEFAULT_LIBRARY_ROOT_GUID):
                        continue
                    layout_prototype_guid = int(gid_int)
                    break

            fixture_layout_root = _find_record_by_guid(fixture_record_list, int(layout_prototype_guid))
            if fixture_layout_root is not None:
                _set_children_guids_to_parent_record(fixture_layout_root, [])

            node9_copy["501"] = [
                format_binary_data_hex_text(
                    _encode_varint_stream([int(layout_prototype_guid), int(DEFAULT_LIBRARY_ROOT_GUID)])
                )
            ]
            payload_root["9"] = node9_copy
        else:
            if seed_node9 is None:
                raise RuntimeError("seed_node9 is None（逻辑分支不应到达）。")
            seed_record_list = seed_node9.get("502")
            if isinstance(seed_record_list, dict):
                seed_record_list = [seed_record_list]
            if not isinstance(seed_record_list, list):
                raise ValueError("seed gil 字段 '4/9/502' 结构异常（期望为 list/dict）。")

            seed_library_root = _find_record_by_guid(seed_record_list, int(DEFAULT_LIBRARY_ROOT_GUID))
            if seed_library_root is None:
                raise RuntimeError("seed gil 缺少控件组库根 record（1073741838）。")
            seed_library_root_copy = copy.deepcopy(seed_library_root)
            # 关键：清空库根 children，避免 seed 自带的 children GUID 与后续分配 GUID 撞号导致串页/混乱。
            _set_children_guids_to_parent_record(seed_library_root_copy, [])

            # 选择一个布局 root 原型：优先默认布局 guid=1073741825，否则选 registry 中第一个非库根 guid。
            seed_registry = seed_node9.get("501")
            if isinstance(seed_registry, str):
                seed_registry = [seed_registry]
            first_blob = (
                seed_registry[0]
                if isinstance(seed_registry, list) and seed_registry and isinstance(seed_registry[0], str)
                else ""
            )
            seed_layout_guids: List[int] = []
            if first_blob != "" and first_blob.startswith("<binary_data>"):
                seed_layout_guids = [int(x) for x in _decode_varint_stream(parse_binary_data_hex_text(first_blob))]
            seed_layout_guids = [int(x) for x in seed_layout_guids if int(x) != int(DEFAULT_LIBRARY_ROOT_GUID)]
            layout_prototype_guid = (
                1073741825
                if 1073741825 in seed_layout_guids
                else (seed_layout_guids[0] if seed_layout_guids else 1073741825)
            )
            seed_layout_root = _find_record_by_guid(seed_record_list, int(layout_prototype_guid))
            if seed_layout_root is None:
                # 兜底：随便找一个“无 parent 的 root record”（排除 library_root）
                for rec in seed_record_list:
                    if not isinstance(rec, dict):
                        continue
                    if rec.get("504") is not None:
                        continue
                    gid = rec.get("501")
                    gid_int = int(gid) if isinstance(gid, int) else None
                    if gid_int is None or gid_int <= 0 or gid_int == int(DEFAULT_LIBRARY_ROOT_GUID):
                        continue
                    seed_layout_root = rec
                    break
            if seed_layout_root is None:
                raise RuntimeError("seed gil 中未找到可用的布局 root 原型 record。")

            # 避免 seed layout root 原型携带 children guid 引用（否则后续多 bundle 导出时，
            # 可能被误选为 base_layout 并触发“children guid 找不到 record”的错误）。
            layout_root_copy = copy.deepcopy(seed_layout_root)
            _set_children_guids_to_parent_record(layout_root_copy, [])

            payload_root["9"] = {
                "501": [
                    format_binary_data_hex_text(
                        _encode_varint_stream([int(layout_prototype_guid), int(DEFAULT_LIBRARY_ROOT_GUID)])
                    )
                ],
                "502": [seed_library_root_copy, layout_root_copy],
            }

        # ---------------------------------------------------------- 关键：补齐极空存档缺失的 root4 段
        #
        # 用户提供的“极空 base .gil”（例如 67 bytes）常见只包含 root4 的少数字段（如 1/2/34/39/40/41），
        # 缺失大量“运行时/编辑器期望存在”的段。仅注入 UI 段（4/9）会导致编辑器侧布局表现异常
        # （典型现象：布局切换不生效、页面叠加显示、看起来像串页）。
        #
        # 策略：
        # - 以 seed `.gil`（进度条样式）作为“结构真源”；
        # - 对于 seed_root 中存在但 base_root4 缺失的字段：补齐为 seed 的深拷贝；
        # - 不覆盖 base 已有字段（避免破坏 package/项目元信息）。
        seed_root_full = _load_seed_root()
        for k, v in seed_root_full.items():
            if str(k) == "9":
                continue
            if k not in payload_root:
                payload_root[k] = copy.deepcopy(v)

    node5 = payload_root.get("5")
    if node5 is None:
        seed_node5 = _load_seed_root().get("5")
        if not isinstance(seed_node5, dict):
            raise ValueError("seed gil 缺少字段 '4/5'（期望为 dict）。")
        payload_root["5"] = copy.deepcopy(seed_node5)

    # ---------------------------------------------------------- 关键：补齐极空存档缺失的 root4 段（即便 base 已有 UI 段）
    #
    # 背景：
    # - `empty_base_vacuum.gil` 这类“极空 base”可能已包含 4/9(UI) 段，但仍缺失大量 root4 其它段；
    # - 仅靠“UI 段存在”不足以保证编辑器/写回链路的行为稳定；
    # - 本回归要求：至少补齐 root4 的若干关键段（10/11/12），否则编辑器侧常见表现为“布局切换异常/页面叠加”。
    _REQUIRED_ROOT4_SECTION_KEYS_FOR_WEB_UI: tuple[str, ...] = ("10", "11", "12")
    missing_root4_keys = [k for k in _REQUIRED_ROOT4_SECTION_KEYS_FOR_WEB_UI if k not in payload_root]
    if missing_root4_keys:
        seed_root_full = _load_seed_root()
        for k in list(missing_root4_keys):
            if k not in seed_root_full:
                raise RuntimeError(f"seed gil 缺少 root4 段（无法补齐极空 base）：root4[{k!r}]")
            payload_root[k] = copy.deepcopy(seed_root_full[k])

    ui_record_list = _extract_ui_record_list(raw_dump_object)

    # 若本次是从“缺失 4/9 的空存档”bootstrap 出来的 UI 段，则必须创建空布局（不克隆 children）：
    # - layout prototype 仅用于提供“layout root record 形态”；其 children 可能引用 seed 内的其它 record，
    #   若允许 clone_children 会导致缺 record 报错或无意义膨胀。
    if bootstrapped_missing_ui_section and target_layout_guid is None:
        clone_children = False
        empty_layout = True

    # ------------------------------------------------------------------ 基底兼容：挑选“组容器原型 record”
    # 不同 `.gil` 的组容器 meta/component 形态可能不同（例如 meta_len=2 vs meta_len=4），
    # 若强行使用固定样本形态写回，可能导致编辑器打不开。
    # 因此优先从“布局 root”下的现成组容器中挑一个作为 prototype 来 clone。
    layout_root_guids: set[int] = set()
    payload_root = raw_dump_object.get("4")
    node9 = payload_root.get("9") if isinstance(payload_root, dict) else None
    list501 = node9.get("501") if isinstance(node9, dict) else None
    first: str = ""
    if isinstance(list501, str):
        first = list501
    elif isinstance(list501, list) and list501 and isinstance(list501[0], str):
        first = list501[0]
    if first != "" and first.startswith("<binary_data>"):
        layout_root_guids = {int(x) for x in _decode_varint_stream(parse_binary_data_hex_text(first))}
    layout_root_guids.discard(int(DEFAULT_LIBRARY_ROOT_GUID))

    group_container_prototype_record: Optional[Dict[str, Any]] = None
    # 优先：parent 是布局 root（layout tree 内的组容器）
    for rec in ui_record_list:
        if not isinstance(rec, dict):
            continue
        parent_raw = rec.get("504")
        if not isinstance(parent_raw, int) or int(parent_raw) <= 0:
            continue
        if not is_group_container_record_shape(rec):
            continue
        if int(parent_raw) in layout_root_guids:
            group_container_prototype_record = rec
            break
    # 兜底：任意“有 parent 的组容器”
    if group_container_prototype_record is None:
        for rec in ui_record_list:
            if not isinstance(rec, dict):
                continue
            parent_raw = rec.get("504")
            if not isinstance(parent_raw, int) or int(parent_raw) <= 0:
                continue
            if not is_group_container_record_shape(rec):
                continue
            group_container_prototype_record = rec
            break

    existing_guids = _collect_all_widget_guids(ui_record_list)
    if not existing_guids:
        raise RuntimeError("无法收集现有 GUID（疑似 dump 结构异常）。")

    registry_path: Optional[Path] = Path(ui_guid_registry_file_path).resolve() if ui_guid_registry_file_path is not None else None
    ui_key_to_guid: Dict[str, int] = {}
    registry_loaded = False
    registry_guid_dedup_report: Optional[Dict[str, Any]] = None
    if registry_path is not None:
        ui_key_to_guid = load_ui_guid_registry(registry_path)
        ui_key_to_guid, registry_guid_dedup_report = dedup_ui_guid_registry_by_guid(ui_key_to_guid)
        registry_loaded = True

    layout_guid: int
    created_layout: Optional[Dict[str, Any]] = None

    if target_layout_guid is not None:
        layout_guid = int(target_layout_guid)
        layout_record = _find_record_by_guid(ui_record_list, int(layout_guid))
        if layout_record is None:
            raise RuntimeError(f"未找到 target_layout_guid={int(layout_guid)} 对应的 UI record。")
    else:
        if bool(clone_children) and bool(empty_layout):
            raise ValueError("clone_children=True 时 empty_layout 必须为 False（否则语义冲突）。")
        if not bool(clone_children) and not bool(empty_layout):
            raise ValueError("empty_layout=False 但未启用 clone_children，会导致 child 归属不一致。")

        if base_layout_guid is None:
            base_layout_guid = _infer_base_layout_guid(ui_record_list)
        base_layout_guid = int(base_layout_guid)
        base_record = _find_record_by_guid(ui_record_list, int(base_layout_guid))
        if base_record is None:
            raise RuntimeError(f"未找到 base_layout_guid={int(base_layout_guid)} 对应的 UI record。")

        new_layout_guid = _allocate_next_guid(existing_guids, start=max(existing_guids) + 1)
        existing_guids.add(int(new_layout_guid))
        layout_guid = int(new_layout_guid)

        cloned_layout = copy.deepcopy(base_record)
        _set_widget_guid(cloned_layout, int(layout_guid))
        _set_widget_name(cloned_layout, new_layout_name)
        if "504" in cloned_layout:
            del cloned_layout["504"]

        new_child_records: List[Dict[str, Any]] = []
        if bool(clone_children):
            base_child_guids = _get_children_guids_from_parent_record(base_record)
            if not base_child_guids:
                raise RuntimeError(
                    f"base_layout_guid={int(base_layout_guid)} 的 children 为空，无法克隆固有内容；"
                    "请显式指定一个有 children 的 base_layout_guid，或使用 empty_layout=True 创建空布局。"
                )
            base_child_records: List[Dict[str, Any]] = []
            for child_guid in base_child_guids:
                child_record = _find_record_by_guid(ui_record_list, int(child_guid))
                if child_record is None:
                    raise RuntimeError(f"base_layout 的 children guid={int(child_guid)} 未找到对应 record。")
                skip_reason = should_skip_cloning_base_layout_child(child_record)
                if skip_reason is not None:
                    continue
                base_child_records.append(child_record)

            next_start = int(layout_guid) + 1
            new_child_guids: List[int] = []
            for child_record in base_child_records:
                new_child_guid = _allocate_next_guid(existing_guids, start=next_start)
                existing_guids.add(int(new_child_guid))
                next_start = int(new_child_guid) + 1

                cloned_child = copy.deepcopy(child_record)
                _set_widget_guid(cloned_child, int(new_child_guid))
                _set_widget_parent_guid_field504(cloned_child, int(layout_guid))
                new_child_records.append(cloned_child)
                new_child_guids.append(int(new_child_guid))

            _set_children_guids_to_parent_record(cloned_layout, new_child_guids)
        else:
            _set_children_guids_to_parent_record(cloned_layout, [])

        ui_record_list.append(cloned_layout)
        ui_record_list.extend(new_child_records)
        _append_layout_root_guid_to_layout_registry(raw_dump_object, int(layout_guid))

        created_layout = {
            "guid": int(layout_guid),
            "name": new_layout_name,
            "base_layout_guid": int(base_layout_guid),
            "empty_layout": bool(empty_layout),
            "cloned_children_total": int(len(new_child_records)),
        }

        layout_record = cloned_layout

    # 工程化：layout root 的“布局索引”（切换布局所需的整数）会在 web_ui_import_main 的尾部写入 ui_guid_registry：
    # - `LAYOUT_INDEX__*__*` / `LAYOUT_INDEX__HTML__*` -> <layout_root_guid>

    pc_w, pc_h = float(pc_canvas_size[0]), float(pc_canvas_size[1])
    mobile_w, mobile_h = float(mobile_canvas_size[0]), float(mobile_canvas_size[1])
    canvas_size_by_state_index: Dict[int, Tuple[float, float]] = dict(DEFAULT_CANVAS_SIZE_BY_STATE_INDEX)
    canvas_size_by_state_index[0] = (float(pc_w), float(pc_h))
    canvas_size_by_state_index[1] = (float(mobile_w), float(mobile_h))

    # Web 坐标系“参考画布尺寸”推断（用于把导出坐标缩放到目标 state 的 canvas 尺寸）。
    #
    # 优先级：
    # 1) Workbench bundle meta（template_obj['_bundle'].canvas_size_key）
    # 2) template_obj.canvas_size_key（兼容可能的上游写法）
    # 3) 从 widgets bbox 反推（容错：即便上游没带 key，也能避免“全部飞出屏幕”）
    bundle_meta = template_obj.get("_bundle") if isinstance(template_obj, dict) else None
    meta_key = ""
    if isinstance(bundle_meta, dict):
        meta_key = str(bundle_meta.get("canvas_size_key") or "").strip()
    direct_key = str(template_obj.get("canvas_size_key") or "").strip() if isinstance(template_obj, dict) else ""
    reference_pc_canvas_size = (
        _try_parse_canvas_size_key(meta_key)
        or _try_parse_canvas_size_key(direct_key)
        or _infer_reference_pc_canvas_size_from_widgets(template_obj)
        or (float(pc_w), float(pc_h))
    )
    if reference_pc_canvas_size[0] <= 0 or reference_pc_canvas_size[1] <= 0:
        reference_pc_canvas_size = (float(pc_w), float(pc_h))

    ctx = WebUiImportContext(
        input_path=input_path,
        output_path=output_path,
        template_path=template_path,
        template_obj=template_obj,
        ui_record_list=ui_record_list,
        existing_guids=existing_guids,
        layout_guid=int(layout_guid),
        layout_record=layout_record,
        created_layout=created_layout,
        pc_canvas_size=(float(pc_w), float(pc_h)),
        reference_pc_canvas_size=(float(reference_pc_canvas_size[0]), float(reference_pc_canvas_size[1])),
        mobile_canvas_size=(float(mobile_w), float(mobile_h)),
        canvas_size_by_state_index=canvas_size_by_state_index,
        registry_path=registry_path,
        ui_key_to_guid=ui_key_to_guid,
        registry_loaded=bool(registry_loaded),
        registry_guid_dedup_report=registry_guid_dedup_report,
        registry_saved=False,
        guid_collision_avoided=[],
        reserved_guid_to_ui_key={},
        group_container_prototype_record=group_container_prototype_record,
    )
    return ctx, raw_dump_object

