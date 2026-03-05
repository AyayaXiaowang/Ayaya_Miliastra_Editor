from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict

import pprint
import tokenize

from engine.graph.utils.ast_utils import (
    NOT_EXTRACTABLE,
    clear_module_constants_context,
    collect_module_constants,
    extract_constant_value,
    set_module_constants_context,
)
from engine.utils.resource_library_layout import discover_scoped_resource_root_directories
from engine.utils.workspace import (
    get_injected_workspace_root_or_none,
    looks_like_workspace_root,
    resolve_workspace_root,
)


def _find_module_assignment_value(tree: ast.Module, name: str) -> ast.expr | None:
    """在模块顶层寻找对 name 的赋值表达式节点（支持 Assign/AnnAssign）。"""
    want = str(name or "").strip()
    if not want:
        return None

    for stmt in list(getattr(tree, "body", []) or []):
        if isinstance(stmt, ast.Assign):
            targets = list(getattr(stmt, "targets", []) or [])
            for target in targets:
                if isinstance(target, ast.Name) and target.id == want:
                    return stmt.value
        elif isinstance(stmt, ast.AnnAssign):
            target = getattr(stmt, "target", None)
            if isinstance(target, ast.Name) and target.id == want:
                return getattr(stmt, "value", None)

    return None


def _try_extract_save_point_id_and_payload_from_code(py_path: Path) -> tuple[str | None, dict | None]:
    """从局内存档模板代码资源文件中静态提取 (SAVE_POINT_ID, SAVE_POINT_PAYLOAD)。

    约定：该方法**不执行**模块顶层代码；仅支持静态可提取的常量赋值：
    - `SAVE_POINT_ID = "..."`
    - `SAVE_POINT_PAYLOAD = { ... }`
    - payload 内允许引用同模块内已声明的常量（例如 `SAVE_POINT_ID`）。
    """
    if not py_path.is_file():
        return None, None

    with tokenize.open(str(py_path)) as f:
        source_text = f.read()

    tree = ast.parse(source_text, filename=str(py_path))
    constants = collect_module_constants(tree)
    set_module_constants_context(constants)

    id_expr = _find_module_assignment_value(tree, "SAVE_POINT_ID")
    if id_expr is None:
        clear_module_constants_context()
        return None, None
    id_value = extract_constant_value(id_expr)
    if id_value is NOT_EXTRACTABLE or not isinstance(id_value, str) or not id_value:
        clear_module_constants_context()
        return None, None

    payload_expr = _find_module_assignment_value(tree, "SAVE_POINT_PAYLOAD")
    if payload_expr is None:
        clear_module_constants_context()
        return None, None
    payload_value = extract_constant_value(payload_expr)
    clear_module_constants_context()

    if payload_value is NOT_EXTRACTABLE or not isinstance(payload_value, dict):
        return None, None
    return str(id_value), dict(payload_value)


class IngameSaveTemplateSchemaService:
    """局内存档模板的代码级 Schema 载入服务。

    设计目标：
    - 从资产库中的 Python 模块加载所有局内存档模板定义；
    - 提供只读的 {template_id: payload} 视图，供引擎与 UI 使用；
    - 不再依赖 JSON 形式的 SAVE_POINT 资源存放模板本体。

    约定：
    - 根目录：assets/资源库/管理配置/局内存档管理
    - 每个 Python 模块导出：
      - SAVE_POINT_ID: str
      - SAVE_POINT_PAYLOAD: dict
        - 至少包含 template_id 与 template_name 字段；
        - save_point_id 建议与 template_id 相同，用于与 ResourceType.SAVE_POINT 的
          命名约定保持直观一致；
        - 可选字段 is_default_template: bool，用于表达“当前工程默认/主模板”状态。
    """

    def __init__(self) -> None:
        self._template_files: Dict[str, Path] = {}

    def _get_workspace_root(self) -> Path:
        injected_root = get_injected_workspace_root_or_none()
        if injected_root is not None and looks_like_workspace_root(injected_root):
            return injected_root
        return resolve_workspace_root(start_paths=[Path(__file__).resolve()])

    def load_all_templates_from_code(self, *, active_package_id: str | None = None) -> Dict[str, Dict]:
        """从代码资源中加载所有局内存档模板，返回 {template_id: payload}。"""
        workspace_root = self._get_workspace_root()
        resource_library_root = workspace_root / "assets" / "资源库"
        resource_roots = discover_scoped_resource_root_directories(
            resource_library_root,
            active_package_id=active_package_id,
        )
        base_directories = [root / "管理配置" / "局内存档管理" for root in resource_roots]

        results: Dict[str, Dict] = {}
        self._template_files = {}

        for base_directory in base_directories:
            if not base_directory.is_dir():
                continue

            for python_path in base_directory.rglob("*.py"):
                # 允许在目录中放置校验或工具脚本（如 `校验局内存档管理.py`），这些脚本不参与模板 Schema 聚合。
                if "校验" in python_path.stem:
                    continue
                template_id_value, payload_value = _try_extract_save_point_id_and_payload_from_code(python_path)

                if not isinstance(template_id_value, str) or not template_id_value:
                    raise ValueError(f"无效的 SAVE_POINT_ID（{python_path}）")
                if not isinstance(payload_value, dict):
                    raise ValueError(f"无效的 SAVE_POINT_PAYLOAD（{python_path}）")

                template_id = template_id_value
                if template_id in results:
                    raise ValueError(f"重复的局内存档模板 ID：{template_id}")

                # 复制一份 payload，避免外部修改影响模块常量
                template_payload = dict(payload_value)

                # 归一化常见字段，保证下游视图在字段缺失时仍有稳定形态。
                raw_template_id = template_payload.get("template_id", template_id)
                normalized_template_id = str(raw_template_id).strip() or template_id
                template_payload["template_id"] = normalized_template_id

                save_point_id_text = str(
                    template_payload.get("save_point_id", normalized_template_id)
                ).strip()
                if not save_point_id_text:
                    save_point_id_text = normalized_template_id
                template_payload["save_point_id"] = save_point_id_text

                raw_template_name = template_payload.get("template_name")
                if isinstance(raw_template_name, str) and raw_template_name.strip():
                    template_name_text = raw_template_name.strip()
                else:
                    template_name_text = normalized_template_id
                template_payload["template_name"] = template_name_text

                raw_save_point_name = template_payload.get("save_point_name")
                if not isinstance(raw_save_point_name, str) or not raw_save_point_name.strip():
                    template_payload["save_point_name"] = template_name_text

                results[normalized_template_id] = template_payload
                self._template_files[normalized_template_id] = python_path

        return results

    def get_template_file_path(self, template_id: str) -> Path | None:
        return self._template_files.get(template_id)


