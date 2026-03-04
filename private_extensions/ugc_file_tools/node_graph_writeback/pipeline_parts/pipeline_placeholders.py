from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ugc_file_tools.node_graph_semantics.var_base import (
    set_component_id_registry,
    set_entity_id_registry,
    set_ui_key_guid_registry,
)


@dataclass(frozen=True)
class _WritebackRequiredPlaceholders:
    required_ui_keys: set[str]
    required_component_names: set[str]
    required_entity_names: set[str]
    layout_name_hint: Optional[str]


def _load_graph_model_json_object(*, graph_model_json_path: Path) -> Dict[str, Any]:
    graph_json_object = json.loads(Path(graph_model_json_path).read_text(encoding="utf-8"))
    if not isinstance(graph_json_object, dict):
        raise TypeError("graph_model_json must be dict")
    return graph_json_object


def _collect_required_placeholders_from_graph_json_object(
    *,
    graph_json_object: Dict[str, Any],
) -> _WritebackRequiredPlaceholders:
    from ugc_file_tools.component_id_registry import collect_component_key_placeholders_from_graph_json_object
    from ugc_file_tools.entity_id_registry import collect_entity_key_placeholders_from_graph_json_object
    from ugc_file_tools.ui.guid_registry import collect_ui_key_placeholders_from_graph_json_object

    from .pipeline_ui_keys import _infer_layout_name_hint_from_graph_json_object

    required_ui_keys = collect_ui_key_placeholders_from_graph_json_object(graph_json_object=graph_json_object)
    required_component_names = collect_component_key_placeholders_from_graph_json_object(graph_json_object=graph_json_object)
    required_entity_names = collect_entity_key_placeholders_from_graph_json_object(graph_json_object=graph_json_object)
    layout_name_hint = _infer_layout_name_hint_from_graph_json_object(graph_json_object)

    return _WritebackRequiredPlaceholders(
        required_ui_keys=set(required_ui_keys),
        required_component_names=set(required_component_names),
        required_entity_names=set(required_entity_names),
        layout_name_hint=(str(layout_name_hint).strip() if layout_name_hint else None),
    )


def _resolve_component_id_registry_for_writeback(
    *,
    graph_model_json_path: Path,
    preloaded_component_name_to_id: Dict[str, int] | None,
) -> Tuple[Optional[Dict[str, int]], Optional[Path]]:
    if isinstance(preloaded_component_name_to_id, dict) and preloaded_component_name_to_id:
        return dict(preloaded_component_name_to_id), None

    from ugc_file_tools.component_id_registry import try_load_component_id_registry_for_graph_model_json_path

    loaded = try_load_component_id_registry_for_graph_model_json_path(Path(graph_model_json_path))
    if loaded is None:
        return None, None
    component_name_to_id, component_registry_path = loaded
    return dict(component_name_to_id), (Path(component_registry_path) if component_registry_path is not None else None)


def _require_component_registry_coverage_or_raise(
    *,
    graph_model_json_path: Path,
    required_component_names: set[str],
    component_name_to_id: Optional[Dict[str, int]],
    component_registry_path: Optional[Path],
) -> None:
    if not required_component_names:
        return
    if component_name_to_id is None:
        raise ValueError(
            "检测到节点图使用了 component_key: 占位符，但未提供“参考 `.gil`”且未找到 component_id_registry.json。\n"
            f"- graph_model: {str(Path(graph_model_json_path).resolve())}\n"
            "- 解决方案：在导出中心选择“占位符参考 GIL”（推荐），或先运行 sync_component_id_registry_from_gil 生成运行时缓存 registry。"
        )
    missing = sorted({str(x) for x in required_component_names if str(x) not in set(component_name_to_id.keys())})
    if missing:
        raise ValueError(
            "检测到节点图使用了 component_key: 占位符，但注册表缺少部分元件名，无法稳定写回。\n"
            + f"- registry: {str(component_registry_path) if component_registry_path is not None else '<unknown>'}\n"
            + f"- 缺失元件名：{missing}"
        )


