from __future__ import annotations

from PIL import Image


def _assert_rect_is_inside_image(image: Image.Image, rect: tuple[int, int, int, int]) -> None:
    rect_left, rect_top, rect_width, rect_height = rect
    image_width, image_height = image.size

    assert rect_width > 0
    assert rect_height > 0
    assert 0 <= rect_left <= image_width - rect_width
    assert 0 <= rect_top <= image_height - rect_height
    assert rect_left + rect_width <= image_width
    assert rect_top + rect_height <= image_height


def test_get_region_rect_zoom_is_fitted_to_image_bounds(monkeypatch) -> None:
    """派生 ROI（节点图缩放区域）应保证返回矩形完全在截图内，避免越界导致 overlays 画到窗口外。"""

    from app.automation.capture.roi_config import get_region_rect

    image = Image.new("RGB", (1920, 1080), color=(0, 0, 0))

    def _fake_zoom_region_size_px() -> tuple[int, int]:
        return (140, 70)

    monkeypatch.setattr(
        "app.automation.vision.ui_profile_params.get_zoom_region_size_px",
        _fake_zoom_region_size_px,
    )

    rect = get_region_rect(image, "节点图缩放区域")
    _assert_rect_is_inside_image(image, rect)


def test_get_region_rect_zoom_huge_size_is_clamped_to_image(monkeypatch) -> None:
    """当 profile 给出异常的大尺寸时，缩放区域应退化为整张截图，而不是返回越界矩形。"""

    from app.automation.capture.roi_config import get_region_rect

    image = Image.new("RGB", (320, 200), color=(0, 0, 0))

    def _fake_zoom_region_size_px() -> tuple[int, int]:
        return (10_000, 10_000)

    monkeypatch.setattr(
        "app.automation.vision.ui_profile_params.get_zoom_region_size_px",
        _fake_zoom_region_size_px,
    )

    rect_left, rect_top, rect_width, rect_height = get_region_rect(image, "节点图缩放区域")

    assert rect_left == 0
    assert rect_top == 0
    assert rect_width == image.size[0]
    assert rect_height == image.size[1]

