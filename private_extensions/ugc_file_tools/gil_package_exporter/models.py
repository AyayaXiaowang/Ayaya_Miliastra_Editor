from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GilHeader:
    total_size_field: int
    header_value_one: int
    header_value_two: int
    type_id_value: int
    body_size: int
    footer_value: int


@dataclass(frozen=True)
class DataBlobRecord:
    blob_index: int
    json_path: str
    key_name: str
    byte_size: int
    sha1_hex: str
    file_stem: str


