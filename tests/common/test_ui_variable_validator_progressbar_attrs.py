from __future__ import annotations

from pathlib import Path

from app.cli.ui_variable_validator import validate_ui_html_file


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_validate_ui_html_file_reports_invalid_progressbar_binding_expr(tmp_path: Path) -> None:
    html = """
<!doctype html>
<html>
  <body>
    <div data-ui-role="progressbar" data-progress-current-var="bad"></div>
  </body>
</html>
""".strip()
    path = _write(tmp_path, "ui.html", html)
    issues = validate_ui_html_file(path)
    assert len(issues) == 1
    assert "data-progress-current-var" in issues[0].token
    assert "缺少作用域前缀" in issues[0].message


def test_validate_ui_html_file_allows_valid_progressbar_binding_expr(tmp_path: Path) -> None:
    html = """
<!doctype html>
<html>
  <body>
    <div data-ui-role="progressbar" data-progress-current-var="ps.界面_挑战面板数据__战斗状态_当前生命"></div>
  </body>
</html>
""".strip()
    path = _write(tmp_path, "ui.html", html)
    issues = validate_ui_html_file(path)
    assert issues == []


def test_validate_ui_html_file_reports_progressbar_binding_dict_key_path_forbidden(tmp_path: Path) -> None:
    html = """
<!doctype html>
<html>
  <body>
    <div data-ui-role="progressbar" data-progress-current-var="lv.UI结算_整数.完整度_当前"></div>
  </body>
</html>
""".strip()
    path = _write(tmp_path, "ui.html", html)
    issues = validate_ui_html_file(path)
    assert len(issues) == 1
    assert "data-progress-current-var" in issues[0].token
    assert "进度条绑定不支持字典键路径" in issues[0].message


def test_validate_ui_html_file_allows_number_literal_for_progressbar_min_max(tmp_path: Path) -> None:
    html = """
<!doctype html>
<html>
  <body>
    <div data-ui-role="progressbar" data-progress-min-var="0" data-progress-max-var="100"></div>
  </body>
</html>
""".strip()
    path = _write(tmp_path, "ui.html", html)
    issues = validate_ui_html_file(path)
    assert issues == []

