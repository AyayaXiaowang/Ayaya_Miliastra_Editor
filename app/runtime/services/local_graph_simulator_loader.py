from __future__ import annotations

import re
import sys
import types
import tokenize
from dataclasses import dataclass
from pathlib import Path

from engine import GraphCodeParser, get_node_registry
from engine.utils.cache.cache_paths import get_runtime_cache_root
from engine.utils.name_utils import sanitize_class_name
from engine.utils.workspace import init_settings_for_workspace

from app.codegen import ExecutableCodeGenerator

from .local_graph_simulator_ui_keys import _hash32


@dataclass(frozen=True, slots=True)
class GraphCompileResult:
    workspace_root: Path
    graph_code_file: Path
    graph_name: str
    graph_type: str
    executable_file: Path
    module_name: str
    class_name: str


def compile_graph_to_executable(*, workspace_root: Path, graph_code_file: Path) -> GraphCompileResult:
    """
    将节点图源码编译为“可运行节点图类”（生成到 runtime cache），并返回编译结果信息。

    注意：
    - 生成文件属于运行时缓存，不落资源库；
    - 为保持 `app/runtime/cache/` 的“纯数据目录”约束，生成源码 **不以 `.py` 落盘**，而是写入 `.py.txt`；
    - 加载时始终走 `tokenize.open + compile + exec`，避免触发 `__pycache__`（并避免误将 cache 当作可导入包）。
    """
    workspace = Path(workspace_root).resolve()
    graph_path = Path(graph_code_file).resolve()
    if not graph_path.is_file():
        raise FileNotFoundError(str(graph_path))

    init_settings_for_workspace(workspace_root=workspace, load_user_settings=False)

    registry = get_node_registry(workspace, include_composite=True)
    node_library = registry.get_library()

    parser = GraphCodeParser(workspace, node_library)
    graph_model, metadata = parser.parse_file(graph_path)

    graph_name = str(metadata.get("graph_name") or getattr(graph_model, "graph_name", "") or "").strip()
    graph_type = str(metadata.get("graph_type") or "server").strip() or "server"
    if not graph_name:
        graph_name = str(getattr(graph_model, "graph_name", "") or "").strip() or graph_path.stem

    generator = ExecutableCodeGenerator(workspace, node_library)
    executable_code = generator.generate_code(graph_model, metadata)

    cache_root = get_runtime_cache_root(workspace)
    out_dir = (cache_root / "local_graph_sim" / "executable_graph_sources").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # 稳定 key：仅基于绝对路径（避免每次修改源码都生成新文件/新 module_name 造成缓存堆积）。
    key = graph_path.as_posix()
    digest = _hash32(key)
    out_file = (out_dir / f"{graph_path.stem}__exec_{digest:08x}.py.txt").resolve()
    out_file.write_text(executable_code, encoding="utf-8")

    module_name = f"runtime.local_graph_sim.{graph_path.stem}_{digest:08x}"
    class_name = sanitize_class_name(graph_name)
    if not class_name:
        class_name = sanitize_class_name(graph_path.stem) or "Graph"

    return GraphCompileResult(
        workspace_root=workspace,
        graph_code_file=graph_path,
        graph_name=graph_name,
        graph_type=graph_type,
        executable_file=out_file,
        module_name=module_name,
        class_name=class_name,
    )


def load_compiled_graph_class(result: GraphCompileResult) -> type:
    # 说明：
    # - 不走 importlib 的 bytecode cache（__pycache__），避免在 runtime cache 下生成/污染 __pycache__；
    # - 生成文件以 `.py.txt` 形式落盘，仍然按 Python 源码语义执行（便于 diff/排查）。
    if not result.executable_file.is_file():
        raise FileNotFoundError(str(result.executable_file))
    with tokenize.open(str(result.executable_file)) as f:
        source_text = f.read()
    module = types.ModuleType(str(result.module_name))
    module.__file__ = str(result.executable_file)
    module.__package__ = str(result.module_name).rpartition(".")[0]
    sys.modules[str(result.module_name)] = module
    code = compile(source_text, str(result.executable_file), "exec")
    exec(code, module.__dict__)

    graph_class = getattr(module, result.class_name, None)
    if not isinstance(graph_class, type):
        raise RuntimeError(f"可执行图模块缺少类: {result.class_name} ({result.executable_file})")
    return graph_class


@dataclass(frozen=True, slots=True)
class GraphSourceResult:
    workspace_root: Path
    graph_code_file: Path
    graph_name: str
    graph_type: str
    module_name: str
    class_name: str


def _parse_graph_meta_from_source(graph_code_file: Path) -> tuple[str, str]:
    """
    读取源码顶部注释块中的 graph_name / graph_type（若不存在则回退）。

    约定：Graph Code 文件开头 docstring 常含：
      graph_name: xxx
      graph_type: server
    """
    text = Path(graph_code_file).read_text(encoding="utf-8")
    # 只扫描前 200 行足够（但这里直接扫描全文也没副作用）
    name_match = re.search(r"^graph_name:\s*(.+?)\s*$", text, flags=re.MULTILINE)
    type_match = re.search(r"^graph_type:\s*(.+?)\s*$", text, flags=re.MULTILINE)
    graph_name = (name_match.group(1).strip() if name_match else "") or Path(graph_code_file).stem
    graph_type = (type_match.group(1).strip() if type_match else "") or "server"
    return graph_name, graph_type


def load_source_graph_module_and_class(*, result: GraphSourceResult) -> tuple[object, type]:
    # 说明：
    # - 不走 importlib 的 bytecode cache（__pycache__），避免“项目存档目录携带旧 pyc”导致源码与执行不一致；
    # - 同时避免在 `assets/资源库/项目存档/...` 下生成/污染 __pycache__。
    # - 编码规则对齐 Python importer：使用 tokenize.open() 解析 PEP 263 编码声明。
    with tokenize.open(str(result.graph_code_file)) as f:
        source_text = f.read()
    module = types.ModuleType(str(result.module_name))
    module.__file__ = str(result.graph_code_file)
    module.__package__ = str(result.module_name).rpartition(".")[0]
    sys.modules[str(result.module_name)] = module
    code = compile(source_text, str(result.graph_code_file), "exec")
    exec(code, module.__dict__)

    graph_class = getattr(module, result.class_name, None)
    if not isinstance(graph_class, type):
        raise RuntimeError(f"节点图源码模块缺少类: {result.class_name} ({result.graph_code_file})")
    return module, graph_class


__all__ = [
    "GraphCompileResult",
    "compile_graph_to_executable",
    "load_compiled_graph_class",
    "GraphSourceResult",
    "load_source_graph_module_and_class",
]

