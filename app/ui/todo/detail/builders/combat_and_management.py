from __future__ import annotations

from typing import List

from app.models.todo_item import TodoItem
from app.ui.todo.misc.todo_config import CombatTypeNames, ManagementTypeNames
from app.ui.todo.detail.todo_detail_builder_registry import (
    TodoDetailBuildContext,
    register_detail_prefix,
    register_detail_type,
)
from app.ui.todo.detail.builders.shared_builders import (
    BulletListBlock,
    DetailDocument,
    DetailSection,
    ParagraphBlock,
    ParagraphStyle,
    TableBlock,
    build_collapsible_raw_section,
    format_value_preview,
)


@register_detail_type("combat_projectile")
def build_combat_projectile_document(
    _context: TodoDetailBuildContext,
    todo: TodoItem,
    info: dict,
    _detail_type: str,
) -> DetailDocument:
    document = DetailDocument()
    section = DetailSection(title="投射物配置", level=3)

    data_value = info.get("data", {})
    data_mapping = data_value if isinstance(data_value, dict) else {}
    projectile_name = (
        data_mapping.get("projectile_name")
        or data_mapping.get("name")
        or info.get("projectile_id")
        or ""
    )
    if projectile_name:
        section.blocks.append(
            ParagraphBlock(
                text=f"名称：{projectile_name}",
                style=ParagraphStyle.EMPHASIS,
            )
        )

    properties_section = DetailSection(title="属性标签页（图1）", level=4)
    properties_paragraph = "在右侧“属性”标签页中，按分组完成本地投射物的基础与生命周期配置："
    properties_section.blocks.append(
        ParagraphBlock(text=properties_paragraph, style=ParagraphStyle.NORMAL)
    )
    properties_section.blocks.append(
        BulletListBlock(
            items=[
                "基础设置：选择投射物模型资产（例如：木箱），并根据需要调整 X / Y / Z 缩放比例。",
                "原生碰撞：根据玩法勾选“初始生效”“是否可攀爬”等碰撞相关开关。",
                "战斗参数：在“属性设置”中选择是继承创建者还是独立配置属性，并确认“后续是否受创建者影响”。",
                "生命周期设置：决定是否永久持续；如非永久，则设置持续时长(s) 以及 XZ / Y 方向的销毁距离阈值。",
                "生命周期结束行为：为生命周期结束时需要触发的效果预留能力单元入口（例如：爆炸、回收等）。",
            ]
        )
    )

    components_section = DetailSection(title="组件标签页（图2）", level=4)
    components_paragraph = "在“组件”标签页中，为投射物挂载和配置专用组件："
    components_section.blocks.append(
        ParagraphBlock(text=components_paragraph, style=ParagraphStyle.NORMAL)
    )
    components_section.blocks.append(
        BulletListBlock(
            items=[
                "特效播放：维护投射物飞行或出现时需要播放的特效列表，通过“详细编辑”调整具体特效与触发时机。",
                "投射运动器：选择运动类型（如直线投射），并在“详细编辑”中设置速度、重力系数等运动参数。",
                "命中检测：配置命中检测触发区（例如“区域1”），在“详细编辑”里调整碰撞体积、层级过滤等检测规则。",
            ]
        )
    )

    abilities_section = DetailSection(title="能力标签页（图3）", level=4)
    abilities_paragraph = "在“能力”标签页中，集中维护投射物命中或销毁时要触发的能力逻辑："
    abilities_section.blocks.append(
        ParagraphBlock(text=abilities_paragraph, style=ParagraphStyle.NORMAL)
    )
    abilities_section.blocks.append(
        BulletListBlock(
            items=[
                "能力单元：为命中、生命周期结束等事件添加能力单元条目；本页只负责建立引用与顺序，具体能力内容在能力库中维护。"
            ]
        )
    )

    document.sections.append(section)
    document.sections.append(properties_section)
    document.sections.append(components_section)
    document.sections.append(abilities_section)
    return document


