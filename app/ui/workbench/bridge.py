"""内置 Web Workbench（UI 工作台）桥接实现（不依赖 PyQt6）。

目标：
- 通过浏览器承载“界面控件组/布局/模板”的查看与 HTML 导入；
- 提供与 Workbench 前端约定一致的 `/api/ui_converter/*` 接口（由 `http_server.py` 路由到本类方法）。

约束：
- 不导入 PyQt6（由 UI 侧负责打开浏览器 URL）；
- 不吞错：关键错误直接抛出，便于定位问题；
- 写盘应走 PackageController 的增量保存链路（mark_* + save_dirty_blocks）。
"""

from __future__ import annotations

from pathlib import Path

from app.cli.ui_variable_validator import validate_ui_source_dir
from app.runtime.services.ui_workbench.base_gil_cache import (
    load_base_gil_cache as load_base_gil_cache_service,
    save_base_gil_cache as save_base_gil_cache_service,
)
from app.runtime.services.ui_workbench.types import ImportBundleResult, ImportResult
from app.runtime.services.ui_workbench.ui_import_api import (
    import_layout_from_bundle_payload as import_layout_from_bundle_payload_service,
    import_layout_from_template_payload as import_layout_from_template_payload_service,
)
from app.runtime.services.ui_workbench.ui_catalog_api import (
    build_ui_catalog_payload as build_ui_catalog_payload_service,
    get_ui_layout_payload as get_ui_layout_payload_service,
    get_ui_template_payload as get_ui_template_payload_service,
)
from app.runtime.services.ui_workbench.ui_source_api import (
    build_ui_source_catalog_payload as build_ui_source_catalog_payload_service,
    read_ui_source_payload as read_ui_source_payload_service,
    resolve_ui_source_path as resolve_ui_source_path_service,
)
from app.runtime.services.ui_workbench.utils import read_json, write_json
from app.runtime.services.ui_workbench.variable_defaults import (
    apply_variable_defaults_to_registry,
)
from app.ui.workbench.http_server import _WorkbenchHttpServer
from engine.resources.level_variable_schema_view import (
    invalidate_default_level_variable_cache,
)

__all__ = [
    "UiWorkbenchBridge",
]


