from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional, Tuple


def _try_load_ui_key_to_guid_registry_for_graph_model(
    # legacy compatibility: allow positional call
    # (older callers/tests use `_try_load_ui_key_to_guid_registry_for_graph_model(Path(...))`)
    graph_model_json_path: Path,
    required_ui_keys: set[str] | None = None,
) -> Optional[Tuple[Dict[str, int], Path]]:
    """
    尝试为当前写回阶段加载 UIKey→GUID 注册表（仅用于“遗留工具链/诊断”）。

    注意：
    - 写回主流程已不再依赖/落盘 `ui_guid_registry.json`；应优先以 base `.gil` 的 UI records 反查 GUID。
    - 本函数保留的唯一稳定来源是“运行时缓存 registry”与（可选）GraphModel(JSON) 内携带的 snapshot。

    优先级（从高到低）：
    1) GraphModel(JSON) 明确携带 `ui_guid_registry_snapshot_path`：直接读取该快照；
    2) 若能推断 workspace_root/package_id：优先从 `ui_export_records.json` 选择“覆盖 required_ui_keys 最多”的快照（更贴近写回时的 UIKey 命名口径）；
    3) 回退读取运行时缓存 registry（历史语义，通常缺少 LAYOUT_INDEX__HTML__* 且 key 命名可能与图不一致）；
    4) 若 (3) 失败：从 GraphModel(JSON) 元信息推断 workspace_root/package_id 后读取运行时缓存 registry。
    """
    from ugc_file_tools.ui.guid_registry import (
        load_ui_guid_registry,
        try_infer_workspace_root_and_package_id_from_graph_model_json_path,
        try_load_ui_guid_registry_for_graph_model_json_path,
    )

    required = {str(k).strip() for k in (required_ui_keys or set()) if str(k).strip() != ""}

    # 1) snapshot (reproducible)
    p = Path(graph_model_json_path).resolve()
    if p.is_file():
        graph_json_object = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(graph_json_object, dict):
            ui_snapshot_path_text = str(graph_json_object.get("ui_guid_registry_snapshot_path") or "").strip()
            if ui_snapshot_path_text != "":
                from ugc_file_tools.ui.export_records import load_ui_guid_registry_snapshot

                ui_snapshot_path = Path(ui_snapshot_path_text).resolve()
                if not ui_snapshot_path.is_file():
                    raise FileNotFoundError(str(ui_snapshot_path))
                snapshot_mapping = load_ui_guid_registry_snapshot(Path(ui_snapshot_path))
                return dict(snapshot_mapping), Path(ui_snapshot_path).resolve()

    def _try_select_best_snapshot_from_export_records(
        *, workspace_root: Path, package_id: str
    ) -> Optional[Tuple[Dict[str, int], Path]]:
        from ugc_file_tools.ui.export_records import load_ui_export_records, load_ui_guid_registry_snapshot

        best: Tuple[int, str, Dict[str, int], Path] | None = None
        for r in load_ui_export_records(workspace_root=Path(workspace_root), package_id=str(package_id)):
            payload = dict(r.payload or {})
            snap_text = str(payload.get("ui_guid_registry_snapshot_path") or "").strip()
            if snap_text == "":
                continue
            snap_path = Path(snap_text).resolve()
            if not snap_path.is_file():
                continue
            mapping = load_ui_guid_registry_snapshot(Path(snap_path))
            hit = 0
            if required:
                for k in required:
                    if k in mapping:
                        hit += 1
            # (hit, created_at) maximize
            cand = (int(hit), str(r.created_at), dict(mapping), Path(snap_path).resolve())
            if best is None or (cand[0], cand[1]) > (best[0], best[1]):
                best = cand
        if best is None:
            return None
        _hit, _ts, mapping, snap_path = best
        return dict(mapping), Path(snap_path).resolve()

    # 2) prefer snapshots from export records (closest to UI export/writeback naming conventions)
    from ugc_file_tools.ui.guid_registry import (
        load_ui_guid_registry,
        try_infer_workspace_root_and_package_id_from_graph_model_json_path,
        try_load_ui_guid_registry_for_graph_model_json_path,
    )
    inferred = try_infer_workspace_root_and_package_id_from_graph_model_json_path(Path(graph_model_json_path))
    if inferred is not None:
        workspace_root, package_id = inferred
        selected = _try_select_best_snapshot_from_export_records(workspace_root=Path(workspace_root), package_id=str(package_id))
        if selected is not None:
            mapping, snap_path = selected
            return dict(mapping), Path(snap_path).resolve()

    # 3) historical behavior: infer from graph_model_json_path
    fallback_registry: Optional[Tuple[Dict[str, int], Path]] = None
    loaded = try_load_ui_guid_registry_for_graph_model_json_path(Path(graph_model_json_path))
    if loaded is not None:
        mapping, registry_path = loaded
        # 若 required_ui_keys 命中率不足，继续尝试从 export_records/snapshot 补齐；否则直接返回当前 registry。
        if required and any(k not in mapping for k in required):
            fallback_registry = (dict(mapping), Path(registry_path).resolve())
        else:
            return dict(mapping), Path(registry_path).resolve()

    # 4) infer from JSON metadata
    if not p.is_file():
        return fallback_registry
    graph_json_object2 = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(graph_json_object2, dict):
        return fallback_registry

    workspace_root_text = str(
        graph_json_object2.get("graph_generater_root")
        or graph_json_object2.get("workspace_root")
        or graph_json_object2.get("gg_root")
        or ""
    ).strip()
    package_id_text = str(
        graph_json_object2.get("active_package_id")
        or graph_json_object2.get("package_id")
        or graph_json_object2.get("package")
        or ""
    ).strip()
    graph_code_file_text = str(graph_json_object2.get("graph_code_file") or "").strip()

    inferred_workspace: Optional[Path] = Path(workspace_root_text).resolve() if workspace_root_text else None
    inferred_package: Optional[str] = package_id_text if package_id_text else None

    if graph_code_file_text:
        inferred_from_code = try_infer_workspace_root_and_package_id_from_graph_model_json_path(Path(graph_code_file_text))
        if inferred_from_code is not None:
            inferred_workspace, inferred_package = inferred_from_code

    if inferred_workspace is None or inferred_package is None:
        return fallback_registry

    # 若可以推断 workspace/package，再尝试用 export_records 快照补齐（通常比当前 registry 更贴近写回所需命名口径）
    selected2 = _try_select_best_snapshot_from_export_records(
        workspace_root=Path(inferred_workspace),
        package_id=str(inferred_package),
    )
    if selected2 is not None:
        mapping, snap_path = selected2
        return dict(mapping), Path(snap_path).resolve()

    mapping3, source_path3, _candidates = load_ui_guid_registry(
        workspace_root=Path(inferred_workspace),
        project_root=None,
        package_id=str(inferred_package),
        prefer_project_registry=False,
    )
    if mapping3 is None:
        return fallback_registry
    return dict(mapping3), Path(source_path3).resolve()

