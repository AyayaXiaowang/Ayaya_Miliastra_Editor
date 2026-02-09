from __future__ import annotations

from tests._helpers.project_paths import get_repo_root


def _load_web_ui_workbench_plugin_module():
    from app.common import private_extension_loader as loader

    repo_root = get_repo_root()
    plugin_py = repo_root / "private_extensions" / "千星沙箱网页处理工具" / "plugin.py"
    assert plugin_py.is_file(), f"missing plugin.py: {plugin_py}"

    module_id = "tests._private_extensions.qxsandbox_web_ui_workbench_plugin"
    return loader._load_module_from_path(module_id=module_id, file_path=plugin_py)


def test_normalize_progressbar_color_hex_maps_common_pure_colors_to_palette() -> None:
    module = _load_web_ui_workbench_plugin_module()
    Bridge = module._UiWorkbenchBridge

    assert Bridge._normalize_progressbar_color_hex("#FFFFFF") == "#E2DBCE"
    assert Bridge._normalize_progressbar_color_hex("#00FF00") == "#92CD21"
    assert Bridge._normalize_progressbar_color_hex("#FFFF00") == "#F3C330"
    assert Bridge._normalize_progressbar_color_hex("#0000FF") == "#36F3F3"
    assert Bridge._normalize_progressbar_color_hex("#FF0000") == "#F47B7B"


def test_sanitize_bundle_payload_rewrites_progressbar_color_in_place() -> None:
    module = _load_web_ui_workbench_plugin_module()
    Bridge = module._UiWorkbenchBridge

    bundle = {
        "templates": [
            {
                "template_id": "t1",
                "widgets": [
                    {"widget_type": "进度条", "settings": {"color": "#FFFFFF"}},
                    {"widget_type": "文本框", "settings": {"text_content": "hello"}},
                ],
            }
        ]
    }
    Bridge._sanitize_bundle_payload_for_gil_writeback(bundle)
    assert bundle["templates"][0]["widgets"][0]["settings"]["color"] == "#E2DBCE"

