from __future__ import annotations

from pathlib import Path


def _get_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _extract_css_rule_block(text: str, selector: str) -> str:
    """
    取出某个 selector 的 CSS 规则块（粗略解析，足够用于护栏扫描）。
    返回包含花括号内内容的子串；找不到则返回空串。
    """
    idx = text.find(selector)
    if idx < 0:
        return ""
    brace_open = text.find("{", idx)
    if brace_open < 0:
        return ""
    brace_close = text.find("}", brace_open + 1)
    if brace_close < 0:
        return ""
    return text[brace_open + 1 : brace_close]


def test_ui_html_shadow_depth_spec_for_data_ui_pages() -> None:
    """
    目的：把“阴影深度规范”做成硬护栏，避免后续页面阴影深度漂移。

    约束范围：仅对包含 data-ui- 标记、且声明了 tone-3 皮肤遮罩的页面生效。
    """
    repo_root = _get_repo_root()
    ui_src_dir = (
        repo_root
        / "assets"
        / "资源库"
        / "项目存档"
        / "测试项目"
        / "管理配置"
        / "UI源码"
    )
    html_files = sorted([p for p in ui_src_dir.glob("*.html") if p.is_file()], key=lambda p: p.name)
    if not html_files:
        raise AssertionError("未找到 UI HTML 文件（测试项目/管理配置/UI源码/*.html）")

    required_masks = {
        "rgba(14, 14, 14, 0.25)",
        "#0e0e0e40",
    }
    allowed_var_ref = "var(--shadow-mask-25)"
    violations: list[str] = []
    scanned: list[str] = []

    for html_path in html_files:
        text = html_path.read_text(encoding="utf-8")
        if "data-ui-" not in text:
            continue
        if ".tone-3-stripe--bottom" not in text:
            continue

        scanned.append(html_path.name)

        # 必须存在 bottom/deep 两层，且二者都使用同一档浅阴影
        if ".tone-3-stripe--deep" not in text:
            violations.append(f"- {html_path.name}: 缺少 `.tone-3-stripe--deep`（要求两层阴影）")
            continue

        bottom_block = _extract_css_rule_block(text, ".tone-3-stripe--bottom")
        deep_block = _extract_css_rule_block(text, ".tone-3-stripe--deep")
        if not bottom_block or not deep_block:
            violations.append(f"- {html_path.name}: 未能解析 tone-3 遮罩规则块（CSS 结构异常）")
            continue

        combined = bottom_block + "\n" + deep_block
        if not any((m in combined) for m in required_masks):
            if allowed_var_ref in combined:
                # 允许用 CSS 变量引用，但要求变量定义为规范值
                if not any((f"--shadow-mask-25: {m}" in text) for m in required_masks):
                    violations.append(
                        f"- {html_path.name}: 使用 `{allowed_var_ref}` 但未找到规范的变量定义 `--shadow-mask-25: {sorted(required_masks)}`"
                    )
                    continue
            else:
                violations.append(f"- {html_path.name}: 未找到要求的浅阴影色 `{sorted(required_masks)}` 或 `{allowed_var_ref}`")
                continue

        # 禁止出现其它 alpha 的遮罩（简单文本护栏，避免深度漂移）
        forbidden_masks = [
            "rgba(0, 0, 0, 0.14)",
            "rgba(0, 0, 0, 0.22)",
            "rgba(14, 14, 14, 0.45)",
            "#0e0e0e73",
        ]
        for m in forbidden_masks:
            if m in combined:
                violations.append(f"- {html_path.name}: 出现禁止的遮罩色 `{m}`（深度漂移风险）")

    if scanned and violations:
        raise AssertionError(
            "UI HTML 阴影深度规范不符合要求。\n"
            f"扫描范围（data-ui 且声明 tone-3 遮罩）：{';'.join(scanned)}\n"
            "问题列表：\n"
            + "\n".join(violations)
        )

