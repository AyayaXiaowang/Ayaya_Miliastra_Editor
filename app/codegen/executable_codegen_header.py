from __future__ import annotations

from typing import Any, Dict, List, Optional

from engine.graph.common import format_constant
from engine.graph.models import GraphModel
from engine.utils.workspace import render_workspace_bootstrap_lines

from .executable_codegen_options import ExecutableCodegenOptions


class _ExecutableCodegenHeaderMixin:
    def _generate_executable_header(self, graph_model: GraphModel, metadata: Dict[str, Any]) -> List[str]:
        """生成 Graph Code 头部 docstring（资源库/校验器可读的 key: value 格式）。"""
        graph_id = str(metadata.get("graph_id") or getattr(graph_model, "graph_id", "") or "")
        graph_name = str(metadata.get("graph_name") or graph_model.graph_name or "")
        graph_type = str(metadata.get("graph_type") or "server")
        folder_path = str(metadata.get("folder_path") or "")
        description = str(metadata.get("description") or graph_model.description or "")

        lines = ['"""']
        if graph_id:
            lines.append(f"graph_id: {graph_id}")
        if graph_name:
            lines.append(f"graph_name: {graph_name}")
        if graph_type:
            lines.append(f"graph_type: {graph_type}")
        if folder_path:
            lines.append(f"folder_path: {folder_path}")
        if description:
            lines.append(f"description: {description}")
        lines.append('"""')
        return lines

    def _generate_executable_imports(self, graph_type: str = "server") -> List[str]:
        options = self.options
        lines: List[str] = [""]
        lines.append("from __future__ import annotations")
        lines.append("")

        # 兼容：旧 import_mode=local_prelude 视为 workspace_bootstrap（资源库不再维护 _prelude 文件）
        if options.import_mode == "local_prelude":
            options = ExecutableCodegenOptions(
                import_mode="workspace_bootstrap",
                enable_auto_validate=options.enable_auto_validate,
                prelude_module_server=options.prelude_module_server,
                prelude_module_client=options.prelude_module_client,
                validator_import_path=options.validator_import_path,
            )

        if options.import_mode != "workspace_bootstrap":
            raise ValueError(f"未知 import_mode: {options.import_mode}")

        prelude_module = (
            options.prelude_module_client if graph_type == "client" else options.prelude_module_server
        )

        lines.extend(
            render_workspace_bootstrap_lines(
                project_root_var="PROJECT_ROOT",
                assets_root_var="ASSETS_ROOT",
            )
        )
        lines.append("")

        # 直接运行文件时：仅执行校验并退出（避免导入运行时节点实现与触发 @validate_node_graph 的 import-time 校验）
        lines.extend(self._generate_main_validate_block())
        lines.append("")

        lines.append(f"from {prelude_module} import *  # noqa: F401,F403")
        lines.append(f"from {prelude_module} import GameRuntime")
        if options.enable_auto_validate:
            lines.append(f"from {options.validator_import_path} import validate_node_graph")
        return lines

    def _generate_graph_variables_block(self, graph_model: GraphModel) -> List[str]:
        """生成代码级图变量声明：GRAPH_VARIABLES。

        约定：
        - 图变量的唯一事实来源为代码级 GRAPH_VARIABLES（见 engine.graph.utils.metadata_extractor）。
        - 这里将 GraphModel.graph_variables（序列化后的 GraphVariableConfig 列表）还原为
          `GraphVariableConfig(...)` 调用列表，确保“可视化编辑→落盘→再次解析/校验”闭环不丢变量。
        """
        raw_variables = getattr(graph_model, "graph_variables", None)
        if not isinstance(raw_variables, list) or not raw_variables:
            return ["GRAPH_VARIABLES: list[GraphVariableConfig] = []"]

        # 过滤出合法条目（至少包含 name 与 variable_type）
        normalized: List[Dict[str, Any]] = []
        for entry in raw_variables:
            if not isinstance(entry, dict):
                continue
            name_value = str(entry.get("name") or "").strip()
            variable_type_value = str(entry.get("variable_type") or "").strip()
            if not name_value or not variable_type_value:
                continue
            normalized.append(entry)

        if not normalized:
            return ["GRAPH_VARIABLES: list[GraphVariableConfig] = []"]

        lines: List[str] = []
        lines.append("GRAPH_VARIABLES: list[GraphVariableConfig] = [")
        for entry in normalized:
            name_value = str(entry.get("name") or "").strip()
            variable_type_value = str(entry.get("variable_type") or "").strip()

            default_value_expr = format_constant(entry.get("default_value"))
            description_expr = format_constant(entry.get("description", ""))
            is_exposed_value = bool(entry.get("is_exposed", False))

            lines.append("    GraphVariableConfig(")
            lines.append(f"        name={format_constant(name_value)},")
            lines.append(f"        variable_type={format_constant(variable_type_value)},")
            lines.append(f"        default_value={default_value_expr},")
            lines.append(f"        description={description_expr},")
            lines.append(f"        is_exposed={'True' if is_exposed_value else 'False'},")

            # 字典类型：补充 key/value 类型声明（若存在）
            if variable_type_value.strip() == "字典":
                dict_key_type = str(entry.get("dict_key_type") or "").strip()
                dict_value_type = str(entry.get("dict_value_type") or "").strip()
                if dict_key_type:
                    lines.append(f"        dict_key_type={format_constant(dict_key_type)},")
                if dict_value_type:
                    lines.append(f"        dict_value_type={format_constant(dict_value_type)},")

            lines.append("    ),")
        lines.append("]")
        return lines

    @staticmethod
    def _generate_main_validate_block() -> List[str]:
        """生成 `python file.py` 直接执行时的自检入口（与资源库内节点图保持一致）。"""
        return [
            "if __name__ == '__main__':",
            "    from app.runtime.engine.node_graph_validator import validate_file_cli",
            "    raise SystemExit(validate_file_cli(__file__))",
        ]


__all__ = ["_ExecutableCodegenHeaderMixin"]

