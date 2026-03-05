from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import json
import os


class DtypeValueType(Enum):
    UNKNOWN = "unknown"
    INT = "int"
    FLOAT = "float"
    STRING = "string"
    DATA = "data"
    OBJECT = "object"


@dataclass
class DtypeFieldMeta:
    field_id: int
    value_type: DtypeValueType
    is_array: bool
    name: str


@dataclass
class DtypeNode:
    meta: DtypeFieldMeta
    children: List["DtypeNode"] = field(default_factory=list)


class DtypeModel:
    """對應 C++ 中 Dtype 的 Python 版本，只做讀取和查詢，不自動寫回 dtype.json。"""

    def __init__(self) -> None:
        root_meta = DtypeFieldMeta(
            field_id=0,
            value_type=DtypeValueType.OBJECT,
            is_array=False,
            name="",
        )
        self.root_node: DtypeNode = DtypeNode(meta=root_meta)

    def load_from_file(self, file_path: str) -> None:
        absolute_path = os.path.abspath(file_path)
        with open(absolute_path, "r", encoding="utf-8") as input_file:
            json_object = json.load(input_file)
        self._build_tree_from_object(self.root_node, json_object)

    def _build_tree_from_object(self, parent_node: DtypeNode, json_object: Dict[str, Any]) -> None:
        for key_string, value in json_object.items():
            child_node = self._create_node_from_entry(key_string, value)
            parent_node.children.append(child_node)
            if isinstance(value, dict):
                self._build_tree_from_object(child_node, value)

    def _create_node_from_entry(self, key_string: str, value: Any) -> DtypeNode:
        field_id, is_array, first_token, second_token = self._parse_key_string(key_string)

        if isinstance(value, dict):
            value_type = DtypeValueType.OBJECT
            name = first_token if first_token is not None else ""
        else:
            type_token = ""
            name = ""
            if second_token is not None:
                type_token = first_token if first_token is not None else ""
                name = second_token
            elif first_token is not None:
                type_token = first_token
            lower_type_token = type_token.lower()
            if lower_type_token == "int":
                value_type = DtypeValueType.INT
            elif lower_type_token == "float":
                value_type = DtypeValueType.FLOAT
            elif lower_type_token in ("str", "string"):
                value_type = DtypeValueType.STRING
            elif lower_type_token == "data":
                value_type = DtypeValueType.DATA
            else:
                value_type = DtypeValueType.UNKNOWN

        field_meta = DtypeFieldMeta(
            field_id=field_id,
            value_type=value_type,
            is_array=is_array,
            name=name,
        )
        return DtypeNode(meta=field_meta)

    def _parse_key_string(self, key_string: str) -> Tuple[int, bool, Optional[str], Optional[str]]:
        index: int = 0
        length: int = len(key_string)
        while index < length and key_string[index].isdigit():
            index += 1
        if index == 0:
            raise ValueError(f"dtype key does not start with digit: {key_string}")
        field_id_text = key_string[:index]
        field_id = int(field_id_text)

        is_array: bool = False
        first_token: Optional[str] = None
        second_token: Optional[str] = None

        while index < length:
            while index < length and key_string[index].isspace():
                index += 1
            if index >= length:
                break
            if (
                key_string[index] == "["
                and index + 1 < length
                and key_string[index + 1] == "]"
            ):
                is_array = True
                index += 2
                continue
            token_start = index
            while index < length and not key_string[index].isspace() and key_string[index] != "[":
                index += 1
            token_value = key_string[token_start:index]
            if not first_token:
                first_token = token_value
            elif not second_token:
                second_token = token_value
            else:
                raise ValueError(f"dtype key has too many parts: {key_string}")

        return field_id, is_array, first_token, second_token

    def search_id(self, parent_node: DtypeNode, field_id: int) -> Optional[DtypeNode]:
        for child_node in parent_node.children:
            if child_node.meta.field_id == field_id:
                return child_node
        return None

    def search_name(self, parent_node: DtypeNode, field_name: str) -> Optional[DtypeNode]:
        for child_node in parent_node.children:
            if child_node.meta.name == field_name:
                return child_node
        return None


