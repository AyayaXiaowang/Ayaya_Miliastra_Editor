from __future__ import annotations


def deny_direct_execution(*, tool_name: str) -> None:
    """
    约束：单工具脚本不再作为独立入口运行。

    目的：
    - 收口入口，避免出现“入口满天飞”导致的误跑/误用
    - 统一控制台编码与参数透传行为（统一入口负责）
    """

    name = str(tool_name or "").strip()
    if name == "":
        raise ValueError("tool_name must not be empty")

    raise SystemExit(
        "该脚本不再作为独立 CLI 入口使用。\n"
        "请改用统一入口：\n"
        f"  python -X utf8 -m ugc_file_tools tool {name} --help\n"
    )


