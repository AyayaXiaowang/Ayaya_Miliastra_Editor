from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def _project_component_id_registry_path(project_root: Path) -> Path:
    # 与 ui_guid_registry 同级策略：项目存档下的管理配置用于人工查看/协作。
    return (Path(project_root).resolve() / "管理配置" / "元件ID映射" / "component_id_registry.json").resolve()


def _runtime_component_id_registry_path(*, workspace_root: Path, package_id: str) -> Path:
    from engine.utils.cache.cache_paths import get_component_id_registry_cache_file

    return get_component_id_registry_cache_file(Path(workspace_root).resolve(), str(package_id)).resolve()


def load_component_id_registry_file(path: Path) -> Dict[str, int]:
    p = Path(path).resolve()
    if not p.exists():
        return {}
    obj = json.loads(p.read_text(encoding="utf-8"))
    # 兼容两种形态：
    # - {"version": 1, "component_name_to_id": {...}}
    # - {"SomeName": 10005018, ...}（早期/手工映射）
    if isinstance(obj, dict) and "component_name_to_id" in obj:
        mapping = obj.get("component_name_to_id")
    else:
        mapping = obj

    if not isinstance(mapping, dict):
        raise ValueError(f"component_id_registry 不是 dict：path={p}")

    out: Dict[str, int] = {}
    for k, v in mapping.items():
        name = str(k or "").strip()
        if name == "":
            continue
        if not isinstance(v, int):
            if isinstance(v, str) and v.strip().isdigit():
                out[name] = int(v.strip())
                continue
            raise ValueError(f"component_id_registry value 不是 int：name={name!r} value={v!r} path={p}")
        if int(v) <= 0:
            continue
        out[name] = int(v)
    return out


def _component_id_registry_history_dir(registry_path: Path) -> Path:
    return registry_path.parent / "component_id_registry_history"


def _append_component_id_registry_history_line(
    *,
    registry_path: Path,
    saved_at: str,
    mapping_total: int,
    history_file: Path,
    backup_file: Optional[Path],
) -> None:
    history_file.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "saved_at": saved_at,
        "registry_path": str(registry_path),
        "mapping_total": int(mapping_total),
        "backup_file": (str(backup_file) if backup_file is not None else None),
    }
    with history_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _backup_existing_component_id_registry(registry_path: Path, *, saved_at: str) -> Optional[Path]:
    p = Path(registry_path).resolve()
    if not p.exists():
        return None

    history_dir = _component_id_registry_history_dir(p).resolve()
    history_dir.mkdir(parents=True, exist_ok=True)

    old_text = p.read_text(encoding="utf-8")
    base_name = f"component_id_registry_{saved_at.replace(':', '').replace('-', '').replace('T', '_')}.json"
    backup_path = (history_dir / base_name).resolve()
    if backup_path.exists():
        i = 2
        while True:
            candidate = (history_dir / f"{backup_path.stem}__{i}{backup_path.suffix}").resolve()
            if not candidate.exists():
                backup_path = candidate
                break
            i += 1

    backup_path.write_text(old_text, encoding="utf-8")
    return backup_path


