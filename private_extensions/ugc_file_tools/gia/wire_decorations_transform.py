from __future__ import annotations

"""ugc_file_tools.gia.wire_decorations_transform.

Thin facade that preserves the public API while delegating implementation to wire_decorations_transform_impl.
"""

from pathlib import Path
from typing import Any, Dict, Optional

from ugc_file_tools.gia.wire_decorations_transform_impl.api import (
    merge_and_center_decorations_gia_wire as _merge_and_center_decorations_gia_wire_impl,
)


def merge_and_center_decorations_gia_wire(
    *,
    input_gia_path: Path,
    output_gia_path: Path,
    check_header: bool,
    center_mode: str,
    center_axes: str,
    center_policy: str,
    do_center: bool,
    do_merge: bool,
    target_parent_id: Optional[int],
    target_parent_name: str,
    drop_other_parents: bool,
    keep_file_path: bool,
    file_path_override: str,
) -> Dict[str, Any]:
    """Facade for wire-level merge/center decorations operation."""
    return _merge_and_center_decorations_gia_wire_impl(
        input_gia_path=input_gia_path,
        output_gia_path=output_gia_path,
        check_header=check_header,
        center_mode=center_mode,
        center_axes=center_axes,
        center_policy=center_policy,
        do_center=do_center,
        do_merge=do_merge,
        target_parent_id=target_parent_id,
        target_parent_name=target_parent_name,
        drop_other_parents=drop_other_parents,
        keep_file_path=keep_file_path,
        file_path_override=file_path_override,
    )
