from __future__ import annotations

from typing import NoReturn


def raise_deprecated_signal_bindings_write() -> NoReturn:
    """禁止直接写入 GraphModel.metadata['signal_bindings'] 的统一报错入口。"""

    raise ValueError("禁止直接写入 metadata['signal_bindings']，请使用 GraphSemanticPass")


def raise_deprecated_struct_bindings_write() -> NoReturn:
    """禁止直接写入 GraphModel.metadata['struct_bindings'] 的统一报错入口。"""

    raise ValueError("禁止直接写入 metadata['struct_bindings']，请使用 GraphSemanticPass")


__all__ = [
    "raise_deprecated_signal_bindings_write",
    "raise_deprecated_struct_bindings_write",
]


