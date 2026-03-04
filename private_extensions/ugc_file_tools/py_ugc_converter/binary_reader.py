from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BinaryReader:
    """按遊戲自定義格式讀取二進制數據的工具，支持 7bit 可變長整數和小端 float32。"""

    data_bytes: bytes

    def __post_init__(self) -> None:
        self.current_index: int = 0
        self.end_index: int = len(self.data_bytes)
        self.error_flag: bool = False

    @property
    def offset(self) -> int:
        """返回當前讀取位置（相對於本 Reader 緩衝區起點的偏移）。"""
        return self.current_index

    def is_eof(self) -> bool:
        return self.current_index == self.end_index

    def is_error(self) -> bool:
        return self.error_flag or self.current_index > self.end_index

    def is_eof_or_error(self) -> bool:
        return self.is_eof() or self.is_error()

    def _check_size(self, size: int) -> bool:
        if self.current_index + size > self.end_index:
            self.error_flag = True
            self.current_index = self.end_index + 1
            return False
        return True

    def peek_uint8(self) -> int:
        if self.current_index + 1 > self.end_index:
            return 0
        return self.data_bytes[self.current_index]

    def read_uint8(self) -> int:
        if not self._check_size(1):
            return 0
        value = self.data_bytes[self.current_index]
        self.current_index += 1
        return value

    def read_var_uint(self) -> int:
        """讀取 7bit 編碼的可變長無符號整數。"""
        result_value: int = 0
        bit_shift: int = 0
        while bit_shift < 35:
            byte_value = self.read_uint8()
            result_value |= (byte_value & 0x7F) << bit_shift
            if (byte_value & 0x80) == 0:
                break
            bit_shift += 7
        return result_value

    def read_float32(self) -> float:
        """以小端格式讀取 float32。"""
        if not self._check_size(4):
            return 0.0
        import struct

        float_bytes = self.data_bytes[self.current_index : self.current_index + 4]
        self.current_index += 4
        float_value = struct.unpack("<f", float_bytes)[0]
        return float_value

    def read_bytes(self, size: int) -> bytes:
        if not self._check_size(size):
            return b""
        value = self.data_bytes[self.current_index : self.current_index + size]
        self.current_index += size
        return value


