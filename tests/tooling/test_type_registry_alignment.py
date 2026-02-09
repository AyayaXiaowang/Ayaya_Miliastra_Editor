from __future__ import annotations

from engine.configs.components.variable_configs import VariableDataType
from engine.configs.specialized.node_graph_configs import (
    BASIC_STRUCT_SUPPORTED_TYPES as CONFIG_BASIC_STRUCT_SUPPORTED_TYPES,
    INGAME_SAVE_STRUCT_SUPPORTED_TYPES as CONFIG_INGAME_SAVE_STRUCT_SUPPORTED_TYPES,
)
from engine.graph.models.entity_templates import VARIABLE_TYPES as UI_VARIABLE_TYPES
from engine.nodes.port_type_system import FLOW_PORT_TYPE, GENERIC_PORT_TYPE
from engine.type_registry import (
    BASE_TYPES,
    BASIC_STRUCT_SUPPORTED_TYPES,
    INGAME_SAVE_STRUCT_SUPPORTED_TYPES,
    LIST_TYPES,
    TYPE_CAMP,
    TYPE_CAMP_LIST,
    TYPE_DICT,
    TYPE_FLOW,
    TYPE_GENERIC,
    TYPE_GUID_LIST,
    TYPE_STRING,
    TYPE_CONVERSIONS,
    VARIABLE_TYPES,
    parse_typed_dict_alias,
)


def test_datatype_rules_are_single_source_of_truth() -> None:
    import engine.configs.rules.datatype_rules as cfg
    import engine.validate.rules.datatype_rules as val

    assert cfg.BASE_TYPES is BASE_TYPES
    assert cfg.LIST_TYPES is LIST_TYPES
    assert cfg.TYPE_CONVERSIONS is TYPE_CONVERSIONS

    assert val.BASE_TYPES is BASE_TYPES
    assert val.LIST_TYPES is LIST_TYPES
    assert val.TYPE_CONVERSIONS is TYPE_CONVERSIONS


def test_variable_types_align_with_registry() -> None:
    assert tuple(UI_VARIABLE_TYPES) == VARIABLE_TYPES
    assert len(UI_VARIABLE_TYPES) == len(set(UI_VARIABLE_TYPES))


def test_struct_supported_types_align_with_registry() -> None:
    assert tuple(CONFIG_BASIC_STRUCT_SUPPORTED_TYPES) == BASIC_STRUCT_SUPPORTED_TYPES
    assert tuple(CONFIG_INGAME_SAVE_STRUCT_SUPPORTED_TYPES) == INGAME_SAVE_STRUCT_SUPPORTED_TYPES
    assert TYPE_DICT in BASIC_STRUCT_SUPPORTED_TYPES
    assert TYPE_DICT not in INGAME_SAVE_STRUCT_SUPPORTED_TYPES


def test_camp_types_are_present_everywhere() -> None:
    assert TYPE_CAMP in BASE_TYPES
    assert TYPE_CAMP_LIST in LIST_TYPES
    assert TYPE_CAMP in VARIABLE_TYPES
    assert TYPE_CAMP_LIST in VARIABLE_TYPES
    assert TYPE_CAMP in BASIC_STRUCT_SUPPORTED_TYPES
    assert TYPE_CAMP_LIST in BASIC_STRUCT_SUPPORTED_TYPES


def test_parse_typed_dict_alias_is_consistent() -> None:
    ok1, key1, value1 = parse_typed_dict_alias(f"{TYPE_STRING}_{TYPE_GUID_LIST}{TYPE_DICT}")
    assert ok1
    assert key1 == TYPE_STRING
    assert value1 == TYPE_GUID_LIST

    ok2, key2, value2 = parse_typed_dict_alias(f"{TYPE_STRING}-{TYPE_GUID_LIST}{TYPE_DICT}")
    assert ok2
    assert key2 == TYPE_STRING
    assert value2 == TYPE_GUID_LIST

    ok3, _, _ = parse_typed_dict_alias(TYPE_DICT)
    assert not ok3


def test_variable_data_type_enum_aligns_with_registry() -> None:
    values = {member.value for member in VariableDataType if member is not VariableDataType.DICT_ALL}
    assert values == (set(VARIABLE_TYPES) - {TYPE_DICT})
    assert VariableDataType.DICT_ALL.to_canonical_type_name() == TYPE_DICT


def test_port_type_constants_align_with_registry() -> None:
    assert FLOW_PORT_TYPE == TYPE_FLOW
    assert GENERIC_PORT_TYPE == TYPE_GENERIC


