
"""
Perfect Pixel: A library for auto grid detection and pixel art refinement.
"""

__version__ = "0.1.2"

from .perfect_pixel_noCV2 import get_perfect_pixel as _get_perfect_pixel_numpy

try:
    import cv2
    from .perfect_pixel import get_perfect_pixel as _get_perfect_pixel_opencv
    get_perfect_pixel = _get_perfect_pixel_opencv
except ImportError:
    _get_perfect_pixel_opencv = None
    get_perfect_pixel = _get_perfect_pixel_numpy

__all__ = ["get_perfect_pixel"]