@register_detail_prefix("combat_")
def build_combat_generic_document(
    _context: TodoDetailBuildContext,
    _todo: TodoItem,
    info: dict,
    detail_type: str,
) -> DetailDocument:
    document = DetailDocument()
    section = DetailSection(title=CombatTypeNames.get_name(detail_type), level=3)

    data_value = info.get("data", {})
    if isinstance(data_value, dict) and data_value:
        data_mapping = data_value
        name_text = str(data_mapping.get("name", ""))
        if name_text:
            section.blocks.append(
                ParagraphBlock(text=name_text, style=ParagraphStyle.EMPHASIS)
            )
        guide_text = str(info.get("guide") or "").strip()
        if guide_text:
            section.blocks.append(ParagraphBlock(text=guide_text, style=ParagraphStyle.HINT))

        rows: List[List[str]] = []
        max_fields = 24
        for key in list(data_mapping.keys())[: max_fields + 1]:
            if key == "name":
                continue
            if len(rows) >= max_fields:
                break
            value = data_mapping.get(key)
            rows.append([str(key), format_value_preview(value)])
        if rows:
            section.blocks.append(TableBlock(headers=["字段", "值（预览）"], rows=rows))
        if len([k for k in data_mapping.keys() if k != "name"]) > max_fields:
            section.blocks.append(
                ParagraphBlock(
                    text="更多字段已省略（见下方“原始数据”折叠区）。",
                    style=ParagraphStyle.HINT,
                )
            )
        section.blocks.append(build_collapsible_raw_section(title="原始数据（data）", payload=data_mapping))
    elif isinstance(data_value, list) and data_value:
        guide_text = str(info.get("guide") or "").strip()
        if guide_text:
            section.blocks.append(ParagraphBlock(text=guide_text, style=ParagraphStyle.HINT))

        section.blocks.append(
            ParagraphBlock(text=f"数据条目数：{len(data_value)}", style=ParagraphStyle.NORMAL)
        )
        rows: List[List[str]] = []
        max_items = 30
        for index, entry in enumerate(data_value[:max_items]):
            rows.append([str(index), format_value_preview(entry)])
        if rows:
            section.blocks.append(TableBlock(headers=["序号", "条目（预览）"], rows=rows))
        if len(data_value) > max_items:
            section.blocks.append(
                ParagraphBlock(
                    text="更多条目已省略（见下方“原始数据”折叠区）。",
                    style=ParagraphStyle.HINT,
                )
            )
        section.blocks.append(build_collapsible_raw_section(title="原始数据（data）", payload=data_value))
    else:
        # data 不是 dict/list：按纯文本展示，避免频繁切换任务时因格式差异崩溃
        text = str(data_value) if data_value is not None else ""
        if text.strip():
            section.blocks.append(ParagraphBlock(text=text, style=ParagraphStyle.NORMAL))

    document.sections.append(section)
    return document


@register_detail_prefix("management_")
def build_management_generic_document(
    _context: TodoDetailBuildContext,
    _todo: TodoItem,
    info: dict,
    detail_type: str,
) -> DetailDocument:
    document = DetailDocument()
    section = DetailSection(title=ManagementTypeNames.get_name(detail_type), level=3)

    data_value = info.get("data", {})
    if isinstance(data_value, dict) and data_value:
        data_mapping = data_value
        name_text = str(data_mapping.get("name", ""))
        if name_text:
            section.blocks.append(
                ParagraphBlock(text=name_text, style=ParagraphStyle.EMPHASIS)
            )
        guide_text = str(info.get("guide") or "").strip()
        if guide_text:
            section.blocks.append(ParagraphBlock(text=guide_text, style=ParagraphStyle.HINT))

        rows: List[List[str]] = []
        max_fields = 24
        for key in list(data_mapping.keys())[: max_fields + 1]:
            if key == "name":
                continue
            if len(rows) >= max_fields:
                break
            value = data_mapping.get(key)
            rows.append([str(key), format_value_preview(value)])
        if rows:
            section.blocks.append(TableBlock(headers=["字段", "值（预览）"], rows=rows))
        if len([k for k in data_mapping.keys() if k != "name"]) > max_fields:
            section.blocks.append(
                ParagraphBlock(
                    text="更多字段已省略（见下方“原始数据”折叠区）。",
                    style=ParagraphStyle.HINT,
                )
            )
        section.blocks.append(build_collapsible_raw_section(title="原始数据（data）", payload=data_mapping))
    elif isinstance(data_value, list) and data_value:
        guide_text = str(info.get("guide") or "").strip()
        if guide_text:
            section.blocks.append(ParagraphBlock(text=guide_text, style=ParagraphStyle.HINT))

        section.blocks.append(
            ParagraphBlock(text=f"数据条目数：{len(data_value)}", style=ParagraphStyle.NORMAL)
        )
        rows: List[List[str]] = []
        max_items = 30
        for index, entry in enumerate(data_value[:max_items]):
            rows.append([str(index), format_value_preview(entry)])
        if rows:
            section.blocks.append(TableBlock(headers=["序号", "条目（预览）"], rows=rows))
        if len(data_value) > max_items:
            section.blocks.append(
                ParagraphBlock(
                    text="更多条目已省略（见下方“原始数据”折叠区）。",
                    style=ParagraphStyle.HINT,
                )
            )
        section.blocks.append(build_collapsible_raw_section(title="原始数据（data）", payload=data_value))
    else:
        text = str(data_value) if data_value is not None else ""
        if text.strip():
            section.blocks.append(ParagraphBlock(text=text, style=ParagraphStyle.NORMAL))

    document.sections.append(section)
    return document


