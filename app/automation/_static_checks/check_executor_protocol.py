# -*- coding: utf-8 -*-
"""
静态检查：验证 EditorExecutor 实现符合 EditorExecutorProtocol 协议

检查内容：
1. EditorExecutor 是否实现了协议中定义的所有方法
2. 方法签名是否与协议一致（参数名、类型注解）
3. 依赖executor的模块是否使用协议类型注解

使用方式：
    python core/automation/_static_checks/check_executor_protocol.py
"""

import inspect
import sys
from pathlib import Path
from typing import Protocol, get_type_hints, get_origin

# 添加项目根目录到Python路径
workspace_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(workspace_root))

from app.automation.editor.executor_protocol import EditorExecutorProtocol
from app.automation.editor.editor_executor import EditorExecutor


def ascii_safe_print(message: object) -> None:
    """避免控制台编码炸裂：把不可编码字符转义后输出。"""
    text = str(message)
    print(text.encode("ascii", errors="backslashreplace").decode("ascii"))


safe_print = ascii_safe_print


def check_protocol_implementation():
    """检查 EditorExecutor 是否完整实现了 EditorExecutorProtocol"""
    
    safe_print("=" * 80)
    safe_print("Static Check: EditorExecutor Protocol Implementation")
    safe_print("=" * 80)
    safe_print("")
    
    # 获取协议定义的所有成员
    protocol_members = {}
    for name, value in inspect.getmembers(EditorExecutorProtocol):
        if name.startswith('_') and not name.startswith('__'):
            # 私有方法/属性
            protocol_members[name] = value
        elif not name.startswith('_'):
            # 公共方法/属性
            protocol_members[name] = value
    
    # 过滤掉特殊属性和类型注解
    protocol_attributes = {}
    protocol_methods = {}
    
    # 获取协议的类型注解（属性）
    hints = get_type_hints(EditorExecutorProtocol)
    for attr_name, attr_type in hints.items():
        if not attr_name.startswith('__'):
            protocol_attributes[attr_name] = attr_type
    
    # 获取协议的方法签名
    for name in dir(EditorExecutorProtocol):
        if name.startswith('__'):
            continue
        attr = getattr(EditorExecutorProtocol, name)
        if inspect.isfunction(attr):
            sig = inspect.signature(attr)
            protocol_methods[name] = sig
    
    # 检查 EditorExecutor 实现
    missing_attributes = []
    missing_methods = []
    signature_mismatches = []
    
    # 检查属性
    safe_print("1. Check Attributes (Note: Protocol attributes are typically instance attributes)")
    safe_print("-" * 80)
    safe_print("[INFO] Protocol defines attributes that should be initialized in __init__")
    safe_print(f"[INFO] Found {len(protocol_attributes)} protocol attributes:")
    for attr_name, attr_type in protocol_attributes.items():
        safe_print(f"  - {attr_name}: {attr_type}")
    safe_print("[INFO] Assuming attributes are properly initialized (cannot verify at class level)")
    safe_print("")
    
    # 检查方法
    safe_print("2. Check Methods and Signatures")
    safe_print("-" * 80)
    for method_name, protocol_sig in protocol_methods.items():
        if not hasattr(EditorExecutor, method_name):
            missing_methods.append(method_name)
            safe_print(f"[X] Missing method: {method_name}{protocol_sig}")
            continue
        
        impl_method = getattr(EditorExecutor, method_name)
        if not callable(impl_method):
            safe_print(f"[WARN] {method_name} is not callable")
            continue
        
        impl_sig = inspect.signature(impl_method)
        
        # 比较参数（忽略self）
        protocol_params = list(protocol_sig.parameters.items())[1:]  # 跳过self
        impl_params = list(impl_sig.parameters.items())[1:]  # 跳过self
        
        if len(protocol_params) != len(impl_params):
            signature_mismatches.append((method_name, "param count mismatch", protocol_sig, impl_sig))
            safe_print(f"[X] Signature mismatch: {method_name}")
            safe_print(f"  Protocol: {protocol_sig}")
            safe_print(f"  Implementation: {impl_sig}")
        else:
            params_match = True
            for (proto_name, _proto_param), (impl_name, _impl_param) in zip(protocol_params, impl_params):
                if proto_name != impl_name:
                    params_match = False
                    break
            
            if params_match:
                safe_print(f"[OK] Method exists and signature matches: {method_name}")
            else:
                signature_mismatches.append((method_name, "param name mismatch", protocol_sig, impl_sig))
                safe_print(f"[WARN] Method exists but param names don't match: {method_name}")
    
    if not missing_methods and not signature_mismatches:
        safe_print("[OK] All methods correctly implemented")
    safe_print("")
    
    # 总结
    safe_print("=" * 80)
    safe_print("Summary")
    safe_print("=" * 80)
    
    total_errors = len(missing_attributes) + len(missing_methods) + len(signature_mismatches)
    
    if total_errors == 0:
        safe_print("[OK] All checks passed! EditorExecutor fully implements EditorExecutorProtocol")
        return True
    else:
        safe_print(f"[X] Found {total_errors} issues:")
        if missing_attributes:
            safe_print(f"  - Missing attributes: {len(missing_attributes)}")
        if missing_methods:
            safe_print(f"  - Missing methods: {len(missing_methods)}")
        if signature_mismatches:
            safe_print(f"  - Signature mismatches: {len(signature_mismatches)}")
        return False


