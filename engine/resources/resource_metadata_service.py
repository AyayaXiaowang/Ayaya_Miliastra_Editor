from __future__ import annotations

from typing import Any, Dict, List

from engine.configs.resource_types import ResourceType


class ResourceMetadataService:
    """资源元数据提取服务（UI/搜索/列表展示使用）。

    设计目标：
    - 将“按 ResourceType 的字段规则”从 ResourceManager 中抽离，避免门面类持续膨胀；
    - 输出轻量、结构稳定的 metadata 字典，供 UI 与工具脚本复用；
    - 不吞错：输入结构异常时按 Python 规则直接抛出，便于尽早暴露数据问题。
    """

    _DISPLAY_NAME_KEYS_BY_TYPE: Dict[ResourceType, List[str]] = {
        # 战斗预设系列
        ResourceType.PLAYER_TEMPLATE: ["template_name"],
        ResourceType.PLAYER_CLASS: ["class_name"],
        ResourceType.UNIT_STATUS: ["status_name"],
        ResourceType.SKILL: ["skill_name"],
        ResourceType.PROJECTILE: ["projectile_name"],
        ResourceType.ITEM: ["item_name"],
        # 管理配置系列
        ResourceType.UI_LAYOUT: ["layout_name"],
        ResourceType.UI_WIDGET_TEMPLATE: ["template_name"],
        ResourceType.UNIT_TAG: ["tag_name"],
        ResourceType.SHIELD: ["shield_name"],
        ResourceType.SCAN_TAG: ["scan_tag_name"],
        ResourceType.SAVE_POINT: ["save_point_name"],
        ResourceType.TIMER: ["timer_name"],
        ResourceType.LEVEL_VARIABLE: ["variable_name"],
        ResourceType.CHAT_CHANNEL: ["channel_name"],
        ResourceType.LIGHT_SOURCE: ["light_name"],
        ResourceType.PERIPHERAL_SYSTEM: ["system_name"],
        ResourceType.BACKGROUND_MUSIC: ["music_name"],
        ResourceType.LEVEL_SETTINGS: ["level_name"],
    }

    def build_resource_metadata(
        self,
        resource_type: ResourceType,
        resource_id: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """从资源 payload 构建统一元数据字典。"""
        raw_metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}

        display_name = self.resolve_display_name(resource_type, resource_id, payload)
        guid_value = self._extract_guid(payload, raw_metadata)
        graph_ids = self._collect_graph_ids(resource_type, payload, raw_metadata)

        return {
            "resource_id": resource_id,
            "resource_type": resource_type.value,
            "name": display_name,
            "description": payload.get("description", ""),
            "updated_at": payload.get("updated_at", ""),
            "created_at": payload.get("created_at", ""),
            "guid": guid_value,
            "graph_ids": graph_ids,
        }

    def resolve_display_name(
        self,
        resource_type: ResourceType,
        resource_id: str,
        payload: Dict[str, Any],
    ) -> str:
        """根据资源类型解析 UI 友好的显示名称。"""
        preferred_keys = list(self._DISPLAY_NAME_KEYS_BY_TYPE.get(resource_type, []))
        if "name" not in preferred_keys:
            preferred_keys.append("name")

        for key in preferred_keys:
            raw_value = payload.get(key)
            if isinstance(raw_value, str):
                stripped_value = raw_value.strip()
                if stripped_value:
                    return stripped_value

        return resource_id

    def _extract_guid(self, payload: Dict[str, Any], raw_metadata: Dict[str, Any]) -> str:
        guid_value = ""
        raw_guid = raw_metadata.get("guid")
        if raw_guid is not None:
            guid_value = str(raw_guid)
        elif "guid" in payload and payload.get("guid") is not None:
            guid_value = str(payload.get("guid"))
        return guid_value

    def _collect_graph_ids(
        self,
        resource_type: ResourceType,
        payload: Dict[str, Any],
        raw_metadata: Dict[str, Any],
    ) -> List[str]:
        graph_ids: List[str] = []

        def append_graph_id(value: object) -> None:
            if isinstance(value, str) and value and value not in graph_ids:
                graph_ids.append(value)

        default_graphs = payload.get("default_graphs")
        if isinstance(default_graphs, list):
            for graph_id in default_graphs:
                append_graph_id(graph_id)

        additional_graphs = payload.get("additional_graphs")
        if isinstance(additional_graphs, list):
            for graph_id in additional_graphs:
                append_graph_id(graph_id)

        if resource_type != ResourceType.PLAYER_TEMPLATE:
            return graph_ids

        player_editor = raw_metadata.get("player_editor")
        if not isinstance(player_editor, dict):
            return graph_ids

        def collect_from_section(section: object) -> None:
            if not isinstance(section, dict):
                return
            section_graphs = section.get("graphs")
            if isinstance(section_graphs, list):
                for graph_id in section_graphs:
                    append_graph_id(graph_id)

        collect_from_section(player_editor.get("player"))
        collect_from_section(player_editor.get("role"))

        roles_value = player_editor.get("roles")
        if isinstance(roles_value, list):
            for role_entry in roles_value:
                collect_from_section(role_entry)

        return graph_ids


