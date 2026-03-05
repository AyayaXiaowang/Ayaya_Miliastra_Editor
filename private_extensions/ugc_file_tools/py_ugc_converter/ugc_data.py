from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import base64


class JsonNodeType(Enum):
    NULL = "null"
    FALSE = "false"
    TRUE = "true"
    INT = "int"
    FLOAT = "float"
    STRING = "string"
    ARRAY = "array"
    OBJECT = "object"


class UgcValueType(Enum):
    UNKNOWN = "unknown"
    INT = "int"
    FLOAT = "float"
    STRING = "string"
    DATA = "data"
    ARRAY = "array"
    OBJECT = "object"


@dataclass
class UgcFieldMeta:
    field_id: int
    name: str
    value_type: UgcValueType
    binary_data: bytes
    offset: int


@dataclass
class JsonNode:
    key: str = ""
    node_type: JsonNodeType = JsonNodeType.NULL
    int_value: int = 0
    float_value: float = 0.0
    string_value: str = ""
    children: List["JsonNode"] = field(default_factory=list)
    metadata: Optional[UgcFieldMeta] = None


class UgcData:
    """對應 C++ 中 UgcData 的 Python 版本，只負責構建樹狀節點並轉成 JSON 可序列化結構。"""

    def __init__(self) -> None:
        self.root_node: JsonNode = JsonNode(node_type=JsonNodeType.OBJECT)

    def root(self) -> JsonNode:
        return self.root_node

    def _create_metadata(
        self,
        field_id: int,
        name: str,
        value_type: UgcValueType,
        offset: int,
        binary_data: bytes = b"",
    ) -> UgcFieldMeta:
        return UgcFieldMeta(
            field_id=field_id,
            name=name,
            value_type=value_type,
            binary_data=binary_data,
            offset=offset,
        )

    def push_back_int(
        self,
        parent_node: JsonNode,
        field_id: int,
        name: str,
        value: int,
        offset: int,
    ) -> JsonNode:
        metadata = self._create_metadata(field_id, name, UgcValueType.INT, offset)
        node = JsonNode(
            key=name,
            node_type=JsonNodeType.NULL,
            int_value=value,
            metadata=metadata,
        )
        parent_node.children.append(node)
        return node

    def push_back_float(
        self,
        parent_node: JsonNode,
        field_id: int,
        name: str,
        value: float,
        offset: int,
    ) -> JsonNode:
        metadata = self._create_metadata(field_id, name, UgcValueType.FLOAT, offset)
        node = JsonNode(
            key=name,
            node_type=JsonNodeType.NULL,
            float_value=value,
            metadata=metadata,
        )
        parent_node.children.append(node)
        return node

    def push_back_string(
        self,
        parent_node: JsonNode,
        field_id: int,
        name: str,
        value: str,
        offset: int,
    ) -> JsonNode:
        metadata = self._create_metadata(field_id, name, UgcValueType.STRING, offset)
        node = JsonNode(
            key=name,
            node_type=JsonNodeType.NULL,
            string_value=value,
            metadata=metadata,
        )
        parent_node.children.append(node)
        return node

    def push_back_data(
        self,
        parent_node: JsonNode,
        field_id: int,
        name: str,
        value: bytes,
        offset: int,
    ) -> JsonNode:
        metadata = self._create_metadata(
            field_id, name, UgcValueType.DATA, offset, binary_data=value
        )
        node = JsonNode(
            key=name,
            node_type=JsonNodeType.NULL,
            metadata=metadata,
        )
        parent_node.children.append(node)
        return node

    def push_back_array(
        self,
        parent_node: JsonNode,
        field_id: int,
        name: str,
        offset: int,
    ) -> JsonNode:
        metadata = self._create_metadata(field_id, name, UgcValueType.ARRAY, offset)
        node = JsonNode(
            key=name,
            node_type=JsonNodeType.ARRAY,
            children=[],
            metadata=metadata,
        )
        parent_node.children.append(node)
        return node

    def push_back_object(
        self,
        parent_node: JsonNode,
        field_id: int,
        name: str,
        offset: int,
    ) -> JsonNode:
        metadata = self._create_metadata(field_id, name, UgcValueType.OBJECT, offset)
        node = JsonNode(
            key=name,
            node_type=JsonNodeType.OBJECT,
            children=[],
            metadata=metadata,
        )
        parent_node.children.append(node)
        return node

    def search_id(self, parent_object_node: JsonNode, field_id: int) -> Optional[JsonNode]:
        for child_node in parent_object_node.children:
            if child_node.metadata and child_node.metadata.field_id == field_id:
                return child_node
        return None

    def prepare_for_json(self) -> None:
        self._prepare_node(self.root_node)

    def _prepare_node(self, node: JsonNode) -> None:
        if node.node_type in (JsonNodeType.ARRAY, JsonNodeType.OBJECT):
            for child_node in node.children:
                self._prepare_node(child_node)

        if node.metadata is None:
            return

        field_metadata = node.metadata
        key_parts = [str(field_metadata.field_id)]
        if field_metadata.name:
            key_parts.append(field_metadata.name)
        key_text = " ".join(key_parts)

        if field_metadata.value_type == UgcValueType.UNKNOWN:
            node.node_type = JsonNodeType.STRING
            node.string_value = base64.b64encode(field_metadata.binary_data).decode("ascii")
        elif field_metadata.value_type == UgcValueType.INT:
            key_text += "@int"
            node.node_type = JsonNodeType.INT
        elif field_metadata.value_type == UgcValueType.FLOAT:
            key_text += "@float"
            node.node_type = JsonNodeType.FLOAT
        elif field_metadata.value_type == UgcValueType.STRING:
            key_text += "@string"
            node.node_type = JsonNodeType.STRING
        elif field_metadata.value_type == UgcValueType.DATA:
            key_text += "@data"
            node.node_type = JsonNodeType.STRING
            node.string_value = base64.b64encode(field_metadata.binary_data).decode("ascii")
        # ARRAY 和 OBJECT 類型只需要覆蓋 key，保持原有 node_type

        node.key = key_text

    def to_python(self) -> Any:
        return self._node_to_python(self.root_node)

    def _node_to_python(self, node: JsonNode) -> Any:
        if node.node_type == JsonNodeType.NULL:
            return None
        if node.node_type == JsonNodeType.FALSE:
            return False
        if node.node_type == JsonNodeType.TRUE:
            return True
        if node.node_type == JsonNodeType.INT:
            return int(node.int_value)
        if node.node_type == JsonNodeType.FLOAT:
            return float(node.float_value)
        if node.node_type == JsonNodeType.STRING:
            return node.string_value
        if node.node_type == JsonNodeType.ARRAY:
            element_list: List[Any] = []
            for child_node in node.children:
                element_list.append(self._node_to_python(child_node))
            return element_list
        if node.node_type == JsonNodeType.OBJECT:
            mapping: Dict[str, Any] = {}
            for child_node in node.children:
                mapping[child_node.key] = self._node_to_python(child_node)
            return mapping
        return None


