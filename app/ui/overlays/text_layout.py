"""文本避让与网格占位索引工具"""

from __future__ import annotations

from PyQt6 import QtCore
from typing import Dict, List
from collections import defaultdict


class GridOccupancyIndex:
    """网格索引优化文本避让:按行高分桶存储已占用矩形,降低避让复杂度从O(N²)到O(N×桶内数量)"""
    def __init__(self, row_height: float):
        self.row_height = row_height
        self.buckets: Dict[int, List[QtCore.QRectF]] = defaultdict(list)
    
    def _get_bucket_range(self, rect: QtCore.QRectF) -> tuple[int, int]:
        """计算矩形跨越的桶范围(包含起始和结束桶)"""
        min_bucket = int(rect.top() // self.row_height)
        max_bucket = int(rect.bottom() // self.row_height)
        return min_bucket, max_bucket
    
    def add(self, rect: QtCore.QRectF) -> None:
        """添加占用矩形到所有跨越的桶"""
        min_bucket, max_bucket = self._get_bucket_range(rect)
        for bucket_id in range(min_bucket, max_bucket + 1):
            self.buckets[bucket_id].append(rect)
    
    def check_intersects(self, rect: QtCore.QRectF) -> bool:
        """检查矩形是否与已占用区域相交(仅检查相关桶)"""
        min_bucket, max_bucket = self._get_bucket_range(rect)
        for bucket_id in range(min_bucket, max_bucket + 1):
            for occupied_rect in self.buckets.get(bucket_id, []):
                if rect.intersects(occupied_rect):
                    return True
        return False

