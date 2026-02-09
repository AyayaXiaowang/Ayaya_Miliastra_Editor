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


def test_composite_class_pin_type_generic_is_forbidden(tmp_path: Path) -> None:
    """类格式复合节点：任何对外引脚的 pin_type 只要仍是“占位泛型”，成品校验必须报错。"""
    composite_code = '''
"""
composite_id: composite_pin_type_policy_class_generic
composite_name: 复合_引脚类型策略_类格式泛型占位报错
description: 用于验证类格式复合节点的 pin_type 泛型占位在成品校验阶段必须报错
scope: server
"""

from runtime.engine.graph_prelude_server import *
from engine.nodes.composite_spec import composite_class, flow_entry


@composite_class
class 复合_引脚类型策略_类格式泛型占位报错:
    @flow_entry()
    def 入口(self, 输入参数):
        流程入()
        数据入("输入参数")  # pin_api 默认 pin_type="泛型"（未设置占位）
        流程出("流程出")
'''
    workspace = _workspace_root()
    path = _write_code(tmp_path, "composite_pin_type_policy_class_generic.py", composite_code)

    report = validate_files([path], workspace, strict_entity_wire_only=False, use_cache=False)
    forbidden = [issue for issue in report.issues if issue.code == "COMPOSITE_PIN_TYPE_FORBIDDEN"]
    assert forbidden, "类格式复合节点的对外引脚若仍为泛型占位，应被成品校验禁止"


def test_composite_payload_virtual_pin_generic_is_forbidden(tmp_path: Path) -> None:
    """payload 复合节点：virtual_pins 中若存在占位泛型类型，成品校验必须报错。"""
    composite_code = r'''
"""
composite_id: composite_pin_type_policy_payload_generic
composite_name: 复合_引脚类型策略_payload泛型占位报错
description: 用于验证 payload 复合节点的 virtual_pins 泛型占位在成品校验阶段必须报错
scope: server
"""

from engine.nodes.composite_spec import composite_class

COMPOSITE_PAYLOAD_FORMAT_VERSION = 1
COMPOSITE_PAYLOAD_JSON = r"""
{
  "composite_id": "composite_pin_type_policy_payload_generic",
  "node_name": "复合_引脚类型策略_payload泛型占位报错",
  "node_description": "",
  "scope": "server",
  "folder_path": "",
  "virtual_pins": [
    {
      "pin_index": 1,
      "pin_name": "流程入",
      "pin_type": "流程",
      "is_input": true,
      "is_flow": true,
      "description": "",
      "mapped_ports": []
    },
    {
      "pin_index": 2,
      "pin_name": "数据输入_未设置",
      "pin_type": "泛型",
      "is_input": true,
      "is_flow": false,
      "description": "",
      "mapped_ports": []
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
class 复合_引脚类型策略_payload泛型占位报错:
    """stub"""
    pass
'''
    workspace = _workspace_root()
    path = _write_code(tmp_path, "composite_pin_type_policy_payload_generic.py", composite_code)

    report = validate_files([path], workspace, strict_entity_wire_only=False, use_cache=False)
    forbidden = [issue for issue in report.issues if issue.code == "COMPOSITE_PIN_TYPE_FORBIDDEN"]
    assert forbidden, "payload 复合节点的 virtual_pins 若仍为泛型占位，应被成品校验禁止"


def test_composite_pin_type_any_alias_is_forbidden(tmp_path: Path) -> None:
    """Any/通用 旧别名必须报错。"""
    composite_code = r'''
"""
composite_id: composite_pin_type_policy_any_alias
composite_name: 复合_引脚类型策略_Any旧别名报错
description: 用于验证 Any/通用 旧别名在成品校验阶段必须报错
scope: server
"""

from engine.nodes.composite_spec import composite_class

COMPOSITE_PAYLOAD_FORMAT_VERSION = 1
COMPOSITE_PAYLOAD_JSON = r"""
{
  "composite_id": "composite_pin_type_policy_any_alias",
  "node_name": "复合_引脚类型策略_Any旧别名报错",
  "node_description": "",
  "scope": "server",
  "folder_path": "",
  "virtual_pins": [
    {
      "pin_index": 1,
      "pin_name": "流程入",
      "pin_type": "流程",
      "is_input": true,
      "is_flow": true,
      "description": "",
      "mapped_ports": []
    },
    {
      "pin_index": 2,
      "pin_name": "数据输入_旧别名",
      "pin_type": "Any",
      "is_input": true,
      "is_flow": false,
      "description": "",
      "mapped_ports": []
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
class 复合_引脚类型策略_Any旧别名报错:
    """stub"""
    pass
'''
    workspace = _workspace_root()
    path = _write_code(tmp_path, "composite_pin_type_policy_any_alias.py", composite_code)

    report = validate_files([path], workspace, strict_entity_wire_only=False, use_cache=False)
    forbidden = [issue for issue in report.issues if issue.code == "COMPOSITE_PIN_TYPE_FORBIDDEN"]
    assert forbidden, "Any/通用 旧别名必须被成品校验禁止"


def test_composite_pin_type_python_builtin_is_forbidden(tmp_path: Path) -> None:
    """Python 内置类型名必须报错（payload 路径可直接观测原始 pin_type）。"""
    composite_code = r'''
"""
composite_id: composite_pin_type_policy_python_builtin
composite_name: 复合_引脚类型策略_Python内置类型名报错
description: 用于验证 int/float/str/bool/list/dict 在成品校验阶段必须报错
scope: server
"""

from engine.nodes.composite_spec import composite_class

COMPOSITE_PAYLOAD_FORMAT_VERSION = 1
COMPOSITE_PAYLOAD_JSON = r"""
{
  "composite_id": "composite_pin_type_policy_python_builtin",
  "node_name": "复合_引脚类型策略_Python内置类型名报错",
  "node_description": "",
  "scope": "server",
  "folder_path": "",
  "virtual_pins": [
    {
      "pin_index": 1,
      "pin_name": "流程入",
      "pin_type": "流程",
      "is_input": true,
      "is_flow": true,
      "description": "",
      "mapped_ports": []
    },
    {
      "pin_index": 2,
      "pin_name": "数据输入_int",
      "pin_type": "int",
      "is_input": true,
      "is_flow": false,
      "description": "",
      "mapped_ports": []
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
class 复合_引脚类型策略_Python内置类型名报错:
    """stub"""
    pass
'''
    workspace = _workspace_root()
    path = _write_code(tmp_path, "composite_pin_type_policy_python_builtin.py", composite_code)

    report = validate_files([path], workspace, strict_entity_wire_only=False, use_cache=False)
    forbidden = [issue for issue in report.issues if issue.code == "COMPOSITE_PIN_TYPE_FORBIDDEN"]
    assert forbidden, "Python 内置类型名必须被成品校验禁止"


