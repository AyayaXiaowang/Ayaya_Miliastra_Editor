from __future__ import annotations

import argparse
import sys

from ugc_file_tools.tool_registry import TOOL_NAME_SET, find_tool_spec, iter_tool_module_names, iter_tool_specs


def _iter_available_tool_module_names() -> list[str]:
    # 真源：统一工具注册表 ugc_file_tools/tool_registry.py
    return iter_tool_module_names()


def _command_tool(arguments: argparse.Namespace) -> None:
    """
    统一入口转发到 ugc_file_tools.commands 下的“工具模块”，减少“入口脚本太多”的心智负担。

    示例：
    - 列表：python -m ugc_file_tools tool --list
    - 透传 help：python -m ugc_file_tools tool parse_gil_to_model --help
    """

    import importlib
    import inspect

    list_tools = bool(getattr(arguments, "list_tools", False))
    allow_dangerous = bool(getattr(arguments, "dangerous", False))
    tool_name_text = str(getattr(arguments, "tool_name", "") or "").strip()
    tool_args = list(getattr(arguments, "tool_args", []) or [])

    available = _iter_available_tool_module_names()

    if list_tools or tool_name_text == "":
        print("=" * 80)
        print("可用工具（统一入口可转发的工具名）：")
        for spec in iter_tool_specs():
            print(f"- {spec.name} [{spec.risk}] {spec.summary}")
        print("-" * 80)
        print("运行方式：")
        print("- 推荐：python -X utf8 -m ugc_file_tools tool <name> --help")
        print("- 若工具标记为“危险写盘”，需显式添加：--dangerous")
        print("=" * 80)
        return

    normalized = tool_name_text.replace("-", "_")

    if normalized not in TOOL_NAME_SET:
        raise ValueError(
            f"未知工具模块: {tool_name_text!r}（归一化后 {normalized!r}）。可选: {available}"
        )

    spec = find_tool_spec(normalized)
    if spec is None:
        raise RuntimeError(f"internal error: tool spec not found: {normalized!r}")

    if ("危险" in str(spec.risk)) and (not bool(allow_dangerous)):
        # 允许在不解锁危险写盘的情况下查看帮助，降低“被拦截导致看不到参数”的摩擦。
        if not any(str(a) in {"-h", "--help"} for a in tool_args):
            raise SystemExit(
                f"该工具标记为【{spec.risk}】：{spec.summary}\n"
                "为避免误操作，必须显式添加 --dangerous 才允许运行。\n"
                "示例：\n"
                f"  python -X utf8 -m ugc_file_tools tool --dangerous {normalized} --help\n"
            )

    module = importlib.import_module(f"ugc_file_tools.commands.{normalized}")
    main_func = getattr(module, "main", None)
    if not callable(main_func):
        raise AttributeError(f"{normalized}.main 不存在或不可调用")

    signature = inspect.signature(main_func)
    if len(signature.parameters) == 0:
        sys.argv = [normalized, *tool_args]
        main_func()
        return

    main_func(tool_args)


def add_subparser_tool(subparsers: argparse._SubParsersAction) -> None:
    tool_parser = subparsers.add_parser(
        "tool",
        help="运行 ugc_file_tools 内置工具（透传参数；用于收口入口脚本）。",
    )
    tool_parser.add_argument(
        "--list",
        dest="list_tools",
        action="store_true",
        help="列出可用工具名（对应 ugc_file_tools/commands/<tool>.py）。",
    )
    tool_parser.add_argument(
        "--dangerous",
        dest="dangerous",
        action="store_true",
        help="允许运行标记为“危险写盘”的工具（需要你明确确认风险）。",
    )
    tool_parser.add_argument(
        "tool_name",
        nargs="?",
        help="工具名，例如 parse_gil_to_model（也支持 parse-gil-to-model）。",
    )
    tool_parser.add_argument(
        "tool_args",
        nargs=argparse.REMAINDER,
        help="透传给工具的参数（包含 --help）。",
    )
    tool_parser.set_defaults(entrypoint=_command_tool)


