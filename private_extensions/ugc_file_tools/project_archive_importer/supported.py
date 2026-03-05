from __future__ import annotations

from typing import Any, Dict, List


def get_supported_importers() -> Dict[str, Dict[str, Any]]:
    """
    返回“目前支持从项目存档导入到 .gil”的能力清单。

    约定：
    - 这里只描述“我们明确闭环验证过/已实现的导入能力”；
    - 未支持的类型不要写在这里，避免误导用户。
    """
    return {
        "templates": {
            "name": "元件库模板（TemplateConfig）",
            "source_paths": [
                "元件库/*.json（排除 templates_index.json）",
            ],
            "writes_to_gil": [
                "root4/4/1 (template entries)",
                "root4/4 (template section)",
                "root4/4/1[*].8 (template custom variables groups; group1 -> group_item['11']['1'])",
                "root4/6/1 (template tabs/index registry)",
            ],
            "notes": [
                "写回策略为 overwrite/merge：overwrite 仅覆盖模板“名称”（meta id=1）；merge 则目标已存在同 template_id 时跳过。",
                "默认跳过占位模板（metadata.ugc.placeholder=true），避免把非真源模板写回导致导入失败；如确有需要仅通过 CLI --include-placeholder-templates 显式开启（不推荐）。",
                "新增模板当前采用“按 type_code 克隆一条同类模板 entry”策略，仅保证最小可识别；不承诺完整模板语义闭环。",
                "当模板 JSON 的 metadata.custom_variable_file 引用变量文件（VARIABLE_FILE_ID）时，会加载对应 LEVEL_VARIABLES 并写回模板自定义变量 group1（对齐真源：group_item['11'] 从 empty bytes 变为 message，field '1' 为 variable_item 列表）。",
                "为保证编辑器内“未分类页签/元件列表”稳定可见：写回时会把本次触及到的模板 ID 注册到 root4/6 的索引表（kind=100/400）。",
            ],
        },
        "instances": {
            "name": "实体摆放（InstanceConfig）",
            "source_paths": [
                "实体摆放/*.json（排除 instances_index.json 与 自研_*）",
            ],
            "writes_to_gil": [
                "root4/5/1 (instance entries)",
                "root4/5 (instance section)",
                "root4/5/1[*].7 (instance custom variables groups; group1 -> group_item['11']['1'])",
            ],
            "notes": [
                "写回策略为 overwrite/merge：overwrite 覆盖 name/template_id/transform(position/rotation/scale/guid) 与 entry['8'](template_type)；merge 则目标已存在同 instance_id 时跳过。",
                "默认不新增缺失 instance_id（避免写回不完整 entry 导致导入失败）；可在 UI 中显式开启“克隆 entry 以新增”。",
                "当实体摆放 JSON 的 metadata.custom_variable_file 引用变量文件（VARIABLE_FILE_ID）时，会加载对应 LEVEL_VARIABLES 并写回实例自定义变量 group1（跳过 is_level_entity=true 的关卡实体，避免与“关卡变量同步”流程重复）。",
            ],
        },
        "signals": {
            "name": "信号定义",
            "source_paths": [
                "管理配置/信号/**/*.py（代码级资源：SIGNAL_ID / SIGNAL_PAYLOAD）",
                "（共享）Graph_Generater/assets/资源库/共享/管理配置/信号/**/*.py",
            ],
            "writes_to_gil": [
                "root4/10/5/3 (signal entries)",
                "root4/10/2 (signal node defs)",
                "root4/10/5/2 (signal node_def meta index)",
            ],
            "notes": [
                "导入范围对齐 Graph_Generater：共享根 + 当前项目存档根（项目可覆盖共享同 ID 定义）。",
                "约束对齐 Graph_Generater：信号参数类型禁止使用字典（含别名字典）。",
                "导入策略为 merge：目标存档已存在同名信号则跳过，不覆盖。",
            ],
        },
        "struct_definitions": {
            "name": "结构体定义",
            "source_paths": [
                "管理配置/结构体定义/原始解析/struct_def_*.decoded.json",
            ],
            "writes_to_gil": [
                "root4/10/6 (struct definition blobs)",
                "root4/10/2 (struct node defs: 拼装/拆分/修改结构体)",
                "root4/6/1[22] (struct tabs registration)",
            ],
            "notes": [
                "依赖项目存档中存在原始解析的 decoded-json；若缺失则无法导入。",
                "新增结构体会自动分配新的 node_type_id（避免与既有节点类型冲突）。",
            ],
        },
        "ingame_save_structs": {
            "name": "局内存档结构体定义",
            "source_paths": [
                "管理配置/结构体定义/局内存档结构体/*.py",
                "（共享）Graph_Generater/assets/资源库/共享/管理配置/结构体定义/局内存档结构体/*.py",
            ],
            "writes_to_gil": [
                "root4/10/6 (struct definition blobs, 强制写为 ingame_save: struct_message.field_2.int=2)",
                "root4/10/2 (struct node defs: 拼装/拆分/修改结构体)",
            ],
            "notes": [
                "支持两种 STRUCT_PAYLOAD schema：{type:'Struct',...} 与 {type:'结构体',...}（教学示例旧版）。",
                "当前不写回结构体页签注册（root4/6/*）；若目标存档依赖页签可见性，请自行补齐或改用 decoded-json 导入流程。",
            ],
        },
        "node_graphs": {
            "name": "节点图（GraphModel → .gil）",
            "source_paths": [
                "节点图/**.py（Graph Code；从 docstring metadata 提取 graph_id / graph_name）",
                "（可选）<package>总览.json（仅当选择 overview 模式时）",
            ],
            "writes_to_gil": [
                "root4/10 (节点图段：groups/entries/nodes/edges/graph_variables)",
            ],
            "notes": [
                "导入策略为“写回新增图 entry”：默认按 graph_id 中的 10 位 graph_id_int 写回；缺失时会自动分配新的 graph_id_int（按 scope mask：server=0x40000000，client=0x40800000）。",
                "写回依赖模板样本库（template_gil + template_library_dir）提供节点/record 样本；模板覆盖不足会直接抛错。",
                "scope 优先从 Graph Code 所在目录推断（/节点图/server 或 /节点图/client）。",
            ],
        },
        "ui_widget_templates": {
            "name": "界面控件组模板（UI控件模板）",
            "source_paths": [
                "管理配置/UI控件模板/*.json（排除 ui_widget_templates_index.json）",
                "管理配置/UI控件模板/原始解析/ugc_ui_widget_template_*.raw.json（用于写回）",
            ],
            "writes_to_gil": [
                "root4/9/501[0] (layout registry varint stream)",
                "root4/9/502 (UI record list)",
            ],
            "notes": [
                "当前以“控件组模板 root（meta14）+ children records”为闭环最小集，写回时会把 root 注册到 layout registry，并把 records 插入 UI record list。",
                "merge：目标已存在同 template_root_guid 时跳过；overwrite：覆盖目标同 guid 的 root record。",
                "当新增模板且 children guid 与目标冲突时，会自动为冲突 children 分配新 guid，并同步更新 root 的 children 列表。",
            ],
        },
    }


def list_supported_importer_keys() -> List[str]:
    return sorted(get_supported_importers().keys())


