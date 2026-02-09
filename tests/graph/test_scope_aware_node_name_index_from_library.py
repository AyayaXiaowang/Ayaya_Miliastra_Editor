from __future__ import annotations

from engine.graph.common import node_name_index_from_library
from engine.nodes.node_registry import get_node_registry

from tests._helpers.project_paths import get_repo_root


def _load_node_library() -> dict:
    repo_root = get_repo_root()
    registry = get_node_registry(repo_root, include_composite=True)
    return registry.get_library()


def test_node_name_index_scope_mapping_points_to_available_defs() -> None:
    """
    回归：scope-aware 的 node_name_index 必须保证：
    - 对任意 scope（server/client），索引指向的 NodeDef 必须在该 scope 下可用；
    - 避免 client 图误解析到 server 版本节点（端口不兼容时会导致 UI 连线缺失）。
    """
    node_library = _load_node_library()
    assert isinstance(node_library, dict) and node_library

    for scope in ("server", "client"):
        index = node_name_index_from_library(node_library, scope=scope)
        assert isinstance(index, dict) and index

        for node_name, node_key in index.items():
            node_def = node_library.get(node_key)
            assert node_def is not None, f"node_name_index 指向不存在的 key: name={node_name}, key={node_key}"
            assert (
                node_def.is_available_in_scope(scope)
            ), f"node_name_index 作用域映射错误: scope={scope}, name={node_name}, key={node_key}, scopes={getattr(node_def, 'scopes', None)}"


def test_critical_client_nodes_resolve_to_expected_ports() -> None:
    """
    回归：若 server/client 同名节点端口不兼容（会生成 #scope 变体），
    则 client scope 下的索引必须指向 client 变体，且端口命名与语法糖/图代码一致。
    """
    node_library = _load_node_library()
    client_index = node_name_index_from_library(node_library, scope="client")
    server_index = node_name_index_from_library(node_library, scope="server")

    # math.radians / math.degrees 语法糖依赖
    angle_to_radian_key = client_index.get("角度转弧度")
    assert isinstance(angle_to_radian_key, str) and angle_to_radian_key
    angle_to_radian_def = node_library[angle_to_radian_key]
    assert "角度" in (angle_to_radian_def.inputs or [])
    assert "弧度" in (angle_to_radian_def.outputs or [])
    assert angle_to_radian_def.get_port_type("角度", True) == "浮点数"
    assert angle_to_radian_def.get_port_type("弧度", False) == "浮点数"

    radian_to_angle_key = client_index.get("弧度转角度")
    assert isinstance(radian_to_angle_key, str) and radian_to_angle_key
    radian_to_angle_def = node_library[radian_to_angle_key]
    assert "弧度" in (radian_to_angle_def.inputs or [])
    assert "角度" in (radian_to_angle_def.outputs or [])
    assert radian_to_angle_def.get_port_type("弧度", True) == "浮点数"
    assert radian_to_angle_def.get_port_type("角度", False) == "浮点数"

    # server 侧端口名不同：确保 server scope 下不会映射到 client 端口名
    angle_to_radian_server_key = server_index.get("角度转弧度")
    assert isinstance(angle_to_radian_server_key, str) and angle_to_radian_server_key
    angle_to_radian_server_def = node_library[angle_to_radian_server_key]
    assert "角度值" in (angle_to_radian_server_def.inputs or [])
    assert "弧度值" in (angle_to_radian_server_def.outputs or [])

    radian_to_angle_server_key = server_index.get("弧度转角度")
    assert isinstance(radian_to_angle_server_key, str) and radian_to_angle_server_key
    radian_to_angle_server_def = node_library[radian_to_angle_server_key]
    assert "弧度值" in (radian_to_angle_server_def.inputs or [])
    assert "角度值" in (radian_to_angle_server_def.outputs or [])

    # 设置局部变量：server/client 端口不兼容
    set_local_var_client_key = client_index.get("设置局部变量")
    assert isinstance(set_local_var_client_key, str) and set_local_var_client_key
    set_local_var_client_def = node_library[set_local_var_client_key]
    assert "变量名" in (set_local_var_client_def.inputs or [])
    assert "变量值" in (set_local_var_client_def.inputs or [])

    set_local_var_server_key = server_index.get("设置局部变量")
    assert isinstance(set_local_var_server_key, str) and set_local_var_server_key
    set_local_var_server_def = node_library[set_local_var_server_key]
    assert "局部变量" in (set_local_var_server_def.inputs or [])
    assert "值" in (set_local_var_server_def.inputs or [])

    # 基础算术节点：语法糖/图代码依赖 `左值/右值 -> 结果`
    for op_name in ("减法运算", "乘法运算", "除法运算"):
        op_key = client_index.get(op_name)
        assert isinstance(op_key, str) and op_key, f"client scope 缺少节点: {op_name}"
        op_def = node_library[op_key]
        assert "左值" in (op_def.inputs or []), f"{op_name} 缺少输入端口: 左值"
        assert "右值" in (op_def.inputs or []), f"{op_name} 缺少输入端口: 右值"
        assert "结果" in (op_def.outputs or []), f"{op_name} 缺少输出端口: 结果"


