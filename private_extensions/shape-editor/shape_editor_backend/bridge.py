from __future__ import annotations

import os
import re
import webbrowser
from pathlib import Path

from engine.utils.logging.logger import log_info, log_warn

from .export_gia import export_canvas_payload_to_gia
from .http_server import _ShapeEditorHttpServer
from .project_persistence import (
    create_blank_entity_in_project,
    delete_shape_editor_entity_placement,
    duplicate_shape_editor_entity_placement,
    ensure_canvas_persisted_in_project,
    list_project_entity_placements,
    load_canvas_payload_from_project,
    load_shape_editor_pixel_workbench_state,
    load_shape_editor_project_state,
    rename_shape_editor_entity_placement,
    read_project_entity_placement,
    save_shape_editor_pixel_workbench_state,
    save_shape_editor_project_state,
    save_as_new_entity_in_project,
)
from .settings import get_shape_editor_settings_file_path, load_shape_editor_settings, save_shape_editor_settings


_WIN_ILLEGAL_FILE_CHARS_RE = re.compile(r'[\\/:*?"<>|]+')


def _sanitize_file_stem_part(text: str) -> str:
    """
    Windows 文件名安全化（保证可落盘 + 可读）。
    """
    t = str(text or "").strip()
    if t == "":
        return "未命名"
    t = _WIN_ILLEGAL_FILE_CHARS_RE.sub("_", t)
    t = t.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    while "  " in t:
        t = t.replace("  ", " ")
    t = t.strip(" .")
    return t or "未命名"


def _infer_seq_from_placement_stem(stem: str) -> int:
    """
    序号来源（稳定、可预测）：
    - shape_editor_entity_001 -> 1
    - shape_editor_canvas_instance -> 0
    - 其他：取末尾数字；没有则 0
    """
    s = str(stem or "").strip()
    if s == "" or s == "shape_editor_canvas_instance":
        return 0
    m = re.search(r"shape_editor_entity_(\d+)$", s)
    if m:
        return int(m.group(1))
    m2 = re.search(r"(\d+)$", s)
    if m2:
        return int(m2.group(1))
    return 0


