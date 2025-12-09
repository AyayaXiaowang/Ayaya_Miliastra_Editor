"""管理配置资源文件名迁移脚本（CLI）。

目标：
- 将部分“管理配置”与相关资源的 JSON 文件从“ID 命名”迁移为“名字命名”；
- 同时为这些资源补全稳定的 ID 字段与通用 `name` 字段，实现：
  - 用 ID 做引用（节点图 / 存档索引中只看 ID）；
  - 用名字命名文件（资源库目录中按名称即可识别 JSON）。

用法（在项目根目录执行）：
    python -X utf8 tools/migrate_management_resource_filenames.py         # 试运行，仅打印计划
    python -X utf8 tools/migrate_management_resource_filenames.py --run  # 实际迁移并重建索引
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import Dict, List, Tuple
from importlib.machinery import SourceFileLoader


# 统一工作空间根目录与 sys.path（参考其它 tools 脚本）
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = Path(__file__).resolve().parent

if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

# 修复 Windows 控制台编码问题
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(1, str(WORKSPACE_ROOT))

from engine.configs.resource_types import ResourceType
from engine.resources import ResourceManager
from engine.resources.management_naming_rules import get_id_and_display_name_fields


# 需要执行“按名字命名”的典型资源类型（管理页面中多条记录的管理配置为主）
TARGET_RESOURCE_TYPES: Tuple[ResourceType, ...] = (
    ResourceType.TIMER,
    ResourceType.LEVEL_VARIABLE,
    ResourceType.SKILL_RESOURCE,
    ResourceType.EQUIPMENT_DATA,
    ResourceType.SHOP_TEMPLATE,
    ResourceType.UI_LAYOUT,
    ResourceType.UI_WIDGET_TEMPLATE,
    ResourceType.MAIN_CAMERA,
    ResourceType.BACKGROUND_MUSIC,
    ResourceType.LIGHT_SOURCE,
    ResourceType.PATH,
    ResourceType.ENTITY_DEPLOYMENT_GROUP,
    ResourceType.UNIT_TAG,
    ResourceType.SCAN_TAG,
    ResourceType.SHIELD,
    ResourceType.CHAT_CHANNEL,
)


def _resolve_display_name(
    resource_type: ResourceType,
    resource_id: str,
    payload: Dict[str, object],
) -> str:
    """根据资源类型与数据解析出“业务显示名称”。

    优先：各自的数据模型中约定的 *_name 字段。
    其次：通用的 name 字段。
    最后：回退到资源 ID。
    """
    _id_field, display_name_field = get_id_and_display_name_fields(resource_type)

    if display_name_field:
        raw_value = payload.get(display_name_field)
        if isinstance(raw_value, str):
            text = raw_value.strip()
            if text:
                return text

    raw_name = payload.get("name")
    if isinstance(raw_name, str):
        text = raw_name.strip()
        if text:
            return text

    return resource_id


def _migrate_for_type(
    manager: ResourceManager,
    resource_type: ResourceType,
    *,
    dry_run: bool,
) -> int:
    """迁移单一 ResourceType 下所有资源的文件名与 name/ID 字段。

    返回实际需要写盘的资源数量（在 dry_run 模式下仍然统计“理论迁移数”）。
    """
    resource_ids: List[str] = manager.list_resources(resource_type)
    if not resource_ids:
        return 0

    bucket = manager.resource_index.get(resource_type, {})

    migrated_count = 0
    type_label = resource_type.name
    print(f"[{type_label}] 发现 {len(resource_ids)} 个资源，开始检查...")

    for resource_id in sorted(resource_ids):
        payload_any = manager.load_resource(resource_type, resource_id)
        if not isinstance(payload_any, dict):
            continue

        payload: Dict[str, object] = dict(payload_any)
        id_field, _display_field = get_id_and_display_name_fields(resource_type)

        # 补全专用 ID 字段：缺失时写入 resource_id，确保 JSON 本体携带稳定 ID。
        needs_save = False
        if id_field:
            raw_id_value = payload.get(id_field)
            if not isinstance(raw_id_value, str) or not raw_id_value.strip():
                payload[id_field] = resource_id
                needs_save = True

        # 解析业务显示名，并据此生成目标文件名与通用 name 字段。
        display_name = _resolve_display_name(resource_type, resource_id, payload)
        sanitized_name = ResourceManager.sanitize_filename(display_name)

        # 当前物理文件名（不含扩展名）
        file_path = bucket.get(resource_id)
        if file_path is None:
            # 回退到基于当前 ID 与现有 filename_cache 推导路径
            file_path = manager._file_ops.get_resource_file_path(  # type: ignore[attr-defined]
                resource_type,
                resource_id,
                manager.id_to_filename_cache,
            )

        current_stem = file_path.stem

        # 若通用 name 与文件名都已经是目标值，仅在需要补全 ID 时写盘。
        raw_name = payload.get("name")
        if isinstance(raw_name, str):
            current_name_value = raw_name.strip()
        else:
            current_name_value = ""

        if current_name_value != sanitized_name:
            payload["name"] = sanitized_name
            needs_save = True

        if current_stem != sanitized_name:
            print(
                f"  - {file_path.name}  =>  {sanitized_name}.json"
            )
        elif needs_save:
            print(f"  - {file_path.name}  （仅更新 JSON 中的 ID/name 字段）")

        if not needs_save:
            continue

        migrated_count += 1
        if dry_run:
            continue

        manager.save_resource(resource_type, resource_id, payload)

    if migrated_count == 0:
        print(f"[{type_label}] 无需迁移，全部文件名与 ID/name 字段已符合约定。")
    else:
        print(f"[{type_label}] 预计将更新 {migrated_count} 个资源。")

    return migrated_count


def migrate_management_resources(
    workspace_path: Path,
    *,
    dry_run: bool,
) -> Dict[str, int]:
    """对管理配置相关资源执行文件名与 ID/name 字段迁移。"""
    manager = ResourceManager(workspace_path)

    print("=" * 60)
    print("管理配置资源文件名迁移")
    print(f"工作空间: {workspace_path}")
    print(f"模式: {'试运行（不写盘）' if dry_run else '实际迁移（写盘并重建索引）'}")
    print("=" * 60)

    stats: Dict[str, int] = {}

    for resource_type in TARGET_RESOURCE_TYPES:
        count = _migrate_for_type(manager, resource_type, dry_run=dry_run)
        if count > 0:
            stats[resource_type.name] = count
        print()

    # 额外处理：局内存档管理目录下的代码级模板（.py 文件），按模板名重命名物理文件。
    save_point_template_count = _migrate_ingame_save_templates_by_name(
        workspace_path,
        dry_run=dry_run,
    )
    if save_point_template_count > 0:
        stats["INGAME_SAVE_TEMPLATES"] = save_point_template_count
        print()

    if not dry_run:
        # 迁移完成后重建资源索引，确保缓存与物理文件名保持一致。
        removed = manager.clear_persistent_resource_index_cache()
        print(f"已清理旧的资源索引缓存文件数量: {removed}")
        manager.rebuild_index()
        print("资源索引已重建。")

    print("=" * 60)
    print("迁移统计：")
    total = 0
    for type_name, count in stats.items():
        print(f"  - {type_name}: {count} 个资源")
        total += count
    print(f"  总计: {total} 个资源需要更新")
    print("=" * 60)

    return stats


def _migrate_ingame_save_templates_by_name(
    workspace_path: Path,
    *,
    dry_run: bool,
) -> int:
    """将局内存档模板代码资源从“ID 命名”迁移为“按模板名命名”。

    约定：
    - 根目录：assets/资源库/管理配置/局内存档管理
    - 每个 Python 模块导出：
      - SAVE_POINT_ID: str
      - SAVE_POINT_PAYLOAD: dict，至少包含 template_id/template_name/save_point_name 等字段
    - 物理文件名优先采用 template_name，其次 save_point_name，最后回退到 SAVE_POINT_ID。
    """
    base_directory = (
        workspace_path
        / "assets"
        / "资源库"
        / "管理配置"
        / "局内存档管理"
    )

    if not base_directory.is_dir():
        return 0

    print("=" * 60)
    print("局内存档模板文件名迁移（代码资源 .py）")
    print(f"目录: {base_directory}")

    migrated_count = 0

    for python_file_path in sorted(base_directory.glob("*.py")):
        if python_file_path.name == "__init__.py":
            continue

        module_name = f"code_save_point_template_{abs(hash(python_file_path.as_posix()))}"
        loader = SourceFileLoader(module_name, str(python_file_path))
        module = loader.load_module()

        save_point_id_value = getattr(module, "SAVE_POINT_ID", None)
        payload_value = getattr(module, "SAVE_POINT_PAYLOAD", None)

        if not isinstance(save_point_id_value, str) or not save_point_id_value:
            raise ValueError(f"无效的 SAVE_POINT_ID（{python_file_path}）")
        if not isinstance(payload_value, dict):
            raise ValueError(f"无效的 SAVE_POINT_PAYLOAD（{python_file_path}）")

        template_payload = dict(payload_value)

        raw_template_name = template_payload.get("template_name")
        if isinstance(raw_template_name, str) and raw_template_name.strip():
            template_name_text = raw_template_name.strip()
        else:
            raw_save_point_name = template_payload.get("save_point_name")
            if isinstance(raw_save_point_name, str) and raw_save_point_name.strip():
                template_name_text = raw_save_point_name.strip()
            else:
                template_name_text = save_point_id_value

        sanitized_name = ResourceManager.sanitize_filename(template_name_text)
        if not sanitized_name:
            sanitized_name = save_point_id_value

        current_stem = python_file_path.stem
        if current_stem == sanitized_name:
            continue

        print(f"  - {python_file_path.name}  =>  {sanitized_name}.py")
        migrated_count += 1

        if dry_run:
            continue

        target_path = python_file_path.with_name(f"{sanitized_name}{python_file_path.suffix}")
        if target_path.exists() and target_path != python_file_path:
            raise ValueError(
                f"目标文件已存在，无法重命名：{target_path}"
            )

        python_file_path.rename(target_path)

    if migrated_count == 0:
        print("无需迁移，局内存档模板文件名已按模板名命名。")
    else:
        print(f"预计将重命名 {migrated_count} 个局内存档模板代码文件。")

    return migrated_count


def main() -> None:
    """CLI 入口。"""
    workspace_path = WORKSPACE_ROOT
    actual_run = "--run" in sys.argv
    dry_run = not actual_run

    migrate_management_resources(workspace_path, dry_run=dry_run)


if __name__ == "__main__":
    main()


