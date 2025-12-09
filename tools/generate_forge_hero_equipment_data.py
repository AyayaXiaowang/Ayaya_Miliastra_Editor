from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def build_forge_hero_weapon_configs() -> List[Dict[str, Any]]:
    """构建一组用于“锻刀英雄”玩法的武器模板配置。

    设计约定：
    - 仅提供名称、槽位与基础稀有度等静态信息，不承载玩家锻造进度；
    - 与文本原型 `forge_hero_text_prototype` 中的 PREDEFINED_WEAPON_NAMES 名称列表保持一致；
    - 真正的数值成长、技能与宝石等动态属性由局内存档结构体（例如“玩家背包”中的并行列表字段）与锻造节点图负责维护。
    """
    weapon_names: List[str] = [
        "方天画戟",
        "青龙偃月刀",
        "丈八蛇矛",
        "倚天剑",
        "屠龙刀",
        "轩辕剑",
        "干将",
        "莫邪",
        "鱼肠剑",
        "湛卢",
        "承影",
        "赤霄",
        "太阿",
        "七星龙渊",
        "寒铁重剑",
        "流光双刃",
        "百炼钢枪",
        "破军长刀",
        "龙吟宝剑",
        "虎贲战戟",
        "玄铁重剑",
        "惊虹长弓",
        "落日神弓",
        "追月轻弓",
        "苍穹法杖",
        "星辰权杖",
        "虚空之杖",
        "鎏金长枪",
        "烈焰战斧",
        "霜寒白刃",
        "雷霆战锤",
        "暗影匕首",
        "逐风双刀",
        "碧海长刀",
        "鎏光长剑",
        "裂山巨斧",
        "森罗骨矛",
        "流火短剑",
        "落星重锤",
        "青冥长剑",
        "雪饮狂刀",
        "蚀日长弓",
        "弦月弯刀",
        "墨竹拐杖",
        "秋水佩剑",
        "紫电青霜",
        "踏雪长枪",
        "龙胆亮银枪",
        "金乌烈焰刀",
    ]

    configs: List[Dict[str, Any]] = []
    for index, name in enumerate(weapon_names, start=1):
        equipment_id = f"forge_hero_weapon_{index:03d}"
        config: Dict[str, Any] = {
            "equipment_id": equipment_id,
            "equipment_name": name,
            "equipment_slot": "weapon",
            "base_attributes": {},
            "special_effects": [],
            "rarity": "common",
            "level_requirement": 1,
            "icon": "",
            "model": "",
            "description": "",
            "metadata": {
                "forge_hero_source": "text_prototype",
                "prototype_index": index,
            },
        }
        configs.append(config)
    return configs


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    target_dir = project_root / "assets" / "资源库" / "管理配置" / "装备数据"
    target_dir.mkdir(parents=True, exist_ok=True)

    configs = build_forge_hero_weapon_configs()
    for config in configs:
        equipment_name = str(config.get("equipment_name", "")).strip() or "未命名装备"
        # 这里直接使用装备名作为文件名；Windows/NTFS 支持中文文件名，
        # 且资源系统按内容中的 equipment_id 进行逻辑引用，文件名仅用于人工浏览。
        filename = f"{equipment_name}.json"
        out_path = target_dir / filename

        # 幂等写入：若文件已存在则跳过，避免覆盖手工编辑的配置。
        if out_path.exists():
            continue

        with out_path.open("w", encoding="utf-8") as fp:
            json.dump(config, fp, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()


