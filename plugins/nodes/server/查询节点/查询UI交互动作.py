from __future__ import annotations

from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import resolve_ui_click_action_record_for_current_package


@node_spec(
    name="查询UI交互动作",
    category="查询节点",
    inputs=[("事件源GUID", "GUID")],
    outputs=[
        ("action_key", "字符串"),
        ("action_args", "字符串"),
        ("ui_key", "字符串"),
        ("widget_name", "字符串"),
    ],
    description=(
        "按当前打开的项目存档，从运行时缓存 `app/runtime/cache/ui_artifacts/<package_id>/ui_actions/*.ui_actions.json` "
        "中查询事件源GUID对应的动作标注。"
        "用于在节点图里用 action_key 做 match 分发，避免手写 GUID 分支。"
    ),
)
def 查询UI交互动作(game, 事件源GUID):
    record = resolve_ui_click_action_record_for_current_package(source_guid=int(事件源GUID))
    if record is None:
        return "", "", "", ""
    return record.action_key, record.action_args, record.ui_key, record.widget_name

