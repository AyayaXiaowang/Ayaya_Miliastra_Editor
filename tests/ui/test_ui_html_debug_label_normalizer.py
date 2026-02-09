from __future__ import annotations

from pathlib import Path

from app.ui.controllers.ui_html_debug_label_normalizer import normalize_ui_html_bundle_cli_flattened_outputs


def test_normalize_flattened_html_debug_labels_dedupes_duplicates(tmp_path: Path) -> None:
    # Arrange: 模拟 ui_html_bundle_cli 输出目录结构
    workspace_root = tmp_path / "ws"
    package_id = "pkg_test"
    cache_dir = workspace_root / "app" / "runtime" / "cache" / "ui_html_bundle_cli" / package_id
    cache_dir.mkdir(parents=True)

    source_html_file = workspace_root / "assets" / "resource" / "a_ui_mockup.html"
    source_html_file.parent.mkdir(parents=True)
    source_html_file.write_text("<html></html>", encoding="utf-8")

    flattened = cache_dir / "a_ui_mockup.flattened__deadbe.flattened.html"
    flattened.write_text(
        """
<!doctype html>
<html><body>
  <div class="flat-text debug-target" data-debug-label="text-">A</div>
  <div class="flat-text debug-target" data-debug-label="text-">B</div>
  <div class="flat-text debug-target" data-debug-label="text-">C</div>
  <div class="flat-text debug-target" data-debug-label="text-unique">U</div>
</body></html>
""".strip(),
        encoding="utf-8",
    )

    # Act
    results = normalize_ui_html_bundle_cli_flattened_outputs(
        workspace_root=workspace_root,
        package_id=package_id,
        source_html_file=source_html_file,
    )

    # Assert
    assert len(results) == 1
    assert results[0].changed is True
    assert results[0].duplicate_label_count == 2

    text = flattened.read_text(encoding="utf-8")
    assert 'data-debug-label="text-"' in text
    assert 'data-debug-label="text-__2"' in text
    assert 'data-debug-label="text-__3"' in text
    assert 'data-debug-label="text-unique"' in text

