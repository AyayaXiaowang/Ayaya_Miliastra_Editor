from __future__ import annotations

import json
from pathlib import Path

from engine.resources.package_index_manager import PackageIndexManager
from engine.resources.resource_manager import ResourceManager
from engine.utils.resource_library_layout import (
    discover_package_resource_roots,
    get_shared_root_dir,
)

MAX_PACKAGE_ID_PREVIEW = 5
MAX_INSTANCE_PREVIEW = 8


def collect_template_referencing_package_ids(
    package_index_manager: PackageIndexManager | None,
    *,
    template_id: str,
) -> list[str]:
    if package_index_manager is None:
        return []

    referencing_package_ids: list[str] = []
    for package_info in package_index_manager.list_packages():
        package_id_value = package_info.get("package_id")
        if not isinstance(package_id_value, str) or not package_id_value:
            continue
        package_id = package_id_value
        package_index = package_index_manager.load_package_index(package_id)
        if not package_index:
            continue
        if template_id in package_index.resources.templates:
            referencing_package_ids.append(package_id)

    referencing_package_ids.sort(key=lambda text: text.casefold())
    return referencing_package_ids


def collect_template_referencing_instances(
    resource_manager: ResourceManager,
    *,
    template_id: str,
) -> list[str]:
    referencing_instance_lines: list[str] = []

    resource_library_dir = getattr(resource_manager, "resource_library_dir", None)
    if not isinstance(resource_library_dir, Path):
        return []

    shared_root = get_shared_root_dir(resource_library_dir)
    package_roots = discover_package_resource_roots(resource_library_dir)
    roots: list[tuple[str, Path]] = [("共享", shared_root)]
    roots.extend([(path.name, path) for path in package_roots])

    for pkg_label, root_dir in roots:
        instances_root = root_dir / "实体摆放"
        if not instances_root.exists() or not instances_root.is_dir():
            continue
        for json_path in sorted(instances_root.rglob("*.json")):
            if not json_path.is_file():
                continue
            data = json.loads(json_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            if str(data.get("template_id", "") or "") != str(template_id or ""):
                continue
            instance_id_value = str(data.get("instance_id", "") or "").strip() or json_path.stem
            instance_name_value = str(data.get("name", "") or "").strip() or instance_id_value
            referencing_instance_lines.append(f"[{pkg_label}] {instance_name_value}（{instance_id_value}）")

    referencing_instance_lines.sort(key=lambda text: text.casefold())
    return referencing_instance_lines


def build_template_delete_confirmation_message(
    *,
    template_name: str,
    template_id: str,
    referencing_package_ids: list[str],
    referencing_instance_lines: list[str],
) -> str:
    # 构建确认文案：提示该模板是否仍被某些存档纳入。
    if referencing_package_ids:
        # 仅在提示中展示少量 ID，避免对话框过长；详细排查可通过存档库页面完成。
        preview_count = min(len(referencing_package_ids), MAX_PACKAGE_ID_PREVIEW)
        preview_ids = ", ".join(referencing_package_ids[:preview_count])
        extra_tail = ""
        if len(referencing_package_ids) > preview_count:
            extra_tail = f" 等共 {len(referencing_package_ids)} 个存档"

        instance_hint = ""
        if referencing_instance_lines:
            preview_instances = referencing_instance_lines[:MAX_INSTANCE_PREVIEW]
            more_instances = max(0, len(referencing_instance_lines) - len(preview_instances))
            instance_hint = (
                "\n同时检测到以下实体仍在引用该元件（节选）：\n" + "\n".join(f"- {line}" for line in preview_instances)
            )
            if more_instances:
                instance_hint += f"\n- ... 另有 {more_instances} 个引用未展开"

        return (
            f"将从资源库中彻底删除元件 '{template_name}'（ID: {template_id}），"
            "并从所有存档索引中移除对该元件的引用。\n\n"
            "当前仍有以下存档纳入了该元件：\n"
            f"- {preview_ids}{extra_tail}\n\n"
            f"{instance_hint}\n\n"
            "此操作无法撤销，可能导致这些存档中原本使用该元件的实体变为“悬空引用”。\n"
            "如需保留某些存档的使用，请先在对应存档中替换或移除相关实体，再执行删除。\n\n"
            "确定要继续执行全局删除吗？"
        )

    instance_hint = ""
    if referencing_instance_lines:
        preview_instances = referencing_instance_lines[:MAX_INSTANCE_PREVIEW]
        more_instances = max(0, len(referencing_instance_lines) - len(preview_instances))
        instance_hint = (
            "\n⚠️ 虽然未发现任何存档显式纳入该元件，但仍检测到实体引用（节选）：\n"
            + "\n".join(f"- {line}" for line in preview_instances)
        )
        if more_instances:
            instance_hint += f"\n- ... 另有 {more_instances} 个引用未展开"

    return (
        f"将从资源库中彻底删除未被任何存档纳入的元件 '{template_name}'（ID: {template_id}）。\n\n"
        f"{instance_hint}\n\n"
        "此操作会删除元件 JSON 文件本身，且无法撤销。\n"
        "确定要继续吗？"
    )

