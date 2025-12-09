from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def load_equipment_templates(source_dir: Path) -> List[Dict[str, Any]]:
    """从管理配置/装备数据目录中加载“锻刀英雄”武器模板，用于生成对应的装备类道具。

    约定：
    - 仅处理带有 metadata.forge_hero_source == "text_prototype" 的记录；
    - 保留 equipment_id 作为道具元数据中的引用字段，不改变现有装备模板。
    """
    templates: List[Dict[str, Any]] = []
    for path in sorted(source_dir.glob("*.json")):
        if path.name == "装备1.json":
            continue
        with path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
        if not isinstance(data, dict):
            continue
        metadata = data.get("metadata", {})
        if not isinstance(metadata, dict):
            continue
        if metadata.get("forge_hero_source") != "text_prototype":
            continue
        templates.append(data)
    return templates


def build_item_payload_from_equipment(equipment: Dict[str, Any]) -> Dict[str, Any]:
    """根据单个装备模板构造一条“装备类道具”配置。"""
    equipment_id = str(equipment.get("equipment_id", ""))
    equipment_name = str(equipment.get("equipment_name", "")).strip() or "未命名装备"
    rarity = str(equipment.get("rarity", "common"))

    item_id = f"item_{equipment_id}"
    payload: Dict[str, Any] = {
        "item_id": item_id,
        "item_name": equipment_name,
        "description": "",
        "item_type": "equipment",
        "rarity": rarity,
        "max_stack": 1,
        "icon": equipment.get("icon", ""),
        "use_effect": "",
        "cooldown": 0.0,
        "attributes": {},
        "requirements": {},
        "metadata": {
            "forge_hero_source": "text_prototype",
            "equipment_id": equipment_id,
        },
        "id": item_id,
        "last_modified": "",
        "updated_at": "",
        "name": equipment_name,
    }
    return payload


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    equipment_dir = project_root / "assets" / "资源库" / "管理配置" / "装备数据"
    items_dir = project_root / "assets" / "资源库" / "战斗预设" / "道具"
    items_dir.mkdir(parents=True, exist_ok=True)

    templates = load_equipment_templates(equipment_dir)
    for equipment in templates:
        equipment_name = str(equipment.get("equipment_name", "")).strip() or "未命名装备"
        filename = f"{equipment_name}.json"
        out_path = items_dir / filename

        # 幂等写入：若目标道具文件已存在，则跳过，避免覆盖 UI 中手工编辑的内容。
        if out_path.exists():
            continue

        payload = build_item_payload_from_equipment(equipment)
        with out_path.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()


