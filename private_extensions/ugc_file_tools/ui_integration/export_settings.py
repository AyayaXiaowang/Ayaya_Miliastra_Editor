from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass(frozen=True, slots=True)
class UGCFileToolsExportSettings:
    """
    `.gia` / `.gil` 导出入口的 UI 持久化设置。

    说明：
    - 存放于运行期缓存：`app/runtime/cache/ugc_file_tools_export_settings.json`
    - 仅保存“用户上次选择的路径/开关”等 UI 状态，不保存任何私有资源内容。
    """

    inject_target_gil_path: str = ""  # 可选：导出后注入到的目标 .gil（真源地图存档）
    inject_skip_non_empty_check: bool = False
    inject_create_backup: bool = True
    # 可选：占位符参考 `.gil`（用于回填节点图中的 entity_key/component_key）
    id_ref_gil_path: str = ""


def _settings_file_path(*, workspace_root: Path) -> Path:
    return (Path(workspace_root).resolve() / "app" / "runtime" / "cache" / "ugc_file_tools_export_settings.json").resolve()


def load_ugc_file_tools_export_settings(*, workspace_root: Path) -> UGCFileToolsExportSettings:
    path = _settings_file_path(workspace_root=Path(workspace_root))
    if not path.is_file():
        return UGCFileToolsExportSettings()
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        return UGCFileToolsExportSettings()
    inject_target_gil_path = obj.get("inject_target_gil_path")
    inject_skip_non_empty_check = obj.get("inject_skip_non_empty_check")
    inject_create_backup = obj.get("inject_create_backup")
    id_ref_gil_path = obj.get("id_ref_gil_path")
    return UGCFileToolsExportSettings(
        inject_target_gil_path=str(inject_target_gil_path or "").strip()
        if isinstance(inject_target_gil_path, (str, int))
        else "",
        inject_skip_non_empty_check=bool(inject_skip_non_empty_check) if isinstance(inject_skip_non_empty_check, bool) else False,
        inject_create_backup=bool(inject_create_backup) if isinstance(inject_create_backup, bool) else True,
        id_ref_gil_path=str(id_ref_gil_path or "").strip() if isinstance(id_ref_gil_path, (str, int)) else "",
    )


def save_ugc_file_tools_export_settings(*, workspace_root: Path, settings: UGCFileToolsExportSettings) -> Path:
    path = _settings_file_path(workspace_root=Path(workspace_root))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {
        "inject_target_gil_path": str(settings.inject_target_gil_path or "").strip(),
        "inject_skip_non_empty_check": bool(settings.inject_skip_non_empty_check),
        "inject_create_backup": bool(settings.inject_create_backup),
        "id_ref_gil_path": str(settings.id_ref_gil_path or "").strip(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path

