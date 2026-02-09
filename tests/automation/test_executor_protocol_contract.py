from __future__ import annotations

import inspect
from pathlib import Path

from app.automation.editor.editor_executor import EditorExecutor
from app.automation.editor.executor_protocol import EditorExecutorProtocol, ViewportController
from tests._helpers.project_paths import get_repo_root


def _get_signature_param_names(signature: inspect.Signature) -> list[str]:
    return [name for name in signature.parameters.keys() if name != "self"]


def test_editor_executor_critical_protocol_methods_signature_stable() -> None:
    """
    冒烟级回归：自动化执行器的关键协议方法存在且签名不漂移。

    说明：
    - 不实例化 EditorExecutor（避免依赖真实窗口/截图/输入环境），仅做反射级契约校验；
    - 仅覆盖关键方法子集，避免把“协议新增但暂未用于跨模块调用”的变化误判为失败。
    """
    critical_executor_method_names = [
        # 日志/可视化（跨模块最常用）
        "log",
        "emit_visual",
        "capture_and_emit",
        # 节点识别与步骤执行（上层编排核心入口）
        "recognize_visible_nodes",
        "execute_step",
        # 上下文菜单坐标（UI/自动化交互边界）
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
        assert hasattr(EditorExecutorProtocol, method_name)
        assert hasattr(EditorExecutor, method_name)

        protocol_signature = inspect.signature(getattr(EditorExecutorProtocol, method_name))
        implementation_signature = inspect.signature(getattr(EditorExecutor, method_name))

        assert _get_signature_param_names(protocol_signature) == _get_signature_param_names(
            implementation_signature
        )

    for method_name in critical_viewport_method_names:
        assert hasattr(ViewportController, method_name)
        assert hasattr(EditorExecutor, method_name)

        protocol_signature = inspect.signature(getattr(ViewportController, method_name))
        implementation_signature = inspect.signature(getattr(EditorExecutor, method_name))

        assert _get_signature_param_names(protocol_signature) == _get_signature_param_names(
            implementation_signature
        )


def test_key_automation_modules_use_protocol_type_annotations() -> None:
    """
    冒烟级回归：关键 automation 模块使用协议类型注解，避免回退到具体实现类导致耦合膨胀。
    """
    workspace_root = get_repo_root()

    module_paths = [
        workspace_root / "app" / "automation" / "ports" / "port_type_steps.py",
        workspace_root / "app" / "automation" / "ports" / "port_type_steps_input.py",
        workspace_root / "app" / "automation" / "ports" / "port_type_steps_output.py",
        workspace_root / "app" / "automation" / "config" / "config_node_steps.py",
        workspace_root / "app" / "automation" / "editor" / "executor_utils.py",
        workspace_root / "app" / "automation" / "editor" / "editor_nodes.py",
    ]

    for module_path in module_paths:
        module_text = module_path.read_text(encoding="utf-8")
        assert "EditorExecutorProtocol" in module_text
        assert "from app.automation.editor.executor_protocol import" in module_text


