from __future__ import annotations

from pathlib import Path

from app.cli.ui_variable_quickfixes import _collect_required_variables


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_collect_required_variables_includes_progressbar_binding_expr(tmp_path: Path) -> None:
    html = """
<!doctype html>
<html>
  <body>
    <div data-ui-role="progressbar" data-progress-current-var="ps.界面_挑战面板数据__战斗状态_当前生命"></div>
  </body>
</html>
""".strip()
    _write(tmp_path, "ui.html", html)
    required, _defaults_by_scope, _progressbar_int_defaults_by_scope = _collect_required_variables(tmp_path)
    assert () in required["ps"]["界面_挑战面板数据__战斗状态_当前生命"]


def test_collect_required_variables_ignores_number_literal_progressbar_min_max(tmp_path: Path) -> None:
    html = """
<!doctype html>
<html>
  <body>
    <div data-ui-role="progressbar" data-progress-min-var="0" data-progress-max-var="100"></div>
  </body>
</html>
""".strip()
    _write(tmp_path, "ui.html", html)
    required, _defaults_by_scope, _progressbar_int_defaults_by_scope = _collect_required_variables(tmp_path)
    assert required["ps"] == {}
    assert required["lv"] == {}

