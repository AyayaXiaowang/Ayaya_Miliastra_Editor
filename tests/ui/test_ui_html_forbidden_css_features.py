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


def test_ui_html_forbidden_css_features() -> None:
    """
    目的：把“扁平化不支持/会直接报错”的坑前移到 CI。

    注意：Workbench 的伪元素校验对源码文本很敏感，
    甚至可能在注释里出现相同片段也会触发（因此这里也按纯文本扫描）。
    """
    repo_root = _get_repo_root()
    html_files = _iter_ui_html_files(repo_root)
    if not html_files:
        raise AssertionError("未找到 UI HTML 文件（测试项目/管理配置/UI源码/*.html）")

    # 1) 结构级硬错误：伪元素（Workbench 直接报错）
    # 这里不只禁 ::before/::after，也禁任意 '::'，避免注释中误写触发校验失败。
    forbidden_tokens = [
        ("::", "禁止伪元素/浏览器私有伪元素（Workbench 不会导出伪元素层，且会校验失败）"),
        ("background-image", "background-image 无法稳定写回（会被忽略/降级为纯色）"),
        ("transition", "CSS 动效不应出现（扁平化/运行态不支持/不一致）"),
        ("animation", "CSS 动效不应出现（扁平化/运行态不支持/不一致）"),
        ("filter:", "filter/backdrop-filter 不应出现（扁平化链路不支持/不一致）"),
        ("backdrop-filter", "filter/backdrop-filter 不应出现（扁平化链路不支持/不一致）"),
    ]

    violations: list[str] = []
    scanned_files: list[str] = []
    for html_path in html_files:
        text = html_path.read_text(encoding="utf-8")
        # 仅对“准备走 Workbench 扁平化/写回”的页面启用硬护栏：
        # 约定：至少包含一个 data-ui- 标记（按钮/变量/状态等）。
        # 目录内可能存在纯设计草稿（不走写回链路），不强制这些草稿满足扁平化约束。
        if "data-ui-" not in text:
            continue

        scanned_files.append(html_path.name)
        lower = text.lower()
        for token, hint in forbidden_tokens:
            if token.lower() in lower:
                violations.append(f"- {html_path.name}: 命中 `{token}`（{hint}）")

    if not scanned_files:
        raise AssertionError("未找到包含 data-ui- 标记的 UI HTML（无法应用扁平化护栏规则）")

    if violations:
        raise AssertionError(
            "UI HTML 存在扁平化不兼容特性（请修复后再提交）。\n"
            f"扫描范围（仅 data-ui- 页面）：{';'.join(scanned_files)}\n"
            "命中列表：\n"
            + "\n".join(violations)
        )

