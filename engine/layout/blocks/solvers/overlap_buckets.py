from __future__ import annotations

import math
from typing import List, Set

from ...internal.layout_models import LayoutBlock

from .types import PositioningRuntimeState


def iter_overlap_candidates(runtime: PositioningRuntimeState, top: float, bottom: float) -> List[LayoutBlock]:
    """
    根据垂直区间仅返回可能重叠的已放置块，避免对整个集合进行O(N)扫描。

    重要：该函数为“逻辑搬迁”，保持与 BlockPositioningEngine._iter_overlap_candidates 完全一致。
    """
    if not runtime.bucket_map:
        return list(runtime.positioned_blocks)
    start_bucket = int(math.floor(top / runtime.bucket_size)) - 1
    end_bucket = int(math.floor(bottom / runtime.bucket_size)) + 1
    candidates: List[LayoutBlock] = []
    seen: Set[LayoutBlock] = set()
    for bucket_index in range(start_bucket, end_bucket + 1):
        bucket_blocks = runtime.bucket_map.get(bucket_index)
        if not bucket_blocks:
            continue
        for block in bucket_blocks:
            if block in seen:
                continue
            seen.add(block)
            candidates.append(block)
    return candidates


def register_block_in_buckets(runtime: PositioningRuntimeState, block: LayoutBlock) -> None:
    """
    将已放置块按垂直区间注册到桶中，供后续重叠检测快速查询。

    重要：该函数为“逻辑搬迁”，保持与 BlockPositioningEngine._register_block_in_buckets 完全一致。
    """
    top = float(block.top_left_pos[1])
    bottom = top + float(block.height)
    start_bucket = int(math.floor(top / runtime.bucket_size))
    end_bucket = int(math.floor(bottom / runtime.bucket_size))
    for bucket_index in range(start_bucket, end_bucket + 1):
        runtime.bucket_map.setdefault(bucket_index, []).append(block)


