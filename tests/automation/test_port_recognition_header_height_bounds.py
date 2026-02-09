from __future__ import annotations

import app.automation.vision.ui_profile_params as ui_profile_params


def _make_params(*, port_header_height_px: int) -> ui_profile_params.AutomationUiProfileParams:
    return ui_profile_params.AutomationUiProfileParams(
        profile_name="TEST",
        port_header_height_px=int(port_header_height_px),
        node_view_size_px=(1, 1),
        node_dedup_grid_size_px=1,
        node_dedup_iou_threshold=0.0,
        node_dedup_containment_ratio=0.0,
        node_dedup_center_distance_px=0.0,
        node_dedup_axis_overlap_ratio=0.0,
        port_same_row_y_tolerance_px=1,
        port_template_nms_iou_threshold=0.0,
        color_scan_min_height_threshold_px=1,
        color_scan_min_width_threshold_px=1,
        color_merge_max_vertical_gap_px=1,
        ocr_exclude_top_pixels_default=0,
        candidate_search_margin_top_px=0,
        candidate_popup_size_px=(1, 1),
        zoom_region_size_px=(1, 1),
    )


def test_get_port_header_height_px_clamped_to_minimum(monkeypatch) -> None:
    def fake_resolve_automation_ui_params(
        *,
        workspace_root=None,
        preferred_locale: str = "CN",
        profile_name_override: str | None = None,
    ):
        _ = workspace_root, preferred_locale, profile_name_override
        return _make_params(port_header_height_px=17)

    monkeypatch.setattr(ui_profile_params, "resolve_automation_ui_params", fake_resolve_automation_ui_params)
    assert ui_profile_params.get_port_header_height_px() == ui_profile_params._MIN_PORT_HEADER_HEIGHT_PX


def test_get_port_header_height_px_clamped_to_maximum(monkeypatch) -> None:
    def fake_resolve_automation_ui_params(
        *,
        workspace_root=None,
        preferred_locale: str = "CN",
        profile_name_override: str | None = None,
    ):
        _ = workspace_root, preferred_locale, profile_name_override
        return _make_params(port_header_height_px=999)

    monkeypatch.setattr(ui_profile_params, "resolve_automation_ui_params", fake_resolve_automation_ui_params)
    assert ui_profile_params.get_port_header_height_px() == ui_profile_params._MAX_PORT_HEADER_HEIGHT_PX


def test_get_port_header_height_px_keeps_mid_range_value(monkeypatch) -> None:
    def fake_resolve_automation_ui_params(
        *,
        workspace_root=None,
        preferred_locale: str = "CN",
        profile_name_override: str | None = None,
    ):
        _ = workspace_root, preferred_locale, profile_name_override
        return _make_params(port_header_height_px=23)

    monkeypatch.setattr(ui_profile_params, "resolve_automation_ui_params", fake_resolve_automation_ui_params)
    assert ui_profile_params.get_port_header_height_px() == 23


