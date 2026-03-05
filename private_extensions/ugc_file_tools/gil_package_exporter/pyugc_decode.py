from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Tuple

from ..py_ugc_converter.binary_reader import BinaryReader
from ..py_ugc_converter.dtype_model import DtypeNode
from ..py_ugc_converter.ugc_converter import UgcConverter
from ..py_ugc_converter.ugc_data import JsonNodeType, UgcData

from .gil_reader import _read_gil_header
from .models import GilHeader


def _decode_gil_with_pyugc(gil_file_path: Path, dtype_path: Path) -> Tuple[GilHeader, Any]:
    converter = UgcConverter()
    converter.load_dtype(str(dtype_path))
    converter.load_file(str(gil_file_path))

    gil_bytes = gil_file_path.read_bytes()
    header = _read_gil_header(gil_bytes)

    converter.ugc_data.prepare_for_json()
    python_object = converter.ugc_data.to_python()
    return header, python_object


def _decode_bytes_with_dtype_root(
    dtype_converter: UgcConverter,
    dtype_root_node: DtypeNode,
    message_bytes: bytes,
) -> Tuple[Any, Dict[str, Any]]:
    dtype_converter.ugc_data = UgcData()
    root_data_node = dtype_converter.ugc_data.root()
    root_data_node.node_type = JsonNodeType.OBJECT

    reader = BinaryReader(message_bytes)
    dtype_converter._read_data_section(root_data_node, dtype_root_node, reader)

    dtype_converter.ugc_data.prepare_for_json()
    decoded_object = dtype_converter.ugc_data.to_python()

    consumed_bytes = int(reader.offset)
    total_bytes = len(message_bytes)
    consumed_ratio = (consumed_bytes / total_bytes) if total_bytes > 0 else 0.0
    stats = {
        "total_bytes": total_bytes,
        "consumed_bytes": consumed_bytes,
        "consumed_ratio": consumed_ratio,
        "reader_error": bool(reader.is_error()),
        "reader_eof": bool(reader.is_eof()),
    }
    return decoded_object, stats


