from __future__ import annotations

"""运行时节点实现加载器（V2 唯一入口）。

说明：
- 节点“定义/发现/校验”由 engine.nodes.pipeline（V2 AST 管线）完成；
- 节点“实现导入”是运行时必需行为，本模块用 V2 的 AST 提取结果作为唯一清单来源，
  在需要导出节点函数时按文件加载并把实现函数注入到目标模块的 globals()。

约束：
- 不做目录级额外“自发扫描”逻辑：文件清单来自 V2 的 discover_implementation_files；
- 不做 try/except 吞错：任何导入失败直接抛出，便于暴露副作用与依赖问题。
"""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Callable, Dict, List
import re
import sys
import zlib

from engine.nodes.pipeline.discovery import discover_implementation_files
from engine.nodes.pipeline.extractor_ast import extract_specs
from engine.utils.name_utils import make_valid_identifier


_CACHED_MODULES_BY_FILE: Dict[Path, ModuleType] = {}
_CACHED_EXPORTS_BY_SCOPE: Dict[str, Dict[str, Callable[..., object]]] = {}


def _find_workspace_root() -> Path:
    """从当前文件位置向上推导项目根目录。"""
    candidate = Path(__file__).resolve()
    for _ in range(12):
        if (candidate / "pyrightconfig.json").exists():
            return candidate
        if (candidate / "engine").exists() and (candidate / "app").exists():
            return candidate
        candidate = candidate.parent
    return Path(__file__).resolve().parents[3]


def _ensure_import_roots_on_sys_path(workspace_root: Path) -> None:
    """确保导入节点实现时，engine/plugins 等包可被解析。"""
    root_text = str(workspace_root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)


def _sanitize_module_part(text: str) -> str:
    # 保留：ASCII 字母数字、下划线、常用中文汉字；其余一律替换为 '_'
    cleaned = re.sub(r"[^0-9A-Za-z_\u4e00-\u9fff]+", "_", str(text or ""))
    cleaned = cleaned.strip("_")
    if cleaned == "":
        cleaned = "module"
    if cleaned[0].isdigit():
        cleaned = "_" + cleaned
    return cleaned


def _make_loaded_module_name(workspace_root: Path, file_path: Path, scope: str) -> str:
    rel = str(file_path.resolve().relative_to(workspace_root.resolve()).as_posix())
    checksum = zlib.adler32(rel.encode("utf-8")) & 0xFFFFFFFF
    stem_safe = _sanitize_module_part(file_path.stem)
    return f"runtime.engine._loaded_nodes.{_sanitize_module_part(scope)}.{stem_safe}_{checksum:08x}"


def _load_module_from_file(*, workspace_root: Path, file_path: Path, scope: str) -> ModuleType:
    cached = _CACHED_MODULES_BY_FILE.get(file_path)
    if cached is not None:
        return cached

    module_name = _make_loaded_module_name(workspace_root, file_path, scope)
    spec = spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法为节点实现创建模块说明：{file_path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    _CACHED_MODULES_BY_FILE[file_path] = module
    return module


def load_node_exports_for_scope(scope: str) -> Dict[str, Callable[..., object]]:
    """加载并返回指定作用域（server/client）的节点实现函数导出表：{函数名: callable}。"""
    scope_text = str(scope or "").strip().lower()
    if scope_text not in {"server", "client"}:
        raise ValueError(f"scope 必须是 'server' 或 'client'（got: {scope!r}）")

    cached = _CACHED_EXPORTS_BY_SCOPE.get(scope_text)
    if cached is not None:
        return cached

    workspace_root = _find_workspace_root().resolve()
    _ensure_import_roots_on_sys_path(workspace_root)

    impl_root = (workspace_root / "plugins" / "nodes" / scope_text).resolve()
    all_files = discover_implementation_files(workspace_root)
    scoped_files: List[Path] = [p for p in all_files if impl_root in p.resolve().parents]

    extracted = extract_specs(scoped_files)

    exports: Dict[str, Callable[..., object]] = {}
    for spec in extracted:
        function_name = str(getattr(spec, "function_name", "") or "").strip()
        if function_name == "":
            raise ValueError(f"节点实现函数名缺失（file={spec.file_path}）")

        module = _load_module_from_file(
            workspace_root=workspace_root,
            file_path=spec.file_path,
            scope=scope_text,
        )
        impl = getattr(module, function_name)
        if function_name in exports and exports[function_name] is not impl:
            raise ValueError(f"节点实现函数名冲突：{function_name}（file={spec.file_path}）")
        exports[function_name] = impl

        # 统一“可调用名”别名：根据 @node_spec(name=...) 的显示名称推导稳定的 Python 标识符。
        # 说明：
        # - Graph Code 与导出的可执行代码都要求节点以函数调用形式出现（必须是合法标识符）；
        # - 节点显示名可能包含 '/'、'：'、括号等字符；此处为其注入稳定别名，保持“显示名/实现函数名”解耦。
        display_name = str(getattr(spec, "name", "") or "").strip()
        if display_name:
            callable_alias = make_valid_identifier(display_name)
            if callable_alias and callable_alias not in exports:
                exports[callable_alias] = impl
            elif callable_alias and exports.get(callable_alias) is not impl:
                raise ValueError(
                    f"节点可调用别名冲突：{callable_alias}（name={display_name}，file={spec.file_path}）"
                )

            # 兼容历史约定：若显示名包含 '/'，同时提供“去掉斜杠”的别名。
            # 例如："设置背包掉落道具/货币数量" -> "设置背包掉落道具货币数量"
            slash_removed = display_name.replace("/", "").strip()
            if slash_removed:
                slash_removed_alias = make_valid_identifier(slash_removed)
                if slash_removed_alias and slash_removed_alias not in exports:
                    exports[slash_removed_alias] = impl
                elif slash_removed_alias and exports.get(slash_removed_alias) is not impl:
                    raise ValueError(
                        f"节点可调用别名冲突：{slash_removed_alias}（name={display_name}，file={spec.file_path}）"
                    )

    _CACHED_EXPORTS_BY_SCOPE[scope_text] = exports
    return exports


