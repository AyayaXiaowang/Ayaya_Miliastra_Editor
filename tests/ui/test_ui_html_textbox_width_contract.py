from __future__ import annotations

from pathlib import Path


def _get_repo_root() -> Path:
    # tests/ui/<this_file>
    return Path(__file__).resolve().parents[2]


def _iter_ui_html_files(repo_root: Path) -> list[Path]:
    # 仅扫描“测试项目”，避免误扫私有资源库内容
    ui_src_dir = (
        repo_root
        / "assets"
        / "资源库"
        / "项目存档"
        / "测试项目"
        / "管理配置"
        / "UI源码"
    )
    return sorted([p for p in ui_src_dir.glob("*.html") if p.is_file()], key=lambda p: p.name)


def test_ui_html_textbox_width_contract() -> None:
    """
    目的：把“扁平化后 TextBox 宽度过窄 → 运行时文本变长就换行”的坑前移到 CI。

    约束策略（静态护栏，不依赖 Playwright）：
    - 只检查包含 data-ui- 标记的页面（表示会走 Workbench 导出/写回链路）
    - 若页面使用了 btn-text（按钮/标签内层文字），必须定义一条 .btn-text 样式，确保：
      - 作为 flex item 可拉伸（flex: ...）
      - 允许收缩（min-width: 0）
    - 若页面出现 data-ui-text 或 {1:lv. 占位符，则必须提供 data-ui-variable-defaults（默认值映射）
      以避免“跑起来全是空值/0，难以排查”。
    """
    repo_root = _get_repo_root()
    html_files = _iter_ui_html_files(repo_root)
    if not html_files:
        raise AssertionError("未找到 UI HTML 文件（测试项目/管理配置/UI源码/*.html）")

    violations: list[str] = []
    scanned_files: list[str] = []
    for html_path in html_files:
        text = html_path.read_text(encoding="utf-8")
        if "data-ui-" not in text:
            continue

        scanned_files.append(html_path.name)
        lower = text.lower()

        # 1) btn-text 必须可拉伸
        if "btn-text" in lower:
            # 要求存在 .btn-text 规则，并具备 flex + min-width:0 两个关键字
            has_rule = ".btn-text" in lower
            has_flex = "flex:" in lower
            has_min_width0 = "min-width: 0" in lower or "min-width:0" in lower
            if not (has_rule and has_flex and has_min_width0):
                violations.append(
                    "- {name}: 使用了 `.btn-text` 但未满足“可拉伸宽度”约束（需要 `.btn-text` 规则，且包含 `flex:` 与 `min-width:0`）".format(
                        name=html_path.name
                    )
                )

        # 2) 使用了写回文本占位符 -> 必须提供变量默认值映射
        uses_ui_text_binding = ("data-ui-text" in lower) or ("{1:lv." in lower) or ("{{lv." in lower)
        if uses_ui_text_binding and ("data-ui-variable-defaults" not in lower):
            violations.append(
                "- {name}: 使用了 `data-ui-text`/lv 占位符，但未声明 `data-ui-variable-defaults`（建议在页面根元素上提供默认值映射）".format(
                    name=html_path.name
                )
            )

    if not scanned_files:
        raise AssertionError("未找到包含 data-ui- 标记的 UI HTML（无法应用 TextBox 宽度护栏规则）")

    if violations:
        raise AssertionError(
            "UI HTML 存在“TextBox 宽度/变量默认值”合同违规（请修复后再提交）。\n"
            f"扫描范围（仅 data-ui- 页面）：{';'.join(scanned_files)}\n"
            "命中列表：\n"
            + "\n".join(violations)
        )

