from __future__ import annotations

from pathlib import Path

from engine.validate.api import validate_files
from tests._helpers.project_paths import get_repo_root


def _workspace_root() -> Path:
    return get_repo_root()


def _write_code(tmp_dir: Path, filename: str, source: str) -> Path:
    target = tmp_dir / filename
    target.write_text(source, encoding="utf-8")
    return target


def test_composite_payload_virtual_pin_direction_mismatch_is_forbidden(tmp_path: Path) -> None:
    """payload 复合节点：虚拟引脚方向与 mapped_ports 方向不一致必须报错。"""
    composite_code = r'''
"""
composite_id: composite_pin_direction_payload_mismatch
composite_name: 复合_引脚方向策略_payload方向不一致报错
description: 用于验证 payload 复合节点 virtual_pins 的方向标记与 mapped_ports 必须一致
scope: server
"""

from engine.nodes.composite_spec import composite_class

COMPOSITE_PAYLOAD_FORMAT_VERSION = 1
COMPOSITE_PAYLOAD_JSON = r"""
{
  "composite_id": "composite_pin_direction_payload_mismatch",
  "node_name": "复合_引脚方向策略_payload方向不一致报错",
  "node_description": "",
  "scope": "server",
  "folder_path": "",
  "virtual_pins": [
    {
      "pin_index": 1,
      "pin_name": "数据输入_错误方向",
      "pin_type": "整数",
      "is_input": false,
      "is_flow": false,
      "description": "",
      "mapped_ports": [
        {
          "node_id": "node_dummy",
          "port_name": "值",
          "is_input": true,
          "is_flow": false
        }
      ]
    }
  ],
  "sub_graph": {
    "nodes": [],
    "edges": [],
    "graph_variables": []
  }
}
"""


@composite_class
class 复合_引脚方向策略_payload方向不一致报错:
    """stub"""

    pass
'''
    workspace = _workspace_root()
    path = _write_code(tmp_path, "composite_pin_direction_payload_mismatch.py", composite_code)

    report = validate_files([path], workspace, strict_entity_wire_only=False, use_cache=False)
    mismatch = [
        issue
        for issue in report.issues
        if issue.code == "COMPOSITE_VIRTUAL_PIN_MAPPING_DIRECTION_MISMATCH"
    ]
    assert mismatch, "payload 复合节点虚拟引脚方向与 mapped_ports.is_input 不一致必须报错"


def test_composite_class_data_in_and_data_out_same_name_is_forbidden(tmp_path: Path) -> None:
    """类格式复合节点：同名引脚不能同时作为数据入与数据出。"""
    composite_code = r'''
"""
composite_id: composite_pin_direction_class_conflict
composite_name: 复合_引脚方向策略_类格式同名数据入数据出报错
description: 用于验证类格式复合节点同名引脚不能同时声明为数据入与数据出
scope: server
"""

from runtime.engine.graph_prelude_server import *
from engine.nodes.composite_spec import composite_class, flow_entry


@composite_class
class 复合_引脚方向策略_类格式同名数据入数据出报错:
    @flow_entry()
    def 入口(self, 输入参数: "整数"):
        流程入("流程入")
        数据入("输入参数", pin_type="整数")
        数据出("输入参数", pin_type="整数")
        流程出("流程出")
        return 输入参数
'''
    workspace = _workspace_root()
    path = _write_code(tmp_path, "composite_pin_direction_class_conflict.py", composite_code)

    report = validate_files([path], workspace, strict_entity_wire_only=False, use_cache=False)
    conflict = [issue for issue in report.issues if issue.code == "COMPOSITE_PIN_DIRECTION_CONFLICT"]
    assert conflict, "类格式复合节点同名数据入+数据出必须报错"


def test_composite_class_data_output_passthrough_is_forbidden(tmp_path: Path) -> None:
    """类格式复合节点：数据出变量不允许直接透传自数据入/入口形参。"""
    composite_code = r'''
"""
composite_id: composite_pin_direction_class_passthrough
composite_name: 复合_引脚方向策略_类格式数据出透传报错
description: 用于验证类格式复合节点禁止“数据出变量=数据入/入口形参”的透传写法
scope: server
"""

from runtime.engine.graph_prelude_server import *
from engine.nodes.composite_spec import composite_class, flow_entry


@composite_class
class 复合_引脚方向策略_类格式数据出透传报错:
    @flow_entry()
    def 入口(self, 说明文本: "字符串"):
        流程入("流程入")
        数据入("说明文本", pin_type="字符串")
        数据出("描述回声", pin_type="字符串", variable="描述回声")
        流程出("流程出")

        描述回声 = 说明文本
        return 描述回声
'''
    workspace = _workspace_root()
    path = _write_code(tmp_path, "composite_pin_direction_class_passthrough.py", composite_code)

    report = validate_files([path], workspace, strict_entity_wire_only=False, use_cache=False)
    issues = [issue for issue in report.issues if issue.code == "COMPOSITE_DATA_OUTPUT_PASSTHROUGH_FORBIDDEN"]
    assert issues, "类格式复合节点数据出透传数据入必须报错"


