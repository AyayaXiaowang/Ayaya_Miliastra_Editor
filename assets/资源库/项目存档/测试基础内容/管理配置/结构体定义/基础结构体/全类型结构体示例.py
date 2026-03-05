from __future__ import annotations

from typing import Any, Dict

STRUCT_ID = "4199981166"
STRUCT_TYPE = "basic"

STRUCT_PAYLOAD: Dict[str, Any] = {
    "type": "Struct",
    "struct_type": "basic",
    "struct_name": "全类型结构体示例",
    "fields": [
        {"field_name": "实体字段", "param_type": "实体", "default_value": {"param_type": "实体", "value": "0"}},
        {"field_name": "GUID字段", "param_type": "GUID", "default_value": {"param_type": "GUID", "value": "00000000"}},
        {"field_name": "整数字段", "param_type": "整数", "default_value": {"param_type": "整数", "value": "0"}},
        {"field_name": "布尔值字段", "param_type": "布尔值", "default_value": {"param_type": "布尔值", "value": "False"}},
        {"field_name": "浮点数字段", "param_type": "浮点数", "default_value": {"param_type": "浮点数", "value": "0.0"}},
        {"field_name": "字符串字段", "param_type": "字符串", "default_value": {"param_type": "字符串", "value": "示例字符串"}},
        {"field_name": "阵营字段", "param_type": "阵营", "default_value": {"param_type": "阵营", "value": "022"}},
        {"field_name": "三维向量字段", "param_type": "三维向量", "default_value": {"param_type": "三维向量", "value": "0,0,0"}},
        {"field_name": "元件ID字段", "param_type": "元件ID", "default_value": {"param_type": "元件ID", "value": "0"}},
        {"field_name": "配置ID字段", "param_type": "配置ID", "default_value": {"param_type": "配置ID", "value": "0"}},
        {
            "field_name": "结构体字段",
            "param_type": "结构体",
            "default_value": {
                "param_type": "结构体",
                "value": {"structId": "", "type": "Struct", "value": []},
            },
        },
        {
            "field_name": "字典字段",
            "param_type": "字典",
            "default_value": {
                "param_type": "字典",
                "value": {
                    "type": "Dict",
                    "key_type": "String",
                    "value_type": "String",
                    "value": [
                        {"key": {"param_type": "字符串", "value": "示例键111"}, "value": {"param_type": "字符串", "value": "示例值11"}},
                        {"key": {"param_type": "字符串", "value": "123123122"}, "value": {"param_type": "字符串", "value": "213212"}},
                    ],
                },
            },
        },
        {
            "field_name": "实体列表字段",
            "param_type": "实体列表",
            "default_value": {"param_type": "实体列表", "value": ["0", "123", "123", "123", "123123", "12"]},
        },
        {
            "field_name": "GUID列表字段",
            "param_type": "GUID列表",
            "default_value": {
                "param_type": "GUID列表",
                "value": [
                    "1073742153",
                    "1073742154",
                    "0",
                    "1",
                ],
            },
        },
        {"field_name": "整数列表字段", "param_type": "整数列表", "default_value": {"param_type": "整数列表", "value": ["1", "2", "3"]}},
        {"field_name": "布尔值列表字段", "param_type": "布尔值列表", "default_value": {"param_type": "布尔值列表", "value": ["True", "False"]}},
        {"field_name": "浮点数列表字段", "param_type": "浮点数列表", "default_value": {"param_type": "浮点数列表", "value": ["1.0", "2.5"]}},
        {"field_name": "字符串列表字段", "param_type": "字符串列表", "default_value": {"param_type": "字符串列表", "value": ["条目1", "条目2", "条目3"]}},
        {"field_name": "阵营列表字段", "param_type": "阵营列表", "default_value": {"param_type": "阵营列表", "value": ["0", "1"]}},
        {
            "field_name": "三维向量列表字段",
            "param_type": "三维向量列表",
            "default_value": {"param_type": "三维向量列表", "value": ["0,0,0", "1,2,3"]},
        },
        {"field_name": "元件ID列表字段", "param_type": "元件ID列表", "default_value": {"param_type": "元件ID列表", "value": ["0", "1"]}},
        {"field_name": "配置ID列表字段", "param_type": "配置ID列表", "default_value": {"param_type": "配置ID列表", "value": ["0", "1"]}},
        {
            "field_name": "结构体列表字段",
            "param_type": "结构体列表",
            "default_value": {"param_type": "结构体列表", "value": {"structId": "", "value": []}},
        },
    ],
}


