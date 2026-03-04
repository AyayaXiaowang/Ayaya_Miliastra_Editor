from __future__ import annotations

from typing import Any, Dict


SAVE_POINT_ID = "ingame_template_sample_all_fields_01"


SAVE_POINT_PAYLOAD: Dict[str, Any] = {'save_point_id': 'ingame_template_sample_all_fields_01',
 'save_point_name': '示例_局内存档模板_全字段',
 'template_id': 'ingame_template_sample_all_fields_01',
 'template_name': '示例_局内存档模板_全字段',
 'description': '示例局内存档模板：用于对照 entries 结构、struct_id 引用与 max_length '
                '的含义；本示例使用“示例_局内存档_*”专用结构体，避免与业务结构体重名（注意数据量上限 10000 点）。',
 'entries': [{'struct_id': '示例_局内存档_基础信息',
              'max_length': 1,
              'index': '1',
              'data_amount': 0},
             {'struct_id': '示例_局内存档_资源账本',
              'max_length': 1,
              'index': '2',
              'data_amount': 0},
             {'struct_id': '示例_局内存档_状态标记',
              'max_length': 1,
              'index': '3',
              'data_amount': 0},
             {'struct_id': '示例_局内存档_收集汇总',
              'max_length': 1,
              'index': '4',
              'data_amount': 0},
             {'struct_id': '示例_局内存档_进度记录条目',
              'max_length': 2,
              'index': '5',
              'data_amount': 0},
             {'struct_id': '示例_局内存档_事件记录条目',
              'max_length': 3,
              'index': '6',
              'data_amount': 0}],
 'name': '示例_局内存档模板_全字段',
 'last_modified': '2025-12-18 12:20:00',
 'updated_at': '2025-12-18T12:20:00.000000',
 'metadata': {'category': '教学示例'},
 'is_default_template': False}

