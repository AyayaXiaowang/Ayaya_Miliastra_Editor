from __future__ import annotations

import shutil
from pathlib import Path


def _copy_dir_tree(*, src_dir: Path, dst_dir: Path) -> None:
    """
    递归复制目录树（覆盖同名文件）。
    - 用于 bundle 输出与 output_user_dir 复制
    - 不使用 try/except：任何 IO 错误直接抛出（fail-fast）
    """
    src = Path(src_dir).resolve()
    dst = Path(dst_dir).resolve()
    if not src.is_dir():
        raise FileNotFoundError(str(src))
    dst.mkdir(parents=True, exist_ok=True)

    for p in sorted(src.rglob("*"), key=lambda x: x.as_posix().casefold()):
        rel = p.relative_to(src)
        target = (dst / rel).resolve()
        if p.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if p.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
            continue


def _export_bundle_sidecars(
    *,
    project_root: Path,
    output_dir: Path,
    include_signals: bool,
    include_ui_guid_registry: bool,
    workspace_root: Path,
    package_id: str,
    ui_key_to_guid_registry: dict[str, int] | None = None,
) -> dict[str, str]:
    """
    将“运行时依赖的管理配置”复制到输出目录，形成可分发的 bundle 结构。
    返回 copied_items（key=逻辑名，value=目标路径）。
    """
    copied: dict[str, str] = {}
    out_root = Path(output_dir).resolve()
    pkg_root = Path(project_root).resolve()

    if bool(include_signals):
        src_signals = (pkg_root / "管理配置" / "信号").resolve()
        if src_signals.is_dir():
            dst_signals = (out_root / "管理配置" / "信号").resolve()
            _copy_dir_tree(src_dir=src_signals, dst_dir=dst_signals)
            copied["signals_dir"] = str(dst_signals)

    if bool(include_ui_guid_registry):
        # 说明：
        # - 首选：若导出侧已选择 UI 导出记录（ui_export_records snapshot），则直接用 snapshot mapping 写出；
        # - fallback：运行时缓存 registry（本机）；
        # - legacy：项目存档内的历史 registry（若存在）；
        # - bundle 内统一落盘到 `管理配置/UI控件GUID映射/ui_guid_registry.json`，便于分发/导入。
        dst = (out_root / "管理配置" / "UI控件GUID映射" / "ui_guid_registry.json").resolve()
        if ui_key_to_guid_registry is not None and ui_key_to_guid_registry:
            from ugc_file_tools.ui.guid_registry_format import write_ui_guid_registry_file

            write_ui_guid_registry_file(dst, ui_key_to_guid_registry)
            copied["ui_guid_registry_file"] = str(dst)
        else:
            from engine.utils.cache.cache_paths import get_ui_guid_registry_cache_file

            runtime_registry = get_ui_guid_registry_cache_file(Path(workspace_root).resolve(), str(package_id)).resolve()
            legacy_registry = (pkg_root / "管理配置" / "UI控件GUID映射" / "ui_guid_registry.json").resolve()

            src: Path | None = None
            if runtime_registry.is_file():
                src = Path(runtime_registry).resolve()
            elif legacy_registry.is_file():
                src = Path(legacy_registry).resolve()

            if src is not None:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied["ui_guid_registry_file"] = str(dst)

    return copied

