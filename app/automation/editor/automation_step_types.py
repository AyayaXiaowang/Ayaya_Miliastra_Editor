# -*- coding: utf-8 -*-
"""
自动化步骤类型常量（graph_*）与快速链配置。

设计目的：
- 统一步骤类型字符串，避免散落在多个模块里形成隐式耦合；
- 让 “哪些步骤允许进入 fast_chain（跳过等待）” 成为显式数据配置，
  而不是在执行器/步骤编排中到处硬编码。
"""

from __future__ import annotations


GRAPH_STEP_CREATE_NODE = "graph_create_node"
GRAPH_STEP_CONNECT = "graph_connect"
GRAPH_STEP_CREATE_AND_CONNECT = "graph_create_and_connect"
GRAPH_STEP_CONNECT_MERGED = "graph_connect_merged"
GRAPH_STEP_CONFIG_NODE_MERGED = "graph_config_node_merged"
GRAPH_STEP_SET_PORT_TYPES_MERGED = "graph_set_port_types_merged"
GRAPH_STEP_ADD_VARIADIC_INPUTS = "graph_add_variadic_inputs"
GRAPH_STEP_ADD_DICT_PAIRS = "graph_add_dict_pairs"
GRAPH_STEP_ADD_BRANCH_OUTPUTS = "graph_add_branch_outputs"
GRAPH_STEP_CONFIG_BRANCH_OUTPUTS = "graph_config_branch_outputs"
GRAPH_STEP_BIND_SIGNAL = "graph_bind_signal"


# 标记为“快速链可参与类型”的步骤集合：在执行器中用于决定是否跳过等待。
FAST_CHAIN_ELIGIBLE_STEP_TYPES: tuple[str, ...] = (
    GRAPH_STEP_CONNECT,
    GRAPH_STEP_CONNECT_MERGED,
    GRAPH_STEP_CREATE_AND_CONNECT,
    GRAPH_STEP_CONFIG_NODE_MERGED,
    GRAPH_STEP_SET_PORT_TYPES_MERGED,
    GRAPH_STEP_ADD_VARIADIC_INPUTS,
    GRAPH_STEP_ADD_DICT_PAIRS,
    GRAPH_STEP_ADD_BRANCH_OUTPUTS,
    GRAPH_STEP_CONFIG_BRANCH_OUTPUTS,
    GRAPH_STEP_BIND_SIGNAL,
)


