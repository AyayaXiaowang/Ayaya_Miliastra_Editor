from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, List


# NOTE: This module intentionally keeps a small surface area; higher-level helpers should live in subpackages.

def _runtime_ui_guid_registry_path(*, workspace_root: Path, package_id: str) -> Path:
    from engine.utils.cache.cache_paths import get_ui_guid_registry_cache_file

    return get_ui_guid_registry_cache_file(Path(workspace_root).resolve(), str(package_id)).resolve()


def load_ui_guid_registry(
    *,
    workspace_root: Path | None,
    project_root: Path | None,
    package_id: str | None,
    prefer_project_registry: bool = True,
) -> tuple[Dict[str, int] | None, Path, list[Path]]:
    """
    加载 UIKey→GUID registry，并返回：
    - mapping（仅保留 guid>0；若未找到 registry 文件则为 None）
    - source_path（本次选中的 registry 路径；若未找到则为“首选路径 hint”）
    - candidates（尝试路径列表，按优先级排序）

    约定候选路径：
    - 运行时缓存：<runtime_cache>/ui_artifacts/<package_id>/ui_guid_registry.json

    说明：
    - 项目存档内的 `管理配置/UI控件GUID映射/ui_guid_registry.json` 已不再作为稳定接口；
      写回/导出应优先以“本次输出 .gil 的 UI records”为真源反查 GUID。
    """
    candidates_runtime: list[Path] = []

    pid = str(package_id or "").strip()
    if workspace_root is not None and pid != "":
        candidates_runtime.append(_runtime_ui_guid_registry_path(workspace_root=Path(workspace_root), package_id=pid))

    if not candidates_runtime:
        raise ValueError("无法推断 ui_guid_registry.json 运行时缓存路径：workspace_root/package_id 不足")

    candidates: list[Path]
    candidates = list(candidates_runtime)

    source_hint = candidates[0]

    from ugc_file_tools.ui.guid_registry_format import load_ui_guid_registry_mapping as _load

    for p in candidates:
        if Path(p).is_file():
            return _load(Path(p)), Path(p).resolve(), candidates

    return None, Path(source_hint).resolve(), candidates


def try_infer_workspace_root_and_package_id_from_graph_model_json_path(
    graph_model_json_path: Path,
) -> tuple[Path, str] | None:
    """
    尝试从 GraphModel(JSON) 的路径推断 (workspace_root, package_id)。

    约定：
    - <workspace>/assets/资源库/项目存档/<package_id>/...
    """
    p = Path(graph_model_json_path).resolve()
    parts = list(p.parts)

    assets_index: int | None = None
    for i, part in enumerate(parts):
        if str(part) == "assets":
            assets_index = int(i)
            break

    project_index: int | None = None
    for i, part in enumerate(parts):
        if str(part) == "项目存档":
            project_index = int(i)
            break

    if assets_index is None or project_index is None or project_index + 1 >= len(parts):
        return None

    workspace_root = Path(*parts[:assets_index]).resolve()
    package_id = str(parts[project_index + 1]).strip()
    if package_id == "":
        return None

    return workspace_root, package_id


def try_load_ui_guid_registry_for_graph_model_json_path(
    graph_model_json_path: Path,
) -> tuple[Dict[str, int], Path] | None:
    """
    写回链路辅助：从 GraphModel(JSON) 路径推断 package_id，并读取运行时缓存 registry。

    注意：该入口保持“仅 runtime cache”的语义（与历史写回行为一致），不从项目存档读取。
    """
    inferred = try_infer_workspace_root_and_package_id_from_graph_model_json_path(Path(graph_model_json_path))
    if inferred is None:
        return None
    workspace_root, package_id = inferred

    mapping, source_path, _candidates = load_ui_guid_registry(
        workspace_root=Path(workspace_root),
        project_root=None,
        package_id=str(package_id),
        prefer_project_registry=False,
    )
    if mapping is None:
        return None
    return mapping, Path(source_path).resolve()


def extract_ui_key_from_placeholder_text(text: str) -> str | None:
    raw = str(text or "").strip()
    lowered = raw.lower()
    if lowered.startswith("ui_key:"):
        key = raw[len("ui_key:") :].strip()
    elif lowered.startswith("ui:"):
        key = raw[len("ui:") :].strip()
    else:
        return None
    return key if key != "" else None


def collect_ui_key_placeholders_from_value(value: object) -> set[str]:
    out: set[str] = set()
    if isinstance(value, str):
        k = extract_ui_key_from_placeholder_text(value)
        if k is not None:
            out.add(str(k))
        return out
    if isinstance(value, list):
        for item in value:
            out |= collect_ui_key_placeholders_from_value(item)
        return out
    if isinstance(value, dict):
        for k, v in value.items():
            out |= collect_ui_key_placeholders_from_value(k)
            out |= collect_ui_key_placeholders_from_value(v)
        return out
    return out


def collect_ui_key_placeholders_from_graph_json_object(*, graph_json_object: Dict[str, object]) -> set[str]:
    # 统一复用 GraphModel IR（中间表示）的归一化/遍历口径，避免跨模块依赖 writeback 的私有适配器。
    from ugc_file_tools.graph.model_ir import iter_node_payload_dicts, normalize_graph_model_payload

    graph_model = normalize_graph_model_payload(graph_json_object)
    if not isinstance(graph_model, dict):
        return set()

    keys: set[str] = set()

    for payload in iter_node_payload_dicts(graph_model):
        input_constants = payload.get("input_constants")
        if isinstance(input_constants, dict):
            keys |= collect_ui_key_placeholders_from_value(input_constants)

    graph_variables = graph_model.get("graph_variables")
    if isinstance(graph_variables, list):
        for v in graph_variables:
            if not isinstance(v, dict):
                continue
            default_value = v.get("default_value")
            keys |= collect_ui_key_placeholders_from_value(default_value)

    return keys


__all__ = [
    "load_ui_guid_registry",
    "try_infer_workspace_root_and_package_id_from_graph_model_json_path",
    "try_load_ui_guid_registry_for_graph_model_json_path",
    "extract_ui_key_from_placeholder_text",
    "collect_ui_key_placeholders_from_value",
    "collect_ui_key_placeholders_from_graph_json_object",
]