class IngameSaveTemplateSchemaView:
    """局内存档模板 Schema 聚合视图（进程内缓存，只读）。"""

    def __init__(
        self,
        schema_service: IngameSaveTemplateSchemaService | None = None,
    ) -> None:
        self._schema_service = schema_service or IngameSaveTemplateSchemaService()
        # 当前作用域：None 表示仅共享根；str 表示共享根 + 指定项目存档根。
        self._active_package_id: str | None = None
        self._templates: Dict[str, Dict] | None = None

    def set_active_package_id(self, package_id: str | None) -> None:
        """设置局内存档模板 Schema 的项目存档作用域。"""
        normalized = str(package_id or "").strip()
        if normalized in {"global_view", "unclassified_view"}:
            normalized = ""
        normalized_or_none: str | None = normalized or None
        if normalized_or_none == self._active_package_id:
            return
        self._active_package_id = normalized_or_none
        self.invalidate_cache()

    def get_all_templates(self) -> Dict[str, Dict]:
        """返回 {template_id: payload}，payload 为模板定义原始字典的副本。"""
        if self._templates is None:
            self._templates = self._schema_service.load_all_templates_from_code(
                active_package_id=self._active_package_id
            )
        return self._templates

    def get_template(self, template_id: str) -> Dict | None:
        """按 ID 获取单个局内存档模板定义。"""
        all_templates = self.get_all_templates()
        return all_templates.get(template_id)

    def get_template_file_path(self, template_id: str) -> Path | None:
        """按模板 ID 获取对应的 Python 模块路径（若存在）。"""
        # 确保已加载一次，以构建文件路径映射。
        self.get_all_templates()
        return self._schema_service.get_template_file_path(template_id)

    def invalidate_cache(self) -> None:
        """使缓存失效，下次访问时重新加载。"""
        self._templates = None


_default_ingame_save_template_schema_view: IngameSaveTemplateSchemaView | None = None


def get_default_ingame_save_template_schema_view() -> IngameSaveTemplateSchemaView:
    """获取进程级默认 IngameSaveTemplateSchemaView 实例（带缓存）。"""
    global _default_ingame_save_template_schema_view
    if _default_ingame_save_template_schema_view is None:
        _default_ingame_save_template_schema_view = IngameSaveTemplateSchemaView()
    return _default_ingame_save_template_schema_view


def set_default_ingame_save_template_schema_view_active_package_id(package_id: str | None) -> None:
    """同步默认 IngameSaveTemplateSchemaView 的作用域（共享根 / 共享+当前存档）。"""
    schema_view = get_default_ingame_save_template_schema_view()
    set_active = getattr(schema_view, "set_active_package_id", None)
    if callable(set_active):
        set_active(package_id)


def invalidate_default_ingame_save_template_cache() -> None:
    """使默认视图的缓存失效。"""
    global _default_ingame_save_template_schema_view
    if _default_ingame_save_template_schema_view is not None:
        _default_ingame_save_template_schema_view.invalidate_cache()


def update_default_template_id(default_template_id: str | None) -> None:
    """根据给定模板 ID 更新各局内存档模板中的 is_default_template 状态。

    - 若 default_template_id 为空或无效，则所有模板的 is_default_template 均为 False。
    - 若 default_template_id 对应某个模板，则仅该模板的 is_default_template 为 True。
    """
    schema_view = get_default_ingame_save_template_schema_view()
    all_templates = schema_view.get_all_templates()

    normalized_default_id: str | None = None
    if default_template_id is not None:
        candidate_id = str(default_template_id).strip()
        if candidate_id and candidate_id in all_templates:
            normalized_default_id = candidate_id

    for template_id, payload in all_templates.items():
        file_path = schema_view.get_template_file_path(template_id)
        if file_path is None or not file_path.is_file():
            continue

        template_payload = dict(payload)
        template_payload["template_id"] = template_id
        if not str(template_payload.get("save_point_id", "")).strip():
            template_payload["save_point_id"] = template_id

        is_default = normalized_default_id is not None and template_id == normalized_default_id
        template_payload["is_default_template"] = is_default

        source_lines = [
            "from __future__ import annotations",
            "",
            "from typing import Any, Dict",
            "",
            "",
            f'SAVE_POINT_ID = "{template_id}"',
            "",
            "",
            "SAVE_POINT_PAYLOAD: Dict[str, Any] = "
            + pprint.pformat(template_payload, width=88, sort_dicts=False),
            "",
            "",
        ]
        source_text = "\n".join(source_lines)
        file_path.write_text(source_text, encoding="utf-8")

    # 文件已写回：使 schema view 缓存失效，避免后续仍读取旧模板状态。
    schema_view.invalidate_cache()