def _classify_component_key_placeholder_policy_for_writeback(
    *,
    required_component_names: set[str],
    component_name_to_id: Optional[Dict[str, int]],
) -> Tuple[bool, list[str]]:
    """
    缺失策略（与 `.gia` 导出侧一致）：找不到也不阻断写回，缺失占位符回填为 0。

    返回：
    - allow_unresolved_component_keys: bool
    - missing_component_names: list[str]
    """
    if not required_component_names:
        return False, []
    if component_name_to_id is None:
        missing = sorted({str(x) for x in required_component_names if str(x).strip() != ""}, key=lambda t: t.casefold())
        return True, list(missing)
    missing2 = sorted(
        {str(x) for x in required_component_names if str(x) not in set(component_name_to_id.keys()) and str(x).strip() != ""},
        key=lambda t: t.casefold(),
    )
    return bool(missing2), list(missing2)


def _resolve_entity_id_registry_for_writeback(
    *,
    preloaded_entity_name_to_guid: Dict[str, int] | None,
) -> Optional[Dict[str, int]]:
    if isinstance(preloaded_entity_name_to_guid, dict) and preloaded_entity_name_to_guid:
        return dict(preloaded_entity_name_to_guid)
    return None


def _require_entity_registry_coverage_or_raise(
    *,
    graph_model_json_path: Path,
    required_entity_names: set[str],
    entity_name_to_guid: Optional[Dict[str, int]],
) -> None:
    if not required_entity_names:
        return
    if entity_name_to_guid is None:
        raise ValueError(
            "检测到节点图使用了 entity_key: 占位符，但未提供“参考 `.gil`”，无法回填实体 GUID。\n"
            f"- graph_model: {str(Path(graph_model_json_path).resolve())}\n"
            "- 解决方案：在导出中心选择“占位符参考 GIL”（推荐），工具会从参考存档抽取 实体名→GUID 映射并用于本次写回。"
        )
    missing = sorted({str(x) for x in required_entity_names if str(x) not in set(entity_name_to_guid.keys())})
    if missing:
        raise ValueError(
            "检测到节点图使用了 entity_key: 占位符，但注册表缺少部分实体名，无法稳定写回。\n"
            + "- registry: <reference_gil>\n"
            + f"- 缺失实体名：{missing}"
        )


def _classify_entity_key_placeholder_policy_for_writeback(
    *,
    required_entity_names: set[str],
    entity_name_to_guid: Optional[Dict[str, int]],
) -> Tuple[bool, list[str]]:
    """
    缺失策略（与 `.gia` 导出侧一致）：找不到也不阻断写回，缺失占位符回填为 0。

    返回：
    - allow_unresolved_entity_keys: bool
    - missing_entity_names: list[str]
    """
    if not required_entity_names:
        return False, []
    if entity_name_to_guid is None:
        missing = sorted({str(x) for x in required_entity_names if str(x).strip() != ""}, key=lambda t: t.casefold())
        return True, list(missing)
    missing2 = sorted(
        {str(x) for x in required_entity_names if str(x) not in set(entity_name_to_guid.keys()) and str(x).strip() != ""},
        key=lambda t: t.casefold(),
    )
    return bool(missing2), list(missing2)


def _set_placeholder_registries_for_writeback(
    *,
    ui_key_to_guid_registry: Dict[str, int],
    allow_unresolved_ui_keys: bool,
    component_name_to_id: Optional[Dict[str, int]],
    allow_unresolved_component_keys: bool,
    entity_name_to_guid: Optional[Dict[str, int]],
    allow_unresolved_entity_keys: bool,
) -> None:
    set_ui_key_guid_registry(dict(ui_key_to_guid_registry), allow_unresolved=bool(allow_unresolved_ui_keys))
    set_component_id_registry(
        (dict(component_name_to_id) if component_name_to_id is not None else None),
        allow_unresolved=bool(allow_unresolved_component_keys),
    )
    set_entity_id_registry(
        (dict(entity_name_to_guid) if entity_name_to_guid is not None else None),
        allow_unresolved=bool(allow_unresolved_entity_keys),
    )


def _reset_placeholder_registries_after_writeback() -> None:
    set_ui_key_guid_registry(None, allow_unresolved=False)
    set_component_id_registry(None, allow_unresolved=False)
    set_entity_id_registry(None, allow_unresolved=False)

