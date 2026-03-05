from __future__ import annotations

from pathlib import Path

from ugc_file_tools.repo_paths import ugc_file_tools_builtin_resources_root


def get_builtin_empty_base_gil_path() -> Path:
    """
    返回程序内置的“空存档 base .gil”路径。

    约束：
    - 该文件必须随程序分发（属于程序内置资源），用户无需手工提供。
    - 该函数只负责定位与 fail-fast 校验，不做任何复制/解码。
    """
    pkg_root = ugc_file_tools_builtin_resources_root()
    # 说明：
    # - `真空存档.gil` 属于“极空基底”（root4 缺失大量段），用于 bootstrapping/回归；
    # - 导出中心的“内置空存档 base”应使用“带基础设施”的空存档，避免后续增量写回时需要额外补齐大量段。
    p = (pkg_root / "empty_base_samples" / "empty_base_with_infra.gil").resolve()
    if not p.is_file():
        raise FileNotFoundError(f"内置空存档 .gil 不存在：{str(p)}")
    if p.suffix.lower() != ".gil":
        raise RuntimeError(f"内置空存档文件扩展名异常（应为 .gil）：{str(p)}")
    return p

