from __future__ import annotations

"""
Todo 详情数据适配器

职责：
- 为 TodoDetailRenderer 提供所需的数据收集接口，解耦 UI 主组件中的统计/汇总逻辑。

说明：
- 依赖传入的 widget 访问 todo_map 等运行时数据，但不直接操作 UI 控件。
"""

from typing import Any, Dict, List
from engine.resources.resource_manager import ResourceType

from app.models.todo_item import TodoItem
from ui.todo.todo_config import StepTypeRules


class TodoDetailAdapter:
    def __init__(self, widget: Any) -> None:
        self.widget = widget

    # === 根分类概览 ===
    def collect_categories_info(self, root_todo: TodoItem) -> Dict[str, List[tuple]]:
        """收集存档根节点下的所有分类信息。

        返回映射：{ 分类标题: [(名称, 类型/说明), ...] }
        """
        categories_info: Dict[str, List[tuple]] = {}

        for child_id in root_todo.children:
            child_todo = self.widget.todo_map.get(child_id)
            if not child_todo:
                continue

            category_type = child_todo.detail_info.get("category", "")
            items: List[tuple] = []

            # 遍历分类下的所有项目
            for item_id in child_todo.children:
                item_todo = self.widget.todo_map.get(item_id)
                if not item_todo:
                    continue

                item_info = item_todo.detail_info
                item_name = item_info.get("name", item_todo.title)

                if category_type == "templates":
                    item_type = item_info.get("entity_type", "")
                    items.append((item_name, item_type))
                elif category_type == "instances":
                    item_type = f"基于 {item_info.get('template_name', '未知元件')}"
                    items.append((item_name, item_type))
                elif category_type == "combat":
                    item_type = item_info.get("type", "战斗配置")
                    items.append((item_name, item_type))
                elif category_type == "management":
                    item_type = item_info.get("type", "管理配置")
                    items.append((item_name, item_type))

            if items:
                categories_info[child_todo.title] = items

        return categories_info

    # === 分类项列表 ===
    def collect_category_items(self, category_todo: TodoItem) -> List[Dict[str, Any]]:
        """收集分类下的所有项目信息。"""
        items: List[Dict[str, Any]] = []
        category_type = category_todo.detail_info.get("category", "")

        for child_id in category_todo.children:
            child_todo = self.widget.todo_map.get(child_id)
            if not child_todo:
                continue

            item_info = child_todo.detail_info

            if category_type == "templates":
                # 统计模板的配置项
                config_parts: List[str] = []
                for subchild_id in child_todo.children:
                    subchild = self.widget.todo_map.get(subchild_id)
                    if subchild:
                        if "variables" in subchild.detail_info.get("type", ""):
                            var_count = len(subchild.detail_info.get("variables", []))
                            config_parts.append(f"{var_count}个变量")
                        elif "components" in subchild.detail_info.get("type", ""):
                            comp_count = len(subchild.detail_info.get("components", []))
                            config_parts.append(f"{comp_count}个组件")
                        elif "graph" in subchild.detail_info.get("type", ""):
                            config_parts.append("节点图")

                items.append(
                    {
                        "name": item_info.get("name", child_todo.title),
                        "entity_type": item_info.get("entity_type", ""),
                        "config_summary": ", ".join(config_parts) if config_parts else "无配置",
                    }
                )

            elif category_type == "instances":
                # 统计实例的配置项
                config_parts = []
                for subchild_id in child_todo.children:
                    subchild = self.widget.todo_map.get(subchild_id)
                    if subchild:
                        if "properties" in subchild.detail_info.get("type", ""):
                            config_parts.append("属性配置")
                        elif "graph" in subchild.detail_info.get("type", ""):
                            config_parts.append("节点图")

                items.append(
                    {
                        "name": item_info.get("name", child_todo.title),
                        "template_name": item_info.get("template_name", ""),
                        "config_summary": ", ".join(config_parts) if config_parts else "无配置",
                    }
                )

            elif category_type in ["combat", "management"]:
                items.append({"name": item_info.get("name", child_todo.title), "type": item_info.get("type", "")})

            elif category_type == "standalone_graphs":
                # 节点图总览：统计每个图的变量数、节点数、类型与文件夹
                graph_id = str(item_info.get("graph_id", "") or child_todo.target_id or "")
                graph_name = str(item_info.get("graph_name", "") or child_todo.title)

                # 尝试从宿主详情面板/列表组件获取资源管理器（由主窗口注入），避免在此处直接依赖 MainWindow 结构
                resource_manager = getattr(self.widget, "resource_manager", None)
                if resource_manager is None and getattr(self.widget, "host_list_widget", None) is not None:
                    host = self.widget.host_list_widget
                    if hasattr(host, "resource_manager"):
                        resource_manager = host.resource_manager

                variable_count = 0
                node_count = 0
                graph_type = ""
                folder_path = ""

                if resource_manager is not None and graph_id:
                    # 优先加载完整资源以获得变量数；如果失败再回退到轻量元数据
                    data = resource_manager.load_resource(ResourceType.GRAPH, graph_id)
                    if isinstance(data, dict):
                        inner = data.get("data", {}) if isinstance(data.get("data", {}), dict) else {}
                        vars_list = inner.get("graph_variables", [])
                        if isinstance(vars_list, list):
                            variable_count = len(vars_list)
                        nodes_data = inner.get("nodes", [])
                        if isinstance(nodes_data, list):
                            node_count = len(nodes_data)
                        elif isinstance(nodes_data, dict):
                            node_count = len(nodes_data)
                        graph_type = str(data.get("graph_type", ""))
                        folder_path = str(data.get("folder_path", ""))
                    else:
                        meta = resource_manager.load_graph_metadata(graph_id)
                        if isinstance(meta, dict):
                            node_count = int(meta.get("node_count", 0))
                            graph_type = str(meta.get("graph_type", ""))
                            folder_path = str(meta.get("folder_path", ""))

                items.append(
                    {
                        "name": graph_name,
                        "graph_id": graph_id,
                        "graph_type": graph_type,
                        "folder_path": folder_path,
                        "variable_count": variable_count,
                        "node_count": node_count,
                    }
                )

        return items

    # === 模板概览 ===
    def collect_template_summary(self, template_todo: TodoItem) -> Dict[str, int]:
        """收集模板的配置项概要。"""
        summary: Dict[str, int] = {}

        for child_id in template_todo.children:
            child_todo = self.widget.todo_map.get(child_id)
            if not child_todo:
                continue

            child_type = child_todo.detail_info.get("type", "")

            if child_type == "template_basic":
                config_count = len(child_todo.detail_info.get("config", {}))
                if config_count > 0:
                    summary["基础属性"] = config_count
            elif child_type == "template_variables_table":
                var_count = len(child_todo.detail_info.get("variables", []))
                summary["自定义变量"] = var_count
            elif child_type == "template_components_table":
                comp_count = len(child_todo.detail_info.get("components", []))
                summary["组件"] = comp_count
            elif StepTypeRules.is_template_graph_root(child_type):
                summary["节点图"] = 1

        return summary

    # === 实例概览 ===
    def collect_instance_summary(self, instance_todo: TodoItem) -> Dict[str, int]:
        """收集实例的配置项概要。"""
        summary: Dict[str, int] = {}

        for child_id in instance_todo.children:
            child_todo = self.widget.todo_map.get(child_id)
            if not child_todo:
                continue

            child_type = child_todo.detail_info.get("type", "")

            if child_type == "instance_properties_table":
                summary["位置与旋转"] = 1
                override_vars = child_todo.detail_info.get("override_variables", [])
                if override_vars:
                    summary["覆盖变量"] = len(override_vars)
            elif StepTypeRules.is_template_graph_root(child_type):
                if "节点图" not in summary:
                    summary["节点图"] = 0
                summary["节点图"] += 1

        return summary


