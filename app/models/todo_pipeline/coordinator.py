"""节点图任务编排：统一由此处调度 TodoGraphTaskGenerator"""

from __future__ import annotations

from typing import Callable, Dict, Iterable, List, Optional

from app.models import TodoItem
from app.models.package_loader import PackageLoader
from app.models.todo_graph_task_generator import TodoGraphTaskGenerator
from app.models.todo_node_type_helper import NodeTypeHelper
from engine.resources.resource_manager import ResourceManager


class GraphTaskCoordinator:
    """封装 TodoGraphTaskGenerator 的创建/调用，供上层策略复用"""

    def __init__(
        self,
        *,
        type_helper: NodeTypeHelper,
        resource_manager: Optional[ResourceManager],
        add_todo: Callable[[TodoItem], None],
        todo_map: Dict[str, TodoItem],
        package_loader: PackageLoader,
    ) -> None:
        self._add_todo = add_todo
        self._package_loader = package_loader
        self._graph_task_generator = TodoGraphTaskGenerator(
            type_helper=type_helper,
            resource_manager=resource_manager,
            add_todo_callback=add_todo,
            todo_map=todo_map,
            package=getattr(package_loader, "package", None),
        )

    def create_graph_root_tasks(
        self,
        *,
        parent_id: str,
        graph_ids: Iterable[str],
        target_id: str,
        template_ctx_id: str = "",
        instance_ctx_id: str = "",
        preview_template_id: str = "",
        suppress_auto_jump: bool = False,
    ) -> List[str]:
        created_ids: List[str] = []
        for graph_id in graph_ids:
            if not graph_id:
                continue
            graph_name = self._package_loader.resolve_graph_name(graph_id)
            graph_root = self._graph_task_generator.create_graph_root_todo(
                parent_id=parent_id,
                graph_id=graph_id,
                graph_name=graph_name,
                target_id=target_id,
                template_ctx_id=template_ctx_id,
                instance_ctx_id=instance_ctx_id,
                preview_template_id=preview_template_id,
                suppress_auto_jump=suppress_auto_jump,
            )
            self._add_todo(graph_root)
            created_ids.append(graph_root.todo_id)
        return created_ids

    def generate_graph_tasks(
        self,
        *,
        parent_id: str,
        graph_id: str,
        graph_name: str,
        graph_data: Dict,
        preview_template_id: str = "",
        suppress_auto_jump: bool = False,
        graph_root: Optional[TodoItem] = None,
        attach_graph_root: bool = True,
    ) -> List[str]:
        return self._graph_task_generator.generate_graph_tasks(
            parent_id=parent_id,
            graph_id=graph_id,
            graph_name=graph_name,
            graph_data=graph_data,
            preview_template_id=preview_template_id,
            suppress_auto_jump=suppress_auto_jump,
            existing_root=graph_root,
            attach_root=attach_graph_root,
        )


