from __future__ import annotations

import inspect
import sys
from pathlib import Path

if __package__:
    from tools._bootstrap import ensure_workspace_root_on_sys_path, get_workspace_root
else:
    from _bootstrap import ensure_workspace_root_on_sys_path, get_workspace_root


def _get_signature_param_names(signature: inspect.Signature) -> list[str]:
    return [name for name in signature.parameters.keys() if name != "self"]


def _validate_automation_executor_protocol_contract() -> None:
    from app.automation.editor.editor_executor import EditorExecutor
    from app.automation.editor.executor_protocol import EditorExecutorProtocol, ViewportController

    critical_executor_method_names = [
        "log",
        "emit_visual",
        "capture_and_emit",
        "recognize_visible_nodes",
        "execute_step",
        "get_last_context_click_editor_pos",
        "set_last_context_click_editor_pos",
    ]

    critical_viewport_method_names = [
        "get_program_viewport_rect",
        "convert_program_to_editor_coords",
        "convert_editor_to_screen_coords",
        "ensure_program_point_visible",
    ]

    for method_name in critical_executor_method_names:
        if not hasattr(EditorExecutorProtocol, method_name):
            raise AssertionError(f"Protocol missing method: {method_name}")
        if not hasattr(EditorExecutor, method_name):
            raise AssertionError(f"EditorExecutor missing method: {method_name}")

        protocol_signature = inspect.signature(getattr(EditorExecutorProtocol, method_name))
        implementation_signature = inspect.signature(getattr(EditorExecutor, method_name))
        if _get_signature_param_names(protocol_signature) != _get_signature_param_names(
            implementation_signature
        ):
            raise AssertionError(
                f"Signature mismatch for {method_name}: "
                f"protocol={protocol_signature} impl={implementation_signature}"
            )

    for method_name in critical_viewport_method_names:
        if not hasattr(ViewportController, method_name):
            raise AssertionError(f"ViewportController protocol missing method: {method_name}")
        if not hasattr(EditorExecutor, method_name):
            raise AssertionError(f"EditorExecutor missing viewport method: {method_name}")

        protocol_signature = inspect.signature(getattr(ViewportController, method_name))
        implementation_signature = inspect.signature(getattr(EditorExecutor, method_name))
        if _get_signature_param_names(protocol_signature) != _get_signature_param_names(
            implementation_signature
        ):
            raise AssertionError(
                f"Viewport signature mismatch for {method_name}: "
                f"protocol={protocol_signature} impl={implementation_signature}"
            )


def _validate_in_memory_graph_payload_cache_contract() -> None:
    from app.common import in_memory_graph_payload_cache as graph_payload_cache

    graph_payload_cache.clear_all_graph_data()

    first_graph_data = {"graph_id": "graph_a", "nodes": [], "edges": []}
    second_graph_data = {"graph_id": "graph_a", "nodes": [{"id": "n1"}], "edges": []}

    cache_key_first = graph_payload_cache.store_graph_data("root_a", "graph_a", first_graph_data)
    cache_key_second = graph_payload_cache.store_graph_data("root_b", "graph_a", second_graph_data)

    if cache_key_first != "root_a::graph_a":
        raise AssertionError(f"Unexpected cache key: {cache_key_first}")
    if cache_key_second != "root_b::graph_a":
        raise AssertionError(f"Unexpected cache key: {cache_key_second}")

    if graph_payload_cache.fetch_graph_data(cache_key_first) != first_graph_data:
        raise AssertionError("fetch_graph_data mismatch for first key")
    if graph_payload_cache.fetch_graph_data(cache_key_second) != second_graph_data:
        raise AssertionError("fetch_graph_data mismatch for second key")

    resolved_direct = graph_payload_cache.resolve_graph_data(
        {"graph_data": {"direct": True}, "graph_data_key": cache_key_first}
    )
    if resolved_direct != {"direct": True}:
        raise AssertionError("resolve_graph_data should prefer direct payload over cache")

    resolved_cached = graph_payload_cache.resolve_graph_data({"graph_data_key": cache_key_first})
    if resolved_cached != first_graph_data:
        raise AssertionError("resolve_graph_data should resolve cached payload via graph_data_key")

    graph_payload_cache.drop_graph_data_for_graph("graph_a")
    if graph_payload_cache.fetch_graph_data(cache_key_first) is not None:
        raise AssertionError("drop_graph_data_for_graph should invalidate first key")
    if graph_payload_cache.fetch_graph_data(cache_key_second) is not None:
        raise AssertionError("drop_graph_data_for_graph should invalidate second key")


def _run_ui_library_pages_smoke(*, skip_ocr: bool) -> None:
    from engine.configs.settings import settings
    from tools import smoke_test_ui_libraries as ui_smoke

    workspace_root = get_workspace_root()
    settings.set_config_path(workspace_root)
    settings.load()

    # 重要：如需 OCR 预热，必须在导入 PyQt6 之前完成，避免 DLL 冲突。
    if not skip_ocr:
        ui_smoke._load_ocr_engine()

    from PyQt6 import QtWidgets

    qt_app = QtWidgets.QApplication.instance()
    if qt_app is None:
        qt_app = QtWidgets.QApplication(sys.argv)

    resource_manager, package_index_manager, package_views = ui_smoke._build_package_view_candidates(
        workspace_root
    )

    ui_smoke._run_template_library_smoke(resource_manager, package_views)
    ui_smoke._run_entity_placement_smoke(resource_manager, package_views)
    ui_smoke._run_graph_library_smoke(resource_manager, package_index_manager)
    ui_smoke._run_package_library_smoke(resource_manager, package_index_manager)

    for top_level_widget in list(QtWidgets.QApplication.topLevelWidgets()):
        top_level_widget.close()


def main() -> None:
    """
    UI/automation 冒烟级回归入口（不启动主窗口）：
    - UI：资源库关键页面构造+刷新（可选预热 OCR）
    - automation：执行器协议关键方法签名一致性
    - common：graph_data in-memory 缓存契约（cache_key 与失效语义）
    """
    ensure_workspace_root_on_sys_path()

    skip_ui = "--skip-ui" in sys.argv
    skip_ocr = "--skip-ocr" in sys.argv
    skip_automation = "--skip-automation" in sys.argv

    sys.argv = [arg for arg in sys.argv if arg not in {"--skip-ui", "--skip-ocr", "--skip-automation"}]

    from engine.utils.logging.console_sanitizer import install_ascii_safe_print

    install_ascii_safe_print()

    if not skip_ui:
        _run_ui_library_pages_smoke(skip_ocr=skip_ocr)

    if not skip_automation:
        _validate_automation_executor_protocol_contract()
        _validate_in_memory_graph_payload_cache_contract()

    print("OK: validate_ui_automation_contracts passed.")


if __name__ == "__main__":
    main()