def save_component_id_registry_file(path: Path, component_name_to_id: Dict[str, int]) -> None:
    p = Path(path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)

    cleaned: Dict[str, int] = {}
    for k, v in component_name_to_id.items():
        name = str(k or "").strip()
        if name == "":
            continue
        if not isinstance(v, int) or int(v) <= 0:
            continue
        cleaned[name] = int(v)

    saved_at = datetime.now().isoformat(timespec="seconds")
    backup_file = _backup_existing_component_id_registry(p, saved_at=saved_at)
    history_file = (_component_id_registry_history_dir(p) / "history.jsonl").resolve()
    _append_component_id_registry_history_line(
        registry_path=p,
        saved_at=saved_at,
        mapping_total=len(cleaned),
        history_file=history_file,
        backup_file=backup_file,
    )

    payload = {
        "version": 1,
        "component_name_to_id": {k: cleaned[k] for k in sorted(cleaned.keys())},
        "updated_at": saved_at,
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_component_id_registry(
    *,
    workspace_root: Path | None,
    project_root: Path | None,
    package_id: str | None,
    prefer_project_registry: bool = True,
) -> Tuple[Dict[str, int] | None, Path, list[Path]]:
    """
    加载元件名→元件ID registry，并返回：
    - mapping（仅保留 id>0；若未找到 registry 文件则为 None）
    - source_path（本次选中的 registry 路径；若未找到则为“首选路径 hint”）
    - candidates（尝试路径列表，按优先级排序）

    候选路径：
    - 项目存档：<project_root>/管理配置/元件ID映射/component_id_registry.json
    - 运行时缓存：<runtime_cache>/component_artifacts/<package_id>/component_id_registry.json
    """
    candidates_project: list[Path] = []
    candidates_runtime: list[Path] = []

    if project_root is not None:
        candidates_project.append(_project_component_id_registry_path(Path(project_root)))

    pid = str(package_id or "").strip()
    if workspace_root is not None and pid != "":
        candidates_runtime.append(_runtime_component_id_registry_path(workspace_root=Path(workspace_root), package_id=pid))

    if not candidates_project and not candidates_runtime:
        raise ValueError("无法推断 component_id_registry.json 候选路径：workspace_root/project_root/package_id 均不足")

    candidates: list[Path]
    if bool(prefer_project_registry):
        candidates = list(candidates_project) + list(candidates_runtime)
    else:
        candidates = list(candidates_runtime) + list(candidates_project)

    source_hint = candidates[0]
    for p in candidates:
        if Path(p).is_file():
            return load_component_id_registry_file(Path(p)), Path(p).resolve(), candidates

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


def try_load_component_id_registry_for_graph_model_json_path(
    graph_model_json_path: Path,
) -> tuple[Dict[str, int], Path] | None:
    """
    写回链路辅助：从 GraphModel(JSON) 路径推断 package_id，并读取运行时缓存 registry。

    注意：该入口保持“仅 runtime cache”的语义（与 ui_guid_registry 的写回口径一致），不从项目存档读取。
    """
    inferred = try_infer_workspace_root_and_package_id_from_graph_model_json_path(Path(graph_model_json_path))
    if inferred is None:
        return None
    workspace_root, package_id = inferred

    mapping, source_path, _candidates = load_component_id_registry(
        workspace_root=Path(workspace_root),
        project_root=None,
        package_id=str(package_id),
        prefer_project_registry=False,
    )
    if mapping is None:
        return None
    return mapping, Path(source_path).resolve()


def extract_component_key_from_placeholder_text(text: str) -> str | None:
    raw = str(text or "").strip()
    lowered = raw.lower()
    if lowered.startswith("component_key:"):
        key = raw[len("component_key:") :].strip()
    elif lowered.startswith("component:"):
        key = raw[len("component:") :].strip()
    else:
        return None
    return key if key != "" else None


def collect_component_key_placeholders_from_value(value: object) -> set[str]:
    out: set[str] = set()
    if isinstance(value, str):
        k = extract_component_key_from_placeholder_text(value)
        if k is not None:
            out.add(str(k))
        return out
    if isinstance(value, list):
        for item in value:
            out |= collect_component_key_placeholders_from_value(item)
        return out
    if isinstance(value, dict):
        for k, v in value.items():
            out |= collect_component_key_placeholders_from_value(k)
            out |= collect_component_key_placeholders_from_value(v)
        return out
    return out


def collect_component_key_placeholders_from_graph_json_object(*, graph_json_object: Dict[str, object]) -> set[str]:
    from ugc_file_tools.graph.model_ir import iter_node_payload_dicts, normalize_graph_model_payload

    graph_model = normalize_graph_model_payload(graph_json_object)
    if not isinstance(graph_model, dict):
        return set()

    keys: set[str] = set()
    for payload in iter_node_payload_dicts(graph_model):
        input_constants = payload.get("input_constants")
        if isinstance(input_constants, dict):
            keys |= collect_component_key_placeholders_from_value(input_constants)

    graph_variables = graph_model.get("graph_variables")
    if isinstance(graph_variables, list):
        for v in graph_variables:
            if not isinstance(v, dict):
                continue
            default_value = v.get("default_value")
            keys |= collect_component_key_placeholders_from_value(default_value)

    return keys


__all__ = [
    "load_component_id_registry_file",
    "save_component_id_registry_file",
    "load_component_id_registry",
    "try_infer_workspace_root_and_package_id_from_graph_model_json_path",
    "try_load_component_id_registry_for_graph_model_json_path",
    "extract_component_key_from_placeholder_text",
    "collect_component_key_placeholders_from_value",
    "collect_component_key_placeholders_from_graph_json_object",
]

