from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from app.models import TodoItem
from engine.utils.graph.graph_utils import is_flow_port_name
from engine.nodes.composite_node_manager import get_composite_node_manager


class CompositeTaskBuilder:
    def __init__(
        self,
        add_todo: Callable[[TodoItem], None],
        resource_manager=None,
        generate_graph_tasks: Optional[Callable[..., List[str]]] = None,
    ) -> None:
        self._add_todo = add_todo
        self._resource_manager = resource_manager
        self._generate_graph_tasks = generate_graph_tasks

    def build_composite_steps(
        self,
        parent_id: str,
        graph_id: str,
        graph_name: str,
        composite_id: str,
        composite_name: str,
        template_ctx_id: str,
        instance_ctx_id: str,
        composite_nodes: Optional[List[Any]] = None,
    ) -> List[str]:
        comp_root_id = f"{parent_id}:composite:{graph_id}:{composite_id}"
        comp_root = TodoItem(
            todo_id=comp_root_id,
            title=f"复合节点：{composite_name}",
            description="该复合节点在后续节点图中被使用，请先完成其创建与配置",
            level=3,
            parent_id=parent_id,
            children=[],
            task_type="template",
            target_id=composite_id,
            detail_info={
                "type": "composite_root",
                "composite_id": composite_id,
                "composite_name": composite_name,
                "graph_id": graph_id,
                "graph_name": graph_name,
                "template_id": template_ctx_id if template_ctx_id else None,
                "instance_id": instance_ctx_id if instance_ctx_id else None,
            },
        )
        self._add_todo(comp_root)

        comp_create_id = f"{comp_root_id}:create"
        comp_create = TodoItem(
            todo_id=comp_create_id,
            title="新建复合节点",
            description="在复合节点库中新建该复合节点",
            level=4,
            parent_id=comp_root_id,
            children=[],
            task_type="template",
            target_id=composite_id,
            detail_info={
                "type": "composite_create_new",
                "composite_id": composite_id,
                "composite_name": composite_name,
                "template_id": template_ctx_id if template_ctx_id else None,
                "instance_id": instance_ctx_id if instance_ctx_id else None,
            },
        )
        self._add_todo(comp_create)
        comp_root.children.append(comp_create_id)

        comp_meta_id = f"{comp_root_id}:meta"
        comp_meta = TodoItem(
            todo_id=comp_meta_id,
            title="设置复合节点属性",
            description="填写名称、描述与文件夹（如需）",
            level=4,
            parent_id=comp_root_id,
            children=[],
            task_type="template",
            target_id=composite_id,
            detail_info={
                "type": "composite_set_meta",
                "name": composite_name,
                "description": "",
                "folder_path": "",
                "composite_id": composite_id,
                "template_id": template_ctx_id if template_ctx_id else None,
                "instance_id": instance_ctx_id if instance_ctx_id else None,
            },
        )
        self._add_todo(comp_meta)
        comp_root.children.append(comp_meta_id)

        input_pins, output_pins = self._collect_composite_pins(composite_nodes or [])
        comp_pins_id = f"{comp_root_id}:pins"
        comp_pins = TodoItem(
            todo_id=comp_pins_id,
            title="设置虚拟引脚",
            description="在复合节点编辑器中添加对应的输入/输出与流程引脚",
            level=4,
            parent_id=comp_root_id,
            children=[],
            task_type="template",
            target_id=composite_id,
            detail_info={
                "type": "composite_set_pins",
                "composite_id": composite_id,
                "inputs": input_pins,
                "outputs": output_pins,
                "input_count": len(input_pins),
                "output_count": len(output_pins),
                "template_id": template_ctx_id if template_ctx_id else None,
                "instance_id": instance_ctx_id if instance_ctx_id else None,
            },
        )
        self._add_todo(comp_pins)
        comp_root.children.append(comp_pins_id)

        comp_save_id = f"{comp_root_id}:save"
        comp_save = TodoItem(
            todo_id=comp_save_id,
            title="保存复合节点",
            description="保存并刷新节点库以便在节点图中使用",
            level=4,
            parent_id=comp_root_id,
            children=[],
            task_type="template",
            target_id=composite_id,
            detail_info={
                "type": "composite_save",
                "composite_id": composite_id,
                "template_id": template_ctx_id if template_ctx_id else None,
                "instance_id": instance_ctx_id if instance_ctx_id else None,
            },
        )
        self._add_todo(comp_save)
        comp_root.children.append(comp_save_id)

        if (
            self._resource_manager
            and hasattr(self._resource_manager, "workspace_path")
            and self._generate_graph_tasks
        ):
            workspace_path = self._resource_manager.workspace_path
            manager = get_composite_node_manager(workspace_path)
            manager.load_subgraph_if_needed(composite_id)
            composite_obj = manager.get_composite_node(composite_id)
            if composite_obj and isinstance(composite_obj.sub_graph, dict):
                sub_graph = composite_obj.sub_graph
                if sub_graph.get("nodes"):
                    internal_graph_id = f"{graph_id}:{composite_id}:sub"
                    internal_graph_name = f"{composite_name} 内部子图"
                    internal_ids = self._generate_graph_tasks(
                        parent_id=comp_root_id,
                        graph_id=internal_graph_id,
                        graph_name=internal_graph_name,
                        graph_data=sub_graph,
                        preview_template_id=template_ctx_id or "",
                        suppress_auto_jump=True,
                    )
                    existing = comp_root.children.copy()
                    ordered: List[str] = []
                    if comp_create_id in existing:
                        ordered.append(comp_create_id)
                    ordered.extend(internal_ids)
                    if comp_meta_id in existing:
                        ordered.append(comp_meta_id)
                    if comp_pins_id in existing:
                        ordered.append(comp_pins_id)
                    if comp_save_id in existing:
                        ordered.append(comp_save_id)

                    def _uniq(seq: List[str]) -> List[str]:
                        seen: set[str] = set()
                        result: List[str] = []
                        for item in seq:
                            if item not in seen:
                                seen.add(item)
                                result.append(item)
                        return result

                    comp_root.children = _uniq(ordered)

        return [comp_root_id]

    def _collect_composite_pins(self, composite_nodes: List[Any]) -> tuple:
        input_pins: List[Dict[str, Optional[bool]]] = []
        output_pins: List[Dict[str, Optional[bool]]] = []
        for node in composite_nodes:
            for port in node.inputs:
                input_pins.append({"name": port.name, "is_flow": is_flow_port_name(port.name)})
            for port in node.outputs:
                output_pins.append({"name": port.name, "is_flow": is_flow_port_name(port.name)})

        def _dedup_pins(pins: List[Dict[str, Optional[bool]]]) -> List[Dict[str, Optional[bool]]]:
            seen: set[tuple[str, Optional[bool]]] = set()
            result: List[Dict[str, Optional[bool]]] = []
            for pin in pins:
                key = (pin["name"], pin["is_flow"])
                if key not in seen:
                    seen.add(key)
                    result.append(pin)
            return result

        return _dedup_pins(input_pins), _dedup_pins(output_pins)