class _ShapeEditorBridge:
    def __init__(self, *, workspace_root: Path, tool_dir: Path) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        self._tool_dir = Path(tool_dir).resolve()
        self._main_window: object | None = None
        self._server: object | None = None

    # --------------------------------------------------------------------- life-cycle
    def attach_main_window(self, main_window: object) -> None:
        self._main_window = main_window

    def install_entrypoints(self) -> None:
        if self._main_window is None:
            return
        self._ensure_server_running()
        self._inject_left_nav_button()
        self._inject_menu_actions()

    # --------------------------------------------------------------------- server / urls
    def _ensure_server_running(self) -> None:
        if self._server is not None:
            return
        self._server = _ShapeEditorHttpServer(workspace_root=self._workspace_root, bridge=self)
        self._server.start()

    def _get_editor_url(self) -> str:
        self._ensure_server_running()
        if self._server is None:
            raise RuntimeError("shape editor server 未启动")
        port = int(getattr(self._server, "port"))
        # 以 workspace_root 作为静态根目录，确保 `./common.css` 等相对路径可正常加载
        return f"http://127.0.0.1:{port}/private_extensions/shape-editor/index.html"

    # --------------------------------------------------------------------- open browser
    @staticmethod
    def _open_url_or_raise(*, url: str, purpose: str) -> None:
        url_text = str(url or "").strip()
        purpose_text = str(purpose or "").strip() or "open_url"
        if not url_text:
            raise ValueError(f"URL 为空，无法打开：purpose={purpose_text}")

        log_info("[SHAPE-EDITOR] open: purpose={} url={}", purpose_text, url_text)
        opened = webbrowser.open(url_text, new=2)
        if opened:
            return
        log_warn("[SHAPE-EDITOR] webbrowser.open returned False: purpose={} url={}", purpose_text, url_text)
        if hasattr(os, "startfile"):
            os.startfile(url_text)  # type: ignore[attr-defined]
            return
        raise RuntimeError(f"webbrowser.open returned False and os.startfile unavailable: {url_text}")

    def open_editor_in_browser(self) -> None:
        self._open_url_or_raise(url=self._get_editor_url(), purpose="shape_editor")

    # --------------------------------------------------------------------- API: status/export
    def get_status_payload(self) -> dict:
        main_window = self._main_window
        package_controller = getattr(main_window, "package_controller", None) if main_window is not None else None
        current_package_id = getattr(package_controller, "current_package_id", None) if package_controller is not None else None
        package_id_text = str(current_package_id or "").strip()

        settings_path = get_shape_editor_settings_file_path()
        return {
            "ok": True,
            "connected": True,
            "package_id": package_id_text,
            "editor_url": self._get_editor_url(),
            "settings_file": str(settings_path),
        }

    def export_gia_from_canvas_payload(self, payload: dict) -> dict:
        # backward compat: keep old endpoint as "export entity"
        return self.export_gia_entity_from_canvas_payload(payload)

    def export_gia_entity_from_canvas_payload(self, payload: dict) -> dict:
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("main_window not attached")
        package_controller = getattr(main_window, "package_controller", None)
        current_package_id = getattr(package_controller, "current_package_id", None) if package_controller is not None else None
        package_id_text = str(current_package_id or "").strip()

        settings_obj = load_shape_editor_settings()

        # 项目级持久化：把画布同步写入当前项目存档的“实体摆放”（空实体 + 装饰物组 + 原始画布JSON）
        app_state = getattr(main_window, "app_state", None)
        resource_manager = getattr(app_state, "resource_manager", None) if app_state is not None else None
        resource_library_dir = getattr(resource_manager, "resource_library_dir", None) if resource_manager is not None else None
        if not isinstance(resource_library_dir, Path):
            raise RuntimeError("无法定位 resource_library_dir，无法写入项目级画布数据")
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        target_rel_path = str(meta.get("target_rel_path") or "").strip() or None

        persisted = ensure_canvas_persisted_in_project(
            workspace_root=self._workspace_root,
            resource_library_dir=Path(resource_library_dir),
            package_id=package_id_text,
            canvas_payload=payload,
            settings_obj=settings_obj,
            target_rel_path=target_rel_path,
            # 同一实体反复导出：应覆盖同一个导出文件，而不是序号递增生成多个文件
            bump_export_seq=False,
        )

        # 导出命名：
        # - 文件名：直接使用“实体名字”（instance_name）作为文件名 stem（同名会覆盖）
        # - entity_name：用于 GIA 内部显示名，保持与实体名字一致
        instance_name = str(persisted.get("instance_name") or "拼贴画画布").strip() or "拼贴画画布"
        name_part = _sanitize_file_stem_part(instance_name)
        stable_output_stem = name_part
        entity_name = instance_name

        result = export_canvas_payload_to_gia(
            package_id=package_id_text,
            canvas_payload=payload,
            settings_obj=settings_obj,
            # 输出文件名使用稳定命名（用户仍可手动传 output_stem 覆盖）
            output_file_stem=str(payload.get("output_stem") or "").strip() or stable_output_stem,
            entity_name=entity_name,
        )
        result["export_kind"] = "entity"
        if isinstance(persisted.get("reference_images"), list):
            result["reference_images"] = persisted.get("reference_images")
        return result

    def export_gia_template_from_canvas_payload(self, payload: dict) -> dict:
        """
        导出为“元件 GIA”（单元件结构）：使用 settings.template_base_gia_path 作为 base。
        """
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("main_window not attached")
        package_controller = getattr(main_window, "package_controller", None)
        current_package_id = getattr(package_controller, "current_package_id", None) if package_controller is not None else None
        package_id_text = str(current_package_id or "").strip()

        settings_obj = load_shape_editor_settings()

        base_text = str(settings_obj.template_base_gia_path or "").strip()
        if base_text == "":
            settings_path = get_shape_editor_settings_file_path()
            return {
                "ok": False,
                "export_kind": "template",
                "error": f"未配置 template_base_gia_path（导出为元件需要）：请先编辑 {str(settings_path)!r}",
            }
        base_path = Path(base_text).expanduser().resolve()
        if base_path.suffix.lower() != ".gia":
            return {
                "ok": False,
                "export_kind": "template",
                "error": f"template_base_gia_path 必须是 .gia 文件：{str(base_path)!r}",
            }
        if not base_path.is_file():
            return {
                "ok": False,
                "export_kind": "template",
                "error": f"未找到 template_base_gia：{str(base_path)!r}",
            }

        app_state = getattr(main_window, "app_state", None)
        resource_manager = getattr(app_state, "resource_manager", None) if app_state is not None else None
        resource_library_dir = getattr(resource_manager, "resource_library_dir", None) if resource_manager is not None else None
        if not isinstance(resource_library_dir, Path):
            raise RuntimeError("无法定位 resource_library_dir，无法写入项目级画布数据")

        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        target_rel_path = str(meta.get("target_rel_path") or "").strip() or None

        persisted = ensure_canvas_persisted_in_project(
            workspace_root=self._workspace_root,
            resource_library_dir=Path(resource_library_dir),
            package_id=package_id_text,
            canvas_payload=payload,
            settings_obj=settings_obj,
            target_rel_path=target_rel_path,
            bump_export_seq=False,
        )

        instance_name = str(persisted.get("instance_name") or "拼贴画画布").strip() or "拼贴画画布"
        name_part = _sanitize_file_stem_part(instance_name)
        stable_output_stem = name_part
        entity_name = instance_name

        # 元件导出：单元件结构（Root.field_1 为 dict + Root.field_2 accessories）
        # base_gia_path 应为用户提供的“装饰物元件.gia”一类样本。
        result = export_canvas_payload_to_gia(
            package_id=package_id_text,
            canvas_payload=payload,
            settings_obj=settings_obj,
            base_gia_path=base_path,
            output_file_stem=str(payload.get("output_stem") or "").strip() or stable_output_stem,
            entity_name=entity_name,
        )
        result["export_kind"] = "template"
        if isinstance(persisted.get("reference_images"), list):
            result["reference_images"] = persisted.get("reference_images")
        return result

    def load_project_canvas_payload(self) -> dict:
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("main_window not attached")
        package_controller = getattr(main_window, "package_controller", None)
        current_package_id = getattr(package_controller, "current_package_id", None) if package_controller is not None else None
        package_id_text = str(current_package_id or "").strip()

        app_state = getattr(main_window, "app_state", None)
        resource_manager = getattr(app_state, "resource_manager", None) if app_state is not None else None
        resource_library_dir = getattr(resource_manager, "resource_library_dir", None) if resource_manager is not None else None
        if not isinstance(resource_library_dir, Path):
            raise RuntimeError("无法定位 resource_library_dir")

        return load_canvas_payload_from_project(
            resource_library_dir=Path(resource_library_dir),
            package_id=package_id_text,
        )

    def save_project_canvas_payload(self, payload: dict) -> dict:
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("main_window not attached")
        package_controller = getattr(main_window, "package_controller", None)
        current_package_id = getattr(package_controller, "current_package_id", None) if package_controller is not None else None
        package_id_text = str(current_package_id or "").strip()
        if package_id_text == "" or package_id_text == "global_view":
            raise ValueError("必须在“具体项目存档”上下文保存（global_view 不支持）")

        app_state = getattr(main_window, "app_state", None)
        resource_manager = getattr(app_state, "resource_manager", None) if app_state is not None else None
        resource_library_dir = getattr(resource_manager, "resource_library_dir", None) if resource_manager is not None else None
        if not isinstance(resource_library_dir, Path):
            raise RuntimeError("无法定位 resource_library_dir")

        settings_obj = load_shape_editor_settings()
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        target_rel_path = str(meta.get("target_rel_path") or "").strip()
        return ensure_canvas_persisted_in_project(
            workspace_root=self._workspace_root,
            resource_library_dir=Path(resource_library_dir),
            package_id=package_id_text,
            canvas_payload=payload,
            settings_obj=settings_obj,
            target_rel_path=target_rel_path or None,
            bump_export_seq=False,
        )

    def create_blank_entity(self, payload: dict) -> dict:
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("main_window not attached")
        package_controller = getattr(main_window, "package_controller", None)
        current_package_id = getattr(package_controller, "current_package_id", None) if package_controller is not None else None
        package_id_text = str(current_package_id or "").strip()
        if package_id_text == "" or package_id_text == "global_view":
            raise ValueError("必须在“具体项目存档”上下文新建实体（global_view 不支持）")

        app_state = getattr(main_window, "app_state", None)
        resource_manager = getattr(app_state, "resource_manager", None) if app_state is not None else None
        resource_library_dir = getattr(resource_manager, "resource_library_dir", None) if resource_manager is not None else None
        if not isinstance(resource_library_dir, Path):
            raise RuntimeError("无法定位 resource_library_dir")

        settings_obj = load_shape_editor_settings()
        name = str(payload.get("name") or "").strip() or None
        return create_blank_entity_in_project(
            workspace_root=self._workspace_root,
            resource_library_dir=Path(resource_library_dir),
            package_id=package_id_text,
            settings_obj=settings_obj,
            instance_name=name,
        )

    def save_as_new_entity(self, payload: dict) -> dict:
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("main_window not attached")
        package_controller = getattr(main_window, "package_controller", None)
        current_package_id = getattr(package_controller, "current_package_id", None) if package_controller is not None else None
        package_id_text = str(current_package_id or "").strip()
        if package_id_text == "" or package_id_text == "global_view":
            raise ValueError("必须在“具体项目存档”上下文另存实体（global_view 不支持）")

        app_state = getattr(main_window, "app_state", None)
        resource_manager = getattr(app_state, "resource_manager", None) if app_state is not None else None
        resource_library_dir = getattr(resource_manager, "resource_library_dir", None) if resource_manager is not None else None
        if not isinstance(resource_library_dir, Path):
            raise RuntimeError("无法定位 resource_library_dir")

        settings_obj = load_shape_editor_settings()
        name = str(payload.get("name") or "").strip() or None
        canvas_payload = payload.get("canvas_payload")
        if not isinstance(canvas_payload, dict):
            raise ValueError("canvas_payload 必须是 object")

        return save_as_new_entity_in_project(
            workspace_root=self._workspace_root,
            resource_library_dir=Path(resource_library_dir),
            package_id=package_id_text,
            settings_obj=settings_obj,
            canvas_payload=canvas_payload,
            instance_name=name,
        )

    def delete_entity(self, payload: dict) -> dict:
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("main_window not attached")
        package_controller = getattr(main_window, "package_controller", None)
        current_package_id = getattr(package_controller, "current_package_id", None) if package_controller is not None else None
        package_id_text = str(current_package_id or "").strip()
        if package_id_text == "" or package_id_text == "global_view":
            raise ValueError("必须在“具体项目存档”上下文删除实体（global_view 不支持）")

        app_state = getattr(main_window, "app_state", None)
        resource_manager = getattr(app_state, "resource_manager", None) if app_state is not None else None
        resource_library_dir = getattr(resource_manager, "resource_library_dir", None) if resource_manager is not None else None
        if not isinstance(resource_library_dir, Path):
            raise RuntimeError("无法定位 resource_library_dir")

        rel_path = str(payload.get("rel_path") or "").strip()
        return delete_shape_editor_entity_placement(
            resource_library_dir=Path(resource_library_dir),
            package_id=package_id_text,
            rel_path=rel_path,
        )

    def rename_entity(self, payload: dict) -> dict:
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("main_window not attached")
        package_controller = getattr(main_window, "package_controller", None)
        current_package_id = getattr(package_controller, "current_package_id", None) if package_controller is not None else None
        package_id_text = str(current_package_id or "").strip()
        if package_id_text == "" or package_id_text == "global_view":
            raise ValueError("必须在“具体项目存档”上下文重命名实体（global_view 不支持）")

        app_state = getattr(main_window, "app_state", None)
        resource_manager = getattr(app_state, "resource_manager", None) if app_state is not None else None
        resource_library_dir = getattr(resource_manager, "resource_library_dir", None) if resource_manager is not None else None
        if not isinstance(resource_library_dir, Path):
            raise RuntimeError("无法定位 resource_library_dir")

        rel_path = str(payload.get("rel_path") or "").strip()
        name = str(payload.get("name") or "").strip()
        return rename_shape_editor_entity_placement(
            resource_library_dir=Path(resource_library_dir),
            package_id=package_id_text,
            rel_path=rel_path,
            new_name=name,
        )

    def duplicate_entity(self, payload: dict) -> dict:
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("main_window not attached")
        package_controller = getattr(main_window, "package_controller", None)
        current_package_id = getattr(package_controller, "current_package_id", None) if package_controller is not None else None
        package_id_text = str(current_package_id or "").strip()
        if package_id_text == "" or package_id_text == "global_view":
            raise ValueError("必须在“具体项目存档”上下文复制实体（global_view 不支持）")

        app_state = getattr(main_window, "app_state", None)
        resource_manager = getattr(app_state, "resource_manager", None) if app_state is not None else None
        resource_library_dir = getattr(resource_manager, "resource_library_dir", None) if resource_manager is not None else None
        if not isinstance(resource_library_dir, Path):
            raise RuntimeError("无法定位 resource_library_dir")

        rel_path = str(payload.get("rel_path") or "").strip()
        return duplicate_shape_editor_entity_placement(
            resource_library_dir=Path(resource_library_dir),
            package_id=package_id_text,
            rel_path=rel_path,
        )

    def get_project_placements_catalog_payload(self) -> dict:
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("main_window not attached")
        package_controller = getattr(main_window, "package_controller", None)
        current_package_id = getattr(package_controller, "current_package_id", None) if package_controller is not None else None
        package_id_text = str(current_package_id or "").strip()

        app_state = getattr(main_window, "app_state", None)
        resource_manager = getattr(app_state, "resource_manager", None) if app_state is not None else None
        resource_library_dir = getattr(resource_manager, "resource_library_dir", None) if resource_manager is not None else None
        if not isinstance(resource_library_dir, Path):
            raise RuntimeError("无法定位 resource_library_dir")

        settings_obj = load_shape_editor_settings()
        return list_project_entity_placements(
            resource_library_dir=Path(resource_library_dir),
            package_id=package_id_text,
            settings_obj=settings_obj,
        )

    def read_project_placement_payload(self, *, rel_path: str) -> dict:
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("main_window not attached")
        package_controller = getattr(main_window, "package_controller", None)
        current_package_id = getattr(package_controller, "current_package_id", None) if package_controller is not None else None
        package_id_text = str(current_package_id or "").strip()

        app_state = getattr(main_window, "app_state", None)
        resource_manager = getattr(app_state, "resource_manager", None) if app_state is not None else None
        resource_library_dir = getattr(resource_manager, "resource_library_dir", None) if resource_manager is not None else None
        if not isinstance(resource_library_dir, Path):
            raise RuntimeError("无法定位 resource_library_dir")

        settings_obj = load_shape_editor_settings()
        return read_project_entity_placement(
            resource_library_dir=Path(resource_library_dir),
            package_id=package_id_text,
            rel_path=str(rel_path or ""),
            settings_obj=settings_obj,
        )

    def get_project_state_payload(self) -> dict:
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("main_window not attached")
        package_controller = getattr(main_window, "package_controller", None)
        current_package_id = getattr(package_controller, "current_package_id", None) if package_controller is not None else None
        package_id_text = str(current_package_id or "").strip()
        if package_id_text == "" or package_id_text == "global_view":
            raise ValueError("必须在“具体项目存档”上下文读取（global_view 不支持）")

        app_state = getattr(main_window, "app_state", None)
        resource_manager = getattr(app_state, "resource_manager", None) if app_state is not None else None
        resource_library_dir = getattr(resource_manager, "resource_library_dir", None) if resource_manager is not None else None
        if not isinstance(resource_library_dir, Path):
            raise RuntimeError("无法定位 resource_library_dir")

        return load_shape_editor_project_state(
            resource_library_dir=Path(resource_library_dir),
            package_id=package_id_text,
        )

    def set_project_state_payload(self, payload: dict) -> dict:
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("main_window not attached")
        package_controller = getattr(main_window, "package_controller", None)
        current_package_id = getattr(package_controller, "current_package_id", None) if package_controller is not None else None
        package_id_text = str(current_package_id or "").strip()
        if package_id_text == "" or package_id_text == "global_view":
            raise ValueError("必须在“具体项目存档”上下文写入（global_view 不支持）")

        app_state = getattr(main_window, "app_state", None)
        resource_manager = getattr(app_state, "resource_manager", None) if app_state is not None else None
        resource_library_dir = getattr(resource_manager, "resource_library_dir", None) if resource_manager is not None else None
        if not isinstance(resource_library_dir, Path):
            raise RuntimeError("无法定位 resource_library_dir")

        rel_path = str(payload.get("rel_path") or "").strip()
        return save_shape_editor_project_state(
            resource_library_dir=Path(resource_library_dir),
            package_id=package_id_text,
            last_opened_rel_path=rel_path,
        )

    def get_pixel_workbench_state_payload(self) -> dict:
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("main_window not attached")
        package_controller = getattr(main_window, "package_controller", None)
        current_package_id = getattr(package_controller, "current_package_id", None) if package_controller is not None else None
        package_id_text = str(current_package_id or "").strip()
        if package_id_text == "" or package_id_text == "global_view":
            raise ValueError("必须在“具体项目存档”上下文读取（global_view 不支持）")

        app_state = getattr(main_window, "app_state", None)
        resource_manager = getattr(app_state, "resource_manager", None) if app_state is not None else None
        resource_library_dir = getattr(resource_manager, "resource_library_dir", None) if resource_manager is not None else None
        if not isinstance(resource_library_dir, Path):
            raise RuntimeError("无法定位 resource_library_dir")

        return load_shape_editor_pixel_workbench_state(
            resource_library_dir=Path(resource_library_dir),
            package_id=package_id_text,
        )

    def set_pixel_workbench_state_payload(self, payload: dict) -> dict:
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("main_window not attached")
        package_controller = getattr(main_window, "package_controller", None)
        current_package_id = getattr(package_controller, "current_package_id", None) if package_controller is not None else None
        package_id_text = str(current_package_id or "").strip()
        if package_id_text == "" or package_id_text == "global_view":
            raise ValueError("必须在“具体项目存档”上下文写入（global_view 不支持）")

        app_state = getattr(main_window, "app_state", None)
        resource_manager = getattr(app_state, "resource_manager", None) if app_state is not None else None
        resource_library_dir = getattr(resource_manager, "resource_library_dir", None) if resource_manager is not None else None
        if not isinstance(resource_library_dir, Path):
            raise RuntimeError("无法定位 resource_library_dir")

        if not isinstance(payload, dict):
            raise TypeError("payload 必须是 dict")

        return save_shape_editor_pixel_workbench_state(
            workspace_root=self._workspace_root,
            resource_library_dir=Path(resource_library_dir),
            package_id=package_id_text,
            state_payload=payload,
        )

    # --------------------------------------------------------------------- UI injection
    def _inject_left_nav_button(self) -> None:
        main_window = self._main_window
        if main_window is None:
            return
        nav_bar = getattr(main_window, "nav_bar", None)
        if nav_bar is None:
            return

        ensure_extension_button = getattr(nav_bar, "ensure_extension_button", None)
        if callable(ensure_extension_button):
            ensure_extension_button(
                key="shape_editor",
                icon_text="🎨",
                label="拼贴画",
                on_click=lambda: self.open_editor_in_browser(),
                tooltip="打开拼贴画编辑器（Web）",
            )
            return

        # 旧版主程序无扩展 API：回退为插件内直插（尽量不破坏 mode button group）
        from PyQt6 import QtWidgets

        nav_module = __import__(nav_bar.__class__.__module__, fromlist=["NavigationButton"])
        NavigationButton = getattr(nav_module, "NavigationButton", None)
        if NavigationButton is None:
            return
        btn = NavigationButton("🎨", "拼贴画", "shape_editor", nav_bar)
        btn.setCheckable(False)
        btn.clicked.connect(lambda: self.open_editor_in_browser())

        layout = nav_bar.layout()
        if isinstance(layout, QtWidgets.QVBoxLayout):
            insert_index = max(0, layout.count() - 1)
            layout.insertWidget(insert_index, btn)

    def _inject_menu_actions(self) -> None:
        main_window = self._main_window
        if main_window is None:
            return

        from PyQt6 import QtGui, QtWidgets

        if not isinstance(main_window, QtWidgets.QMainWindow):
            raise TypeError(f"main_window 必须是 QMainWindow（got: {type(main_window).__name__}）")

        menu_bar = main_window.menuBar()
        # 复用/创建“内部工具”菜单（与 example plugin 保持一致的中文入口）
        private_menu = None
        for action in menu_bar.actions():
            if action is None:
                continue
            text = str(action.text() or "")
            if text.strip() == "内部工具":
                private_menu = action.menu()
                break
        if private_menu is None:
            private_menu = menu_bar.addMenu("内部工具")

        # 避免重复注入
        if getattr(main_window, "_shape_editor_menu_installed", False):
            return

        open_editor_action = QtGui.QAction("打开拼贴画编辑器（Web）", main_window)
        open_editor_action.triggered.connect(lambda: self.open_editor_in_browser())
        private_menu.addAction(open_editor_action)

        def _ensure_settings_file_exists() -> Path:
            settings_path = get_shape_editor_settings_file_path()
            if not settings_path.is_file():
                save_shape_editor_settings(load_shape_editor_settings())
            return settings_path

        open_settings_action = QtGui.QAction("打开拼贴画导出设置文件…", main_window)
        open_settings_action.setToolTip("打开 runtime cache 下的 shape_editor_settings.json（配置 base .gia 路径与模板映射）")

        def _open_settings() -> None:
            p = _ensure_settings_file_exists()
            if hasattr(os, "startfile"):
                os.startfile(str(p))  # type: ignore[attr-defined]
                return
            raise RuntimeError("os.startfile unavailable")

        open_settings_action.triggered.connect(_open_settings)
        private_menu.addAction(open_settings_action)

        setattr(main_window, "_shape_editor_menu_installed", True)

