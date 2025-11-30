from __future__ import annotations

"""
生成 plugins/nodes/registry.py 的静态注册清单。

约定：
- 扫描 plugins/nodes/{server,client}/**/*.py（排除 __init__.py 与 shared/）
- 解析 AST，收集带 @node_spec(...) 的函数定义
- 生成确定性的 import 清单与 register_node_spec(...) 调用列表

使用：
    python -X utf8 tools/generate_plugin_registry.py
"""

import sys
from pathlib import Path
from typing import List, Tuple
import ast


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
IMPL_ROOT = WORKSPACE_ROOT / "plugins" / "nodes"
REGISTRY_FILE = WORKSPACE_ROOT / "plugins" / "nodes" / "registry.py"


def discover_impl_files() -> List[Path]:
    if not IMPL_ROOT.exists():
        return []
    files: List[Path] = []
    for py in IMPL_ROOT.rglob("*.py"):
        if py.name == "__init__.py":
            continue
        # 排除自身生成产物
        if py.name == "registry.py":
            continue
        # 排除 shared
        try:
            if (IMPL_ROOT / "shared") in py.parents:
                continue
        except Exception as e:
            # 按约定直接抛错，以便定位异常路径
            raise e
        files.append(py)
    # server 优先、再 client，保证导入顺序稳定
    def _key(p: Path) -> Tuple[int, str]:
        lower = str(p.as_posix()).lower()
        prio = 0
        if "/client/" in lower:
            prio = 1
        return (prio, lower)
    return sorted(files, key=_key)


def collect_decorated_functions(py_file: Path) -> List[Tuple[str, str]]:
    """
    返回 [(module_path, function_name)]
    module_path 形如 'plugins.nodes.server.执行节点.设置自定义变量'
    """
    src = py_file.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(py_file))
    results: List[Tuple[str, str]] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            has_node_spec = False
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call):
                    callee = dec.func
                    if isinstance(callee, ast.Name) and callee.id == "node_spec":
                        has_node_spec = True
                        break
            if has_node_spec:
                rel = py_file.relative_to(WORKSPACE_ROOT).with_suffix("")  # 去掉 .py
                module_path = ".".join(rel.parts)
                results.append((module_path, node.name))
    return results


def generate_registry(import_items: List[Tuple[str, str]]) -> str:
    """
    基于收集到的实现函数，生成静态注册表源码文本。

    设计要点：
    - 不再使用 `from ... import ...` 的静态导入，避免文件名中包含全角标点（如：、（、））
      时生成非法的 Python 标识符。
    - 使用字符串形式的模块路径 + `importlib.import_module` 进行懒加载导入，
      仍保持“注册清单是静态的、运行时不做文件扫描”的约定。
    """
    header = (
        'from __future__ import annotations\n\n'
        '"""\n'
        "静态注册表（由生成脚本维护）。\n\n"
        "运行时仅调用 `register_all_nodes(register_node_spec)` 完成节点实现的注册。\n"
        "本文件为确定性产物，请勿手工编辑。\n"
        '"""\n\n'
        "from typing import Callable, List, Tuple\n"
        "from importlib import import_module\n\n"
    )

    lines: List[str] = [header]

    # 静态节点清单：[(模块路径, 函数名)]
    lines.append("NODES: List[Tuple[str, str]] = [\n")
    for module_path, func_name in import_items:
        lines.append(f"    ({module_path!r}, {func_name!r}),\n")
    lines.append("]\n\n\n")

    # 统一的实现加载函数
    lines.append("def _load_node_impl(module_path: str, func_name: str):\n")
    lines.append("    module = import_module(module_path)\n")
    lines.append("    return getattr(module, func_name)\n\n\n")

    # 注册函数仅遍历清单并懒加载实现
    lines.append("def register_all_nodes(register_node_spec: Callable[..., None]) -> None:\n")
    if not import_items:
        lines.append("    return\n")
    else:
        lines.append("    for module_path, func_name in NODES:\n")
        lines.append("        impl = _load_node_impl(module_path, func_name)\n")
        lines.append("        register_node_spec(impl)\n")
    lines.append("\n")
    return "".join(lines)


def main() -> int:
    files = discover_impl_files()
    if not files:
        print("[ERROR] 未找到 plugins/nodes 下的节点实现文件")
        return 1
    items: List[Tuple[str, str]] = []
    for f in files:
        items.extend(collect_decorated_functions(f))
    # 去重（按导入路径+函数名）
    unique = sorted(set(items), key=lambda t: (t[0], t[1]))
    out = generate_registry(unique)
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_FILE.write_text(out, encoding="utf-8")
    print(f"[OK] 已生成静态注册表：{REGISTRY_FILE}")
    print(f"[INFO] 共导入 {len(unique)} 个实现函数")
    return 0


if __name__ == "__main__":
    sys.exit(main())


