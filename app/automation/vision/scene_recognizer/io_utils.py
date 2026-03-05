from __future__ import annotations

from pathlib import Path
from typing import Optional
import os

import cv2
import numpy as np


_workspace_root_cache: Optional[Path] = None


def _resolve_workspace_root() -> Path:
    global _workspace_root_cache
    if _workspace_root_cache is not None:
        return _workspace_root_cache
    from engine.utils.workspace import resolve_workspace_root

    _workspace_root_cache = resolve_workspace_root(start_paths=[Path(__file__).resolve()])
    return _workspace_root_cache


def _cv2_imread_unicode_safe(image_path: Path, flags: int) -> Optional[np.ndarray]:
    """使用 OpenCV 的 imdecode 读取图片，兼容 Windows 中文路径。"""
    image_bytes = image_path.read_bytes()
    image_buffer = np.frombuffer(image_bytes, dtype=np.uint8)
    decoded_image = cv2.imdecode(image_buffer, flags)
    return decoded_image


def _cv2_imwrite_unicode_safe(image_path: Path, image_matrix: np.ndarray) -> None:
    """使用 OpenCV 的 imencode 写入图片，兼容 Windows 中文路径。"""
    file_extension = str(image_path.suffix or ".png").lower()
    success, encoded = cv2.imencode(file_extension, image_matrix)
    if not bool(success):
        raise ValueError(f"cv2.imencode 失败，无法写入：{image_path}")
    image_path.write_bytes(encoded.tobytes())


def _get_debug_output_root_dir() -> Path:
    env_value = str(os.environ.get("GRAPH_GENERATER_DEBUG_OUTPUT_ROOT", "") or "").strip()
    if env_value:
        return Path(env_value)

    workspace_root = _resolve_workspace_root()
    from engine.utils.cache.cache_paths import get_runtime_cache_root

    runtime_cache_root = get_runtime_cache_root(workspace_root)
    return runtime_cache_root / "debug" / "one_shot_scene_recognizer"