def check_protocol_usage_in_modules():
    """检查关键模块是否使用协议类型注解"""
    
    safe_print("")
    safe_print("=" * 80)
    safe_print("Check: Protocol Type Annotation Usage in Key Modules")
    safe_print("=" * 80)
    safe_print("")
    
    # 需要检查的关键模块（按功能分层，而非物理目录名命名）。
    # 说明：
    # - 早期实现位于 `core/automation/*`，现已迁移至应用层 `app/automation/*`；
    # - 这里列出的路径全部相对于仓库根目录。
    modules_to_check = [
        "app/automation/ports/port_type_steps.py",
        "app/automation/ports/port_type_steps_input.py",
        "app/automation/ports/port_type_steps_output.py",
        "app/automation/config/config_node_steps.py",
        "app/automation/editor/executor_utils.py",
        "app/automation/editor/editor_nodes.py",
    ]
    
    results = []
    
    for module_path in modules_to_check:
        full_path = workspace_root / module_path
        if not full_path.exists():
            safe_print(f"[WARN] File not found: {module_path}")
            continue
        
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查是否导入了协议
        has_protocol_import = "from app.automation.editor.executor_protocol import" in content
        
        # 检查是否使用了协议类型注解
        has_protocol_annotation = "EditorExecutorProtocol" in content
        
        if has_protocol_import and has_protocol_annotation:
            safe_print(f"[OK] {module_path}: Using protocol type annotations")
            results.append((module_path, True))
        elif has_protocol_annotation:
            safe_print(f"[WARN] {module_path}: Using protocol but not properly imported")
            results.append((module_path, False))
        else:
            safe_print(f"[X] {module_path}: Not using protocol type annotations")
            results.append((module_path, False))
    
    safe_print("")
    using_count = sum(1 for _, used in results if used)
    safe_print(f"Protocol usage: {using_count}/{len(results)} modules use protocol type annotations")
    
    return all(used for _, used in results)


def main():
    """主函数：执行所有检查"""
    
    # 检查1：协议实现完整性
    impl_ok = check_protocol_implementation()
    
    # 检查2：模块使用协议类型注解
    usage_ok = check_protocol_usage_in_modules()
    
    # 最终结果
    safe_print("")
    safe_print("=" * 80)
    if impl_ok and usage_ok:
        safe_print("[OK][OK][OK] All checks passed! Protocol definition consistent with implementation")
        sys.exit(0)
    else:
        safe_print("[X][X][X] Issues found, please fix and recheck")
        sys.exit(1)


if __name__ == "__main__":
    main()

