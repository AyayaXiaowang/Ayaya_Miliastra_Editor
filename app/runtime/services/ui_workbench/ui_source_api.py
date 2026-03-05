from __future__ import annotations

from pathlib import Path

from .utils import list_html_files


def get_shared_ui_source_dir(*, workspace_root: Path) -> Path:
    return (Path(workspace_root).resolve() / "assets" / "资源库" / "共享" / "管理配置" / "UI源码").resolve()


def get_project_ui_source_dir(*, workspace_root: Path, package_id: str) -> Path:
    return (
        Path(workspace_root).resolve()
        / "assets"
        / "资源库"
        / "项目存档"
        / str(package_id)
        / "管理配置"
        / "UI源码"
    ).resolve()


def build_ui_source_catalog_payload(*, workspace_root: Path, current_package_id: str) -> dict:
    """返回 UI源码（HTML）清单：项目 + 共享。"""
    current_package_id_text = str(current_package_id or "").strip()
    is_global_view = (not current_package_id_text) or current_package_id_text == "global_view"

    shared_ui_dir = get_shared_ui_source_dir(workspace_root=workspace_root)
    project_ui_dir = (
        get_project_ui_source_dir(workspace_root=workspace_root, package_id=current_package_id_text)
        if not is_global_view
        else None
    )

    items: list[dict[str, object]] = []
    if project_ui_dir is not None:
        for name in list_html_files(project_ui_dir):
            items.append({"scope": "project", "file_name": name, "is_shared": False})
    for name in list_html_files(shared_ui_dir):
        items.append({"scope": "shared", "file_name": name, "is_shared": True})

    return {"ok": True, "items": items, "current_package_id": current_package_id_text}


def resolve_ui_source_path(
    *,
    workspace_root: Path,
    scope: str,
    rel_path: str,
    current_package_id: str,
) -> Path:
    """将 Web 侧的 (scope, rel_path) 解析为磁盘路径。"""
    s = str(scope or "project").strip()
    rp = str(rel_path or "").replace("\\", "/").strip().lstrip("/")
    if not rp:
        raise ValueError("rel_path is required")
    if "/" in rp:
        # 预览页的 rel_path 目前只应为文件名；禁止目录穿越
        raise ValueError(f"rel_path must be a file name: {rp}")

    if s == "shared":
        return (get_shared_ui_source_dir(workspace_root=workspace_root) / rp).resolve()

    if s != "project":
        raise ValueError(f"invalid scope: {s!r}")

    current_package_id_text = str(current_package_id or "").strip()
    if (not current_package_id_text) or current_package_id_text == "global_view":
        raise RuntimeError(
            "请先切换到某个【项目存档】再读取项目 UI源码（当前为 <共享资源>/未选择）。"
        )
    return (get_project_ui_source_dir(workspace_root=workspace_root, package_id=current_package_id_text) / rp).resolve()


def read_ui_source_payload(
    *,
    workspace_root: Path,
    scope: str,
    rel_path: str,
    current_package_id: str,
) -> dict:
    file_path = resolve_ui_source_path(
        workspace_root=workspace_root,
        scope=scope,
        rel_path=rel_path,
        current_package_id=current_package_id,
    )
    if not file_path.is_file():
        return {"ok": False, "error": f"file not found: {file_path}"}
    scope_text = str(scope or "project").strip() or "project"
    rel_text = str(rel_path or "").strip()
    return {
        "ok": True,
        "scope": scope_text,
        "rel_path": rel_text,
        "file_name": rel_text,
        "is_shared": scope_text == "shared",
        "content": file_path.read_text(encoding="utf-8"),
    }


__all__ = [
    "build_ui_source_catalog_payload",
    "get_project_ui_source_dir",
    "get_shared_ui_source_dir",
    "read_ui_source_payload",
    "resolve_ui_source_path",
]

