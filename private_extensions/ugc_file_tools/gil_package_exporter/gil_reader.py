from __future__ import annotations

from .models import GilHeader


def _read_gil_header(gil_bytes: bytes) -> GilHeader:
    if len(gil_bytes) < 0x14:
        raise ValueError("gil file size is too small")

    total_size_field = int.from_bytes(gil_bytes[0:4], "big", signed=False)
    header_value_one = int.from_bytes(gil_bytes[4:8], "big", signed=False)
    header_value_two = int.from_bytes(gil_bytes[8:12], "big", signed=False)
    type_id_value = int.from_bytes(gil_bytes[12:16], "big", signed=False)
    body_size = int.from_bytes(gil_bytes[16:20], "big", signed=False)

    if len(gil_bytes) < total_size_field + 4:
        raise ValueError("gil header size field is invalid")

    footer_offset = total_size_field
    footer_value = int.from_bytes(
        gil_bytes[footer_offset : footer_offset + 4],
        "big",
        signed=False,
    )

    return GilHeader(
        total_size_field=total_size_field,
        header_value_one=header_value_one,
        header_value_two=header_value_two,
        type_id_value=type_id_value,
        body_size=body_size,
        footer_value=footer_value,
    )




def read_gil_header(gil_bytes: bytes) -> GilHeader:
    """Public API: parse `.gil` header bytes into a `GilHeader`."""
    return _read_gil_header(gil_bytes)
