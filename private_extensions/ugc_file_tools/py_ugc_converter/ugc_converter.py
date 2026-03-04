from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import json
import os

from .binary_reader import BinaryReader
from .dtype_model import DtypeModel, DtypeNode, DtypeValueType, DtypeFieldMeta
from .ugc_data import UgcData, JsonNode, JsonNodeType, UgcValueType


class CodeType(Enum):
    INT = 0
    DATA = 2
    FLOAT = 5


@dataclass
class GilHeaderInfo:
    total_size_field: int
    header_value_one: int
    header_value_two: int
    type_id_value: int
    body_size: int
    footer_value: int


class UgcConverter:
    """Python 版 UGC 轉換器，目前實現 .gil/.gia → JSON 解碼流程。"""

    def __init__(self) -> None:
        self.dtype_model = DtypeModel()
        self.ugc_data = UgcData()

    def load_dtype(self, dtype_path: str) -> None:
        self.dtype_model.load_from_file(dtype_path)

    def load_file(self, file_path: str) -> None:
        absolute_path = os.path.abspath(file_path)
        with open(absolute_path, "rb") as input_file:
            file_bytes = input_file.read()
        header_info, body_bytes = self._parse_header_and_body(file_bytes)
        self._build_ugc_tree(header_info, body_bytes)

    def save_json(self, output_path: str) -> None:
        self.ugc_data.prepare_for_json()
        python_object = self.ugc_data.to_python()
        absolute_path = os.path.abspath(output_path)
        with open(absolute_path, "w", encoding="utf-8") as output_file:
            json.dump(python_object, output_file, ensure_ascii=False, indent=2)

    def is_gil(self) -> bool:
        root_node = self.ugc_data.root()
        type_node = self.ugc_data.search_id(root_node, 3)
        if not type_node:
            return False
        return type_node.int_value == 2

    def _parse_header_and_body(self, file_bytes: bytes) -> tuple[GilHeaderInfo, bytes]:
        if len(file_bytes) < 0x14:
            raise ValueError("gil file size is too small")

        total_size_field = int.from_bytes(file_bytes[0:4], byteorder="big", signed=False)
        header_value_one = int.from_bytes(file_bytes[4:8], "big", signed=False)
        header_value_two = int.from_bytes(file_bytes[8:12], "big", signed=False)
        type_id_value = int.from_bytes(file_bytes[12:16], "big", signed=False)
        body_size = int.from_bytes(file_bytes[16:20], "big", signed=False)

        data_body_start = 0x14
        if len(file_bytes) < data_body_start + body_size:
            raise ValueError("gil body size is invalid")
        if len(file_bytes) < total_size_field + 4:
            raise ValueError("gil header size field is invalid")

        footer_offset = total_size_field
        footer_value = int.from_bytes(
            file_bytes[footer_offset : footer_offset + 4],
            "big",
            signed=False,
        )

        body_bytes = file_bytes[data_body_start : data_body_start + body_size]
        header_info = GilHeaderInfo(
            total_size_field=total_size_field,
            header_value_one=header_value_one,
            header_value_two=header_value_two,
            type_id_value=type_id_value,
            body_size=body_size,
            footer_value=footer_value,
        )
        return header_info, body_bytes

    def _build_ugc_tree(self, header_info: GilHeaderInfo, body_bytes: bytes) -> None:
        root_node = self.ugc_data.root()
        root_node.node_type = JsonNodeType.OBJECT

        node_one = self.ugc_data.push_back_int(
            root_node, 1, "", header_info.header_value_one, 0
        )
        node_two = self.ugc_data.push_back_int(
            root_node, 2, "", header_info.header_value_two, 0
        )
        node_three = self.ugc_data.push_back_int(
            root_node, 3, "", header_info.type_id_value, 0
        )
        node_four = self.ugc_data.push_back_object(root_node, 4, "", 0)
        node_five = self.ugc_data.push_back_int(
            root_node, 5, "", header_info.footer_value, 0
        )

        if not (node_one and node_two and node_three and node_four and node_five):
            raise ValueError("failed to create root nodes for gil data")

        dtype_root_for_type = self.dtype_model.search_id(
            self.dtype_model.root_node, header_info.type_id_value
        )
        if not dtype_root_for_type:
            raise ValueError(
                f"dtype root not found for type id {header_info.type_id_value}"
            )

        reader = BinaryReader(body_bytes)
        self._read_data_section(node_four, dtype_root_for_type, reader)
        if reader.is_error():
            raise ValueError(
                "binary reader encountered invalid access, "
                "dtype definition may not match gil layout"
            )

    def _create_fallback_dtype_node(self, field_id: int, code_type_value: int) -> DtypeNode:
        if code_type_value == CodeType.INT.value:
            value_type = DtypeValueType.INT
        elif code_type_value == CodeType.FLOAT.value:
            value_type = DtypeValueType.FLOAT
        else:
            value_type = DtypeValueType.UNKNOWN
        fallback_meta = DtypeFieldMeta(
            field_id=field_id,
            value_type=value_type,
            is_array=False,
            name="",
        )
        return DtypeNode(meta=fallback_meta)

    def _read_data_section(
        self,
        parent_data_node: JsonNode,
        parent_dtype_node: DtypeNode,
        reader: BinaryReader,
    ) -> None:
        while not reader.is_eof_or_error():
            field_offset = reader.offset
            child_data_offset = field_offset

            raw_field_id = reader.read_var_uint()
            code_type_value = raw_field_id & 7
            field_id = raw_field_id >> 3

            int_value: int = 0
            float_value: float = 0.0
            binary_value: bytes = b""

            if code_type_value == CodeType.INT.value:
                int_value = reader.read_var_uint()
            elif code_type_value == CodeType.DATA.value:
                data_length = reader.read_var_uint()
                child_data_offset = reader.offset
                binary_value = reader.read_bytes(data_length)
            elif code_type_value == CodeType.FLOAT.value:
                float_value = reader.read_float32()
            else:
                break

            if reader.is_error():
                break

            dtype_node = self.dtype_model.search_id(parent_dtype_node, field_id)
            if not dtype_node:
                dtype_node = self._create_fallback_dtype_node(field_id, code_type_value)

            field_meta = dtype_node.meta

            parent_for_value = parent_data_node
            existing_node = self.ugc_data.search_id(parent_data_node, field_id)

            # 若该字段已被提升为数组容器（例如同字段重复出现时自动升级），后续元素应直接追加到该容器，
            # 避免出现“数组套数组”的嵌套形态。
            if existing_node and existing_node.node_type == JsonNodeType.ARRAY:
                parent_for_value = existing_node
            elif existing_node and field_meta.is_array:
                parent_for_value = existing_node
            elif existing_node and not field_meta.is_array:
                array_container = self.ugc_data.push_back_array(
                    parent_data_node,
                    field_id,
                    field_meta.name,
                    field_offset,
                )
                parent_data_node.children.remove(existing_node)
                array_container.children.append(existing_node)
                parent_for_value = array_container
            elif field_meta.is_array:
                parent_for_value = self.ugc_data.push_back_array(
                    parent_data_node,
                    field_id,
                    field_meta.name,
                    field_offset,
                )

            if field_meta.value_type == DtypeValueType.UNKNOWN:
                self.ugc_data.push_back_data(
                    parent_for_value,
                    field_id,
                    field_meta.name,
                    binary_value,
                    field_offset,
                )
            elif field_meta.value_type == DtypeValueType.INT:
                self.ugc_data.push_back_int(
                    parent_for_value,
                    field_id,
                    field_meta.name,
                    int_value,
                    field_offset,
                )
            elif field_meta.value_type == DtypeValueType.FLOAT:
                self.ugc_data.push_back_float(
                    parent_for_value,
                    field_id,
                    field_meta.name,
                    float_value,
                    field_offset,
                )
            elif field_meta.value_type == DtypeValueType.STRING:
                decoded_string = binary_value.decode("utf-8", errors="replace")
                self.ugc_data.push_back_string(
                    parent_for_value,
                    field_id,
                    field_meta.name,
                    decoded_string,
                    field_offset,
                )
            elif field_meta.value_type == DtypeValueType.DATA:
                self.ugc_data.push_back_data(
                    parent_for_value,
                    field_id,
                    field_meta.name,
                    binary_value,
                    field_offset,
                )
            elif field_meta.value_type == DtypeValueType.OBJECT:
                child_object = self.ugc_data.push_back_object(
                    parent_for_value,
                    field_id,
                    field_meta.name,
                    field_offset,
                )
                if binary_value:
                    child_reader = BinaryReader(binary_value)
                    self._read_data_section(child_object, dtype_node, child_reader)