class UiWorkbenchBridge:
    """将主程序当前上下文（PackageController/PackageView）暴露给 Web Workbench。"""

    def __init__(self, *, workspace_root: Path, workbench_dir: Path) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        self._workbench_dir = Path(workbench_dir).resolve()
        self._main_window: object | None = None
        self._server: _WorkbenchHttpServer | None = None

    # --------------------------------------------------------------------- life-cycle
    def attach_main_window(self, main_window: object) -> None:
        self._main_window = main_window

    def ensure_server_running(self) -> None:
        if self._server is not None:
            return
        self._server = _WorkbenchHttpServer(workbench_dir=self._workbench_dir, bridge=self)
        self._server.start()

    def get_workbench_url(self) -> str:
        self.ensure_server_running()
        if self._server is None:
            raise RuntimeError("Workbench server 未启动")
        # Workbench 页面已下线，所有入口统一导向预览页。
        return f"http://127.0.0.1:{self._server.port}/ui_app_ui_preview.html"

    def get_ui_preview_url(self) -> str:
        """UI 控件组预览页（布局/模板浏览与预览）。"""
        self.ensure_server_running()
        if self._server is None:
            raise RuntimeError("Workbench server 未启动")
        return f"http://127.0.0.1:{self._server.port}/ui_app_ui_preview.html"

    # --------------------------------------------------------------------- api payloads
    def get_status_payload(self) -> dict:
        main_window = self._main_window
        package_controller = (
            getattr(main_window, "package_controller", None) if main_window is not None else None
        )
        current_package_id = (
            getattr(package_controller, "current_package_id", None) if package_controller is not None else None
        )
        current_package = (
            getattr(package_controller, "current_package", None) if package_controller is not None else None
        )
        current_package_name = getattr(current_package, "name", "") if current_package is not None else ""

        package_id_text = str(current_package_id or "")
        package_name_text = str(current_package_name or "")
        is_global_view = package_id_text == "global_view"

        return {
            "ok": True,
            "connected": True,
            "workspace_root": str(self._workspace_root),
            "workbench_dir": str(self._workbench_dir),
            "current_package_id": package_id_text,
            "current_package_name": package_name_text,
            "is_global_view": is_global_view,
            # 预览页 UX：用于“设为基底：当前沙箱”按钮（若为空则按钮禁用）
            "suggested_base_gil_path": "",
            "suggested_gil_paths": [],
            # 能力声明：Web 前端可据此展示/隐藏按钮或给出解释（当前仍以“存在 API=connected”作为主判断）
            "features": {
                "builtin_workbench": True,
                "ui_source_api": True,
                "ui_catalog_api": True,
                "ui_import_layout_api": True,
                "fix_ui_variables_api": True,
                # UGC 写回能力属于私有工具链；内置 Workbench 不提供（前端会显示明确错误提示）
                "export_gil": False,
                "export_gia": False,
            },
        }

    def get_ui_source_catalog_payload(self) -> dict:
        """返回 UI源码（HTML）清单：项目 + 共享。"""
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("主窗口未绑定，无法读取 UI源码 清单")
        package_controller = getattr(main_window, "package_controller", None)
        if package_controller is None:
            raise RuntimeError("主窗口缺少 package_controller，无法读取 UI源码 清单")
        current_package_id = str(getattr(package_controller, "current_package_id", "") or "").strip()
        return build_ui_source_catalog_payload_service(
            workspace_root=self._workspace_root,
            current_package_id=current_package_id,
        )

    def resolve_ui_source_path(self, *, scope: str, rel_path: str) -> Path:
        """将 Web 侧的 (scope, rel_path) 解析为磁盘路径。"""
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("主窗口未绑定，无法读取 UI源码")
        package_controller = getattr(main_window, "package_controller", None)
        if package_controller is None:
            raise RuntimeError("主窗口缺少 package_controller，无法读取 UI源码")
        current_package_id = str(getattr(package_controller, "current_package_id", "") or "").strip()
        return resolve_ui_source_path_service(
            workspace_root=self._workspace_root,
            scope=scope,
            rel_path=rel_path,
            current_package_id=current_package_id,
        )

    def _resolve_ui_source_path(self, *, scope: str, rel_path: str) -> Path:
        # 兼容内部旧调用：优先使用公开方法 resolve_ui_source_path
        return self.resolve_ui_source_path(scope=scope, rel_path=rel_path)

    def read_ui_source_payload(self, *, scope: str, rel_path: str) -> dict:
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("主窗口未绑定，无法读取 UI源码")
        package_controller = getattr(main_window, "package_controller", None)
        if package_controller is None:
            raise RuntimeError("主窗口缺少 package_controller，无法读取 UI源码")
        current_package_id = str(getattr(package_controller, "current_package_id", "") or "").strip()
        return read_ui_source_payload_service(
            workspace_root=self._workspace_root,
            scope=scope,
            rel_path=rel_path,
            current_package_id=current_package_id,
        )

    def _get_ui_workbench_cache_dir(self) -> Path:
        # NOTE: 实现下沉到 `app.runtime.services.ui_workbench.base_gil_cache.get_ui_workbench_cache_dir`
        from app.runtime.services.ui_workbench.base_gil_cache import get_ui_workbench_cache_dir

        return get_ui_workbench_cache_dir(workspace_root=self._workspace_root)

    def save_base_gil_cache(self, *, file_name: str, last_modified: int, content: bytes) -> None:
        save_base_gil_cache_service(
            workspace_root=self._workspace_root,
            file_name=file_name,
            last_modified=last_modified,
            content=content,
        )

    def load_base_gil_cache(self) -> tuple[str, int, bytes] | None:
        return load_base_gil_cache_service(workspace_root=self._workspace_root)

    def get_ui_catalog_payload(self) -> dict:
        """返回当前项目存档的 UI 布局/模板清单（用于 Web 侧浏览与预览）。"""
        current_package_id, _package, management = self._get_current_management_or_raise()
        return build_ui_catalog_payload_service(current_package_id=current_package_id, management=management)

    def get_ui_layout_payload(self, layout_id: str) -> dict:
        current_package_id, _package, management = self._get_current_management_or_raise()
        return get_ui_layout_payload_service(
            current_package_id=current_package_id,
            management=management,
            layout_id=layout_id,
        )

    def get_ui_template_payload(self, template_id: str) -> dict:
        current_package_id, _package, management = self._get_current_management_or_raise()
        return get_ui_template_payload_service(
            current_package_id=current_package_id,
            management=management,
            template_id=template_id,
        )

    def fix_ui_variables_from_ui_source(self, *, dry_run: bool) -> dict:
        """根据当前项目存档的 管理配置/UI源码 扫描占位符并输出校验结果（只读）。

        说明：
        - 方案 S：自定义变量只允许在 `自定义变量注册表.py` 统一定义；UI/节点图只做引用与校验；
        - 因此该接口不再写盘、不生成任何变量文件，也不修改玩家模板；
        - `dry_run` 参数仅为兼容前端旧调用保留（始终只读）。
        """
        current_package_id, _package, _management = self._get_current_management_or_raise()
        ui_source_dir = (
            self._workspace_root
            / "assets"
            / "资源库"
            / "项目存档"
            / current_package_id
            / "管理配置"
            / "UI源码"
        )
        allowed_scopes = {"ps", "lv", "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8"}
        issues = validate_ui_source_dir(
            ui_source_dir,
            allowed_scopes=allowed_scopes,
            workspace_root=self._workspace_root,
            package_id=current_package_id,
        )
        return {
            "ok": not bool(issues),
            "current_package_id": current_package_id,
            "dry_run": bool(dry_run),
            "issue_count": len(issues),
            "issues": [
                {
                    "path": str(i.file_path),
                    "line": int(i.line),
                    "column": int(i.column),
                    "token": str(i.token),
                    "expr": str(i.raw_expr),
                    "message": str(i.message),
                }
                for i in issues
            ],
        }

    def import_variable_defaults_to_current_project(
        self,
        *,
        source_rel_path: str,
        variable_defaults: dict,
    ) -> dict:
        """
        将前端解析出的 `variable_defaults` 写回当前项目的 `自定义变量注册表.py`：
        - lv.* -> owner="level" 的声明 default_value
        - ps.* -> owner="player" 的声明 default_value

        注意：
        - 仅处理 lv/ps 前缀；其它（如 关卡./玩家自身.）不在此处导入（它们属于 .gil 的实体自定义变量范畴）。
        - 不再生成 UI_*_网页默认值.py；registry 作为单文件真源。
        """
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("主窗口未绑定，无法导入变量默认值。")
        package_controller = getattr(main_window, "package_controller", None)
        if package_controller is None:
            raise RuntimeError("主窗口缺少 package_controller，无法导入变量默认值。")
        current_package_id = str(getattr(package_controller, "current_package_id", "") or "")
        report = apply_variable_defaults_to_registry(
            workspace_root=self._workspace_root,
            package_id=current_package_id,
            source_rel_path=str(source_rel_path or ""),
            variable_defaults=variable_defaults,
        )
        invalidate_default_level_variable_cache()
        return report

    # --------------------------------------------------------------------- import
    def import_layout_from_template_payload(self, *, layout_name: str, template_payload: dict) -> ImportResult:
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("主窗口未绑定，无法导入")

        package_controller = getattr(main_window, "package_controller", None)
        if package_controller is None:
            raise RuntimeError("主窗口缺少 package_controller，无法导入")

        current_package_id = str(getattr(package_controller, "current_package_id", "") or "")
        if not current_package_id or current_package_id == "global_view":
            raise RuntimeError("请先切换到某个【项目存档】再执行导入（当前为 <共享资源>/未选择）。")

        package = getattr(package_controller, "current_package", None)
        if package is None:
            raise RuntimeError("当前项目存档为空，无法导入")

        management = getattr(package, "management", None)
        if management is None:
            raise RuntimeError("当前项目存档缺少 management，无法导入")

        resource_manager = getattr(package_controller, "resource_manager", None)
        if resource_manager is None:
            raise RuntimeError("package_controller 缺少 resource_manager，无法导入")

        result = import_layout_from_template_payload_service(
            current_package_id=current_package_id,
            management=management,
            resource_manager=resource_manager,
            layout_name=layout_name,
            template_payload=template_payload,
        )

        # 触发增量落盘：只同步 ui_layouts + ui_widget_templates
        mark_management_dirty = getattr(package_controller, "mark_management_dirty", None)
        if callable(mark_management_dirty):
            mark_management_dirty({"ui_layouts", "ui_widget_templates"})
        mark_index_dirty = getattr(package_controller, "mark_index_dirty", None)
        if callable(mark_index_dirty):
            mark_index_dirty()

        save_dirty_blocks = getattr(package_controller, "save_dirty_blocks", None)
        if callable(save_dirty_blocks):
            save_dirty_blocks()

        return result

    def import_layout_from_bundle_payload(self, *, layout_name: str, bundle_payload: dict) -> ImportBundleResult:
        """导入 Workbench 导出的 bundle（UILayout + 多个 UIControlGroupTemplate）。

        约定：
        - Web 侧负责“HTML → 扁平层 → widgets → 打组 → bundle”；
        - Python 侧负责：生成全库唯一 ID、写入 management、触发增量落盘与 UI 刷新。
        """
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("主窗口未绑定，无法导入")

        package_controller = getattr(main_window, "package_controller", None)
        if package_controller is None:
            raise RuntimeError("主窗口缺少 package_controller，无法导入")

        current_package_id = str(getattr(package_controller, "current_package_id", "") or "")
        if not current_package_id or current_package_id == "global_view":
            raise RuntimeError("请先切换到某个【项目存档】再执行导入（当前为 <共享资源>/未选择）。")

        package = getattr(package_controller, "current_package", None)
        if package is None:
            raise RuntimeError("当前项目存档为空，无法导入")

        management = getattr(package, "management", None)
        if management is None:
            raise RuntimeError("当前项目存档缺少 management，无法导入")

        resource_manager = getattr(package_controller, "resource_manager", None)
        if resource_manager is None:
            raise RuntimeError("package_controller 缺少 resource_manager，无法导入")

        result = import_layout_from_bundle_payload_service(
            current_package_id=current_package_id,
            management=management,
            resource_manager=resource_manager,
            layout_name=layout_name,
            bundle_payload=bundle_payload,
        )

        # 触发增量落盘：只同步 ui_layouts + ui_widget_templates
        mark_management_dirty = getattr(package_controller, "mark_management_dirty", None)
        if callable(mark_management_dirty):
            mark_management_dirty({"ui_layouts", "ui_widget_templates"})
        mark_index_dirty = getattr(package_controller, "mark_index_dirty", None)
        if callable(mark_index_dirty):
            mark_index_dirty()

        save_dirty_blocks = getattr(package_controller, "save_dirty_blocks", None)
        if callable(save_dirty_blocks):
            save_dirty_blocks()

        return result

    def _get_current_management_or_raise(self) -> tuple[str, object, object]:
        """返回 (current_package_id, package, management)。

        约定：不吞错，缺失上下文直接抛出，便于定位问题。
        """
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("主窗口未绑定，无法读取 UI 控件组数据")

        package_controller = getattr(main_window, "package_controller", None)
        if package_controller is None:
            raise RuntimeError("主窗口缺少 package_controller，无法读取 UI 控件组数据")

        current_package_id = str(getattr(package_controller, "current_package_id", "") or "")
        if not current_package_id or current_package_id == "global_view":
            raise RuntimeError("请先切换到某个【项目存档】再查看/导入（当前为 <共享资源>/未选择）。")

        package = getattr(package_controller, "current_package", None)
        if package is None:
            raise RuntimeError("当前项目存档为空，无法读取 UI 控件组数据")

        management = getattr(package, "management", None)
        if management is None:
            raise RuntimeError("当前项目存档缺少 management，无法读取 UI 控件组数据")

        return current_package_id, package, management

