from __future__ import annotations

import argparse
from pathlib import Path

from ugc_file_tools.tool_registry import iter_tool_specs


def _render_tool_line(*, name: str, risk: str, summary: str) -> str:
    n = str(name).strip()
    r = str(risk).strip()
    s = str(summary).strip()
    if n == "":
        raise ValueError("tool name 不能为空")
    if r == "":
        raise ValueError(f"tool risk 不能为空：{n!r}")
    if s == "":
        raise ValueError(f"tool summary 不能为空：{n!r}")
    return f"- **`{n}` [{r}]**：{s}"


def render_tool_index_markdown() -> str:
    specs = list(iter_tool_specs())
    sections_in_order: list[str] = []
    for s in specs:
        if s.section not in sections_in_order:
            sections_in_order.append(s.section)

    lines: list[str] = []
    lines.append("# ugc_file_tools 工具索引（可检索）")
    lines.append("")
    lines.append("本文件由 `ugc_file_tools/tool_registry.py` 生成。")
    lines.append("- 如需新增/改名/调整风险与说明：修改注册表后重新生成本文件。")
    lines.append("- 生成/校验脚本：`python -X utf8 -m ugc_file_tools.tools.generate_tool_index_md --help`")
    lines.append("")
    lines.append("本文件用于快速回答两个问题：")
    lines.append("- **“我该跑哪个入口？”**")
    lines.append("- **“这个入口会不会写盘/改存档？”**")
    lines.append("")
    lines.append("> 约定：下文工具名均可用 `python -X utf8 -m ugc_file_tools tool <工具名> --help` 查看完整参数与示例。")
    lines.append("")
    lines.append("## 统一运行姿势（推荐）")
    lines.append("- **统一入口（最常用）**：`python -X utf8 -m ugc_file_tools --help`")
    lines.append("  - 等价入口：`python ugc_file_tools/ugc_unified.py --help`")
    lines.append("- **统一入口转发单工具**：`python -X utf8 -m ugc_file_tools tool <工具名> --help`")
    lines.append("- 不再提供 `ugc_file_tools.tools.<模块名>` 单独入口（避免同名双入口）；统一用 `ugc_file_tools tool`。")
    lines.append("")
    lines.append("PowerShell 提醒：不使用 `&&` 串联命令；需要多条命令请分行执行。")
    lines.append("")
    lines.append("`.gia` 提醒：所有生成/写回 `.gia` 的工具都会将产物**最终导出**到固定目录：")
    lines.append("- `Path.home()/AppData/LocalLow/miHoYo/原神/BeyondLocal/Beyond_Local_Export`（Windows 推导路径）")
    lines.append("- `ugc_file_tools/out/` 仍会落盘作为中间产物与可追溯输出。")
    lines.append("")
    lines.append("## 风险标识（读写与破坏性）")
    lines.append("- **[只读]**：只读取/解析并输出报告，不改磁盘（或仅写到临时输出文件）")
    lines.append("- **[写盘]**：会生成导出产物/报告/代码到 `out/` 等目录（通常可重复生成）")
    lines.append("- **[危险写盘]**：会生成新的 `.gil`/对存档做写回类操作；务必先备份输入存档，并确认输出路径")
    lines.append("")
    lines.append("## 推荐入口（统一 CLI）")
    lines.append("- **`ugc_file_tools` [写盘/危险写盘]**：统一入口（UI / project / entity）。")
    lines.append("  - `python -X utf8 -m ugc_file_tools --help`")
    lines.append("")

    for section in sections_in_order:
        lines.append(f"## {section}")
        for spec in specs:
            if spec.section != section:
                continue
            lines.append(_render_tool_line(name=spec.name, risk=spec.risk, summary=spec.summary))
        lines.append("")

    return "\n".join(lines)


def _normalize_newlines(text: str) -> str:
    return str(text).replace("\r\n", "\n").replace("\r", "\n")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="从 ugc_file_tools/tool_registry.py 生成/校验 tools/工具索引.md。")
    parser.add_argument(
        "--write",
        action="store_true",
        help="将生成结果写入 ugc_file_tools/tools/工具索引.md。",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="校验 ugc_file_tools/tools/工具索引.md 是否与注册表一致；不一致则抛错。",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    target_path = Path(__file__).resolve().parent / "工具索引.md"
    rendered = render_tool_index_markdown()

    if bool(args.write):
        target_path.write_text(rendered + "\n", encoding="utf-8")
        return

    if bool(args.check):
        existing = target_path.read_text(encoding="utf-8") if target_path.is_file() else ""
        if _normalize_newlines(existing).rstrip("\n") != _normalize_newlines(rendered).rstrip("\n"):
            raise RuntimeError(
                "工具索引与注册表不一致。请运行："
                "python -X utf8 -m ugc_file_tools.tools.generate_tool_index_md --write"
            )
        return

    print(rendered)


if __name__ == "__main__":
    main()


