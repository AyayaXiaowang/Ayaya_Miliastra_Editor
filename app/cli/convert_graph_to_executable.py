#!/usr/bin/env python
from __future__ import annotations

"""将节点图代码（类结构 Python）导出为可执行格式

用法:
    python -X utf8 -m app.cli.convert_graph_to_executable assets/资源库/节点图/server/xxx.py

注意：生成的“可执行代码”主要用于离线调试/教学和快速验证 Graph Code 结构，基于节点定义推导调用顺序，并不承诺完全还原官方编辑器或游戏中的真实执行语义。
"""

import sys
from pathlib import Path

if not __package__:
    raise SystemExit(
        "请从项目根目录使用模块方式运行：\n"
        "  python -X utf8 -m app.cli.convert_graph_to_executable <节点图代码文件路径>\n"
        "（不再支持通过脚本内 sys.path.insert 的方式运行）"
    )

# 项目根目录（脚本位于 app/cli/ 下）
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]

from app.codegen import ExecutableCodeGenerator
from engine import GraphCodeParser, get_node_registry, log_info, log_error
from engine.configs.settings import settings

# CLI 工具默认开启信息级日志，确保用户可见进度与结果
settings.NODE_IMPL_LOG_VERBOSE = True
# 关键：为 layout/registry 等依赖 workspace_path 的模块提供入口信息
settings.set_config_path(WORKSPACE_ROOT)


def convert_graph_file(code_file_path: str) -> int:
    """转换节点图代码文件为可执行格式"""
    code_path = Path(code_file_path)
    if not code_path.exists():
        log_error(f"[ERROR] 文件不存在: {code_path}")
        return 1

    log_info(f"[INFO] 读取节点图代码文件: {code_path.name}")
    log_info("=" * 60)

    workspace = WORKSPACE_ROOT
    registry = get_node_registry(workspace, include_composite=True)
    node_library = registry.get_library()
    log_info(f"[OK] 已加载 {len(node_library)} 个节点定义")

    parser = GraphCodeParser(workspace, node_library)
    graph_model, metadata = parser.parse_file(code_path)
    log_info(f"[OK] 解析成功: {graph_model.graph_name or '未命名节点图'}")
    log_info(f"   - 节点数: {len(graph_model.nodes)}")
    log_info(f"   - 连线数: {len(graph_model.edges)}")

    generator = ExecutableCodeGenerator(workspace, node_library)
    executable_code = generator.generate_code(graph_model, metadata)
    log_info(f"[OK] 生成可执行代码 ({len(executable_code)} 字符)")

    output_path = code_path.parent / f"{code_path.stem}_executable{code_path.suffix}"
    output_path.write_text(executable_code, encoding='utf-8')

    log_info(f"[OK] 已保存到: {output_path}")
    log_info("\n" + "=" * 60)
    log_info("转换完成！")
    log_info("\n运行新文件:")
    log_info(f'  python -X utf8 "{output_path}"')
    log_info("=" * 60)

    return 0


def main() -> int:
    if len(sys.argv) < 2:
        log_error("用法: python -X utf8 -m app.cli.convert_graph_to_executable <节点图代码文件路径>")
        log_error("\n示例:")
        log_error("  python -X utf8 -m app.cli.convert_graph_to_executable assets/资源库/节点图/server/xxx.py")
        return 1
    code_file = sys.argv[1]
    return convert_graph_file(code_file)


if __name__ == "__main__":
    sys.exit(main())



