# -*- coding: utf-8 -*-
"""
Todo 详情渲染器

职责：
- 将 TodoItem.detail_info 渲染为 HTML 字符串
- 样式、命名映射来源于 todo_config 与 theme_manager

说明：
- 依赖回调获取统计/汇总信息，避免直接耦合 UI 组件内部结构
"""

from __future__ import annotations
from typing import Callable, List, Dict

from ui.todo.todo_config import TodoStyles, CombatTypeNames, ManagementTypeNames
from engine.configs.rules import COMPONENT_DEFINITIONS


class TodoDetailRenderer:
    def __init__(
        self,
        build_table: Callable[[List[str], List[List[str]]], str],
        collect_categories_info: Callable[[object], Dict[str, list]],
        collect_category_items: Callable[[object], list],
        collect_template_summary: Callable[[object], Dict[str, int]],
        collect_instance_summary: Callable[[object], Dict[str, int]],
    ) -> None:
        self._build_table = build_table
        self._collect_categories_info = collect_categories_info
        self._collect_category_items = collect_category_items
        self._collect_template_summary = collect_template_summary
        self._collect_instance_summary = collect_instance_summary

    def format_detail_html(self, todo) -> str:
        info = todo.detail_info
        detail_type = info.get("type", "")

        html = TodoStyles.HTML_BASE_STYLE

        if detail_type == "root":
            html += f"<h3>{info.get('package_name', '存档')}</h3>"
            if todo.description:
                html += f"<p>{todo.description}</p>"
            html += "<h4>配置概览</h4>"
            categories_info = self._collect_categories_info(todo)
            if categories_info:
                for cat_name, cat_items in categories_info.items():
                    html += f"<p><b>{cat_name}：</b>{len(cat_items)} 项</p>"
                    if cat_items:
                        html += "<table>"
                        html += "<tr><th>名称</th><th>类型/说明</th></tr>"
                        for item_name, item_type in cat_items[:10]:
                            html += f"<tr><td>{item_name}</td><td>{item_type}</td></tr>"
                        if len(cat_items) > 10:
                            html += f"<tr><td colspan='2' style='text-align: center; color: #999;'>...还有 {len(cat_items) - 10} 项</td></tr>"
                        html += "</table>"

        elif detail_type == "category":
            count = info.get('count', 0)
            category = info.get('category', '')
            html += f"<h3>{todo.title}</h3>"
            html += f"<p>共 {count} 项配置任务</p>"
            category_items = self._collect_category_items(todo)
            if category_items:
                if category == "standalone_graphs":
                    html += "<table>"
                    html += "<tr><th>节点图名称</th><th>类型</th><th>变量数</th><th>节点数</th><th>文件夹</th></tr>"
                    for item_info in category_items:
                        name = item_info.get('name', '-')
                        gtype = item_info.get('graph_type', '')
                        type_text = "服务器" if gtype == "server" else ("客户端" if gtype == "client" else gtype)
                        var_count = item_info.get('variable_count', 0)
                        node_count = item_info.get('node_count', 0)
                        folder = item_info.get('folder_path', '') or "-"
                        html += f"<tr><td><b>{name}</b></td><td>{type_text}</td><td>{var_count}</td><td>{node_count}</td><td>{folder}</td></tr>"
                    html += "</table>"
                else:
                    html += "<table>"
                    if category == "templates":
                        html += "<tr><th>元件名称</th><th>实体类型</th><th>配置项</th></tr>"
                        for item_info in category_items:
                            config_summary = item_info.get('config_summary', '')
                            html += f"<tr><td><b>{item_info['name']}</b></td><td>{item_info['entity_type']}</td><td>{config_summary}</td></tr>"
                    elif category == "instances":
                        html += "<tr><th>实体名称</th><th>基于元件</th><th>配置项</th></tr>"
                        for item_info in category_items:
                            config_summary = item_info.get('config_summary', '')
                            html += f"<tr><td><b>{item_info['name']}</b></td><td>{item_info.get('template_name', '-')}</td><td>{config_summary}</td></tr>"
                    elif category in ["combat", "management"]:
                        html += "<tr><th>名称</th><th>类型</th></tr>"
                        for item_info in category_items:
                            html += f"<tr><td><b>{item_info['name']}</b></td><td>{item_info.get('type', '-')}</td></tr>"
                    html += "</table>"

        elif detail_type == "template":
            html += f"<h3>{info.get('name', '元件')}</h3>"
            html += f"<p><b>实体类型：</b>{info.get('entity_type', '')}</p>"
            if info.get('description'):
                html += f"<p>{info.get('description', '')}</p>"
            template_summary = self._collect_template_summary(todo)
            if template_summary:
                html += "<h4>配置清单</h4>"
                html += "<table>"
                html += "<tr><th>配置项</th><th>数量</th></tr>"
                for config_type, count in template_summary.items():
                    html += f"<tr><td>{config_type}</td><td><b>{count}</b></td></tr>"
                html += "</table>"

        elif detail_type == "template_basic":
            html += "<h3>基础属性配置</h3>"
            config = info.get('config', {})
            if config:
                headers = ["属性", "值"]
                rows = [[key, f"<code>{value}</code>"] for key, value in config.items()]
                html += self._build_table(headers, rows)

        elif detail_type == "template_variables_table":
            html += "<h3>配置自定义变量</h3>"
            variables = info.get('variables', [])
            if variables:
                headers = ["变量名", "类型", "默认值", "说明"]
                rows = []
                for var in variables:
                    desc = var.get('description', '') or '-'
                    rows.append([
                        f"<b>{var.get('name', '')}</b>",
                        f"<code>{var.get('variable_type', '')}</code>",
                        var.get('default_value', ''),
                        desc,
                    ])
                html += self._build_table(headers, rows)

        elif detail_type == "graph_variables_table":
            html += "<h3>配置节点图变量</h3>"
            html += "<p style='color: #A0A0A0; font-size: 10pt; margin: 5px 0;'>节点图变量是生命周期跟随节点图的局部变量，仅在当前节点图内可访问。</p>"
            variables = info.get('variables', [])
            if variables:
                headers = ["变量名", "类型", "默认值", "对外暴露", "说明"]
                rows = []
                for var in variables:
                    desc = var.get('description', '') or '-'
                    is_exposed = var.get('is_exposed', False)
                    # 统一显示为“√/X”，不留空
                    exposed_text = "√" if is_exposed else "X"
                    exposed_style = "color: #4CAF50; font-weight: bold;" if is_exposed else "color: #D32F2F; font-weight: bold;"
                    display_value = var.get('display_value', var.get('default_value', ''))
                    rows.append([
                        f"<b>{var.get('name', '')}</b>",
                        f"<code>{var.get('variable_type', '')}</code>",
                        f"<code>{display_value}</code>",
                        f"<span style='{exposed_style}'>" + exposed_text + "</span>",
                        desc,
                    ])
                html += self._build_table(headers, rows)

        elif detail_type == "template_components_table":
            html += "<h3>添加组件</h3>"
            components = info.get('components', [])
            if components:
                html += "<table>"
                html += "<tr><th>组件类型</th><th>说明</th></tr>"
                for comp in components:
                    component_type = comp.get('component_type', '')
                    definition = COMPONENT_DEFINITIONS.get(component_type, {})
                    desc_text = str(
                        comp.get('description')
                        or definition.get("description")
                        or ""
                    ).strip() or "-"
                    html += f"<tr><td><b>{component_type}</b></td><td>{desc_text}</td></tr>"
                    settings = comp.get('settings', {})
                    if settings:
                        html += f"<tr><td colspan='2'><div style='margin-left: 20px; font-size: 10pt; color: #666;'>"
                        for key, value in settings.items():
                            html += f"{key}: <code>{value}</code><br>"
                        html += "</div></td></tr>"
                html += "</table>"

        elif detail_type == "instance":
            html += f"<h3>{info.get('name', '实体')}</h3>"
            html += f"<p><b>基于元件：</b>{info.get('template_name', '')}</p>"
            instance_summary = self._collect_instance_summary(todo)
            if instance_summary:
                html += "<h4>配置清单</h4>"
                html += "<table>"
                html += "<tr><th>配置项</th><th>数量</th></tr>"
                for config_type, count in instance_summary.items():
                    html += f"<tr><td>{config_type}</td><td><b>{count}</b></td></tr>"
                html += "</table>"

        elif detail_type == "instance_properties_table":
            html += "<h3>配置实体属性</h3>"
            pos = info.get('position', [0, 0, 0])
            html += "<p><b>位置：</b></p>"
            html += self._build_table(["X", "Y", "Z"], [[f"{pos[0]:.2f}", f"{pos[1]:.2f}", f"{pos[2]:.2f}"]])
            rot = info.get('rotation', [0, 0, 0])
            html += "<p><b>旋转：</b></p>"
            html += self._build_table(["Pitch", "Yaw", "Roll"], [[f"{rot[0]:.2f}°", f"{rot[1]:.2f}°", f"{rot[2]:.2f}°"]])
            override_vars = info.get('override_variables', [])
            if override_vars:
                html += "<p><b>覆盖变量：</b></p>"
                rows = [[f"<b>{var.get('name', '')}</b>", var.get('value', '')] for var in override_vars]
                html += self._build_table(["变量名", "值"], rows)

        elif detail_type == "combat_projectile":
            # 战斗预设 - 投射物：按“属性 / 组件 / 能力”三个标签页说明右侧编辑内容
            html += "<h3>投射物配置</h3>"
            data = info.get("data", {}) or {}
            projectile_name = (
                data.get("projectile_name")
                or data.get("name")
                or info.get("projectile_id")
                or ""
            )
            if projectile_name:
                html += f"<p><b>名称：</b>{projectile_name}</p>"

            # 属性标签页（对应图1）
            html += "<h4>属性标签页（图1）</h4>"
            html += "<p>在右侧“属性”标签页中，按分组完成本地投射物的基础与生命周期配置：</p>"
            html += "<ul>"
            html += "<li><b>基础设置</b>：选择投射物模型资产（例如：木箱），并根据需要调整 X / Y / Z 缩放比例。</li>"
            html += "<li><b>原生碰撞</b>：根据玩法勾选“初始生效”“是否可攀爬”等碰撞相关开关。</li>"
            html += "<li><b>战斗参数</b>：在“属性设置”中选择是继承创建者还是独立配置属性，并确认“后续是否受创建者影响”。</li>"
            html += "<li><b>生命周期设置</b>：决定是否永久持续；如非永久，则设置持续时长(s) 以及 XZ / Y 方向的销毁距离阈值。</li>"
            html += "<li><b>生命周期结束行为</b>：为生命周期结束时需要触发的效果预留能力单元入口（例如：爆炸、回收等）。</li>"
            html += "</ul>"

            # 组件标签页（对应图2）
            html += "<h4>组件标签页（图2）</h4>"
            html += "<p>在“组件”标签页中，为投射物挂载和配置专用组件：</p>"
            html += "<ul>"
            html += "<li><b>特效播放</b>：维护投射物飞行或出现时需要播放的特效列表，通过“详细编辑”调整具体特效与触发时机。</li>"
            html += "<li><b>投射运动器</b>：选择运动类型（如直线投射），并在“详细编辑”中设置速度、重力系数等运动参数。</li>"
            html += "<li><b>命中检测</b>：配置命中检测触发区（例如“区域1”），在“详细编辑”里调整碰撞体积、层级过滤等检测规则。</li>"
            html += "</ul>"

            # 能力标签页（对应图3）
            html += "<h4>能力标签页（图3）</h4>"
            html += "<p>在“能力”标签页中，集中维护投射物命中或销毁时要触发的能力逻辑：</p>"
            html += "<ul>"
            html += "<li><b>能力单元</b>：为命中、生命周期结束等事件添加能力单元条目；本页只负责建立引用与顺序，具体能力内容在能力库中维护。</li>"
            html += "</ul>"

        elif detail_type.startswith("combat_"):
            html += f"<h3>{CombatTypeNames.get_name(detail_type)}</h3>"
            data = info.get("data", {})
            if data:
                html += f"<p><b>{data.get('name', '')}</b></p>"
                rows = [[f"<b>{key}</b>", value] for key, value in data.items() if key != "name"]
                html += self._build_table([], rows)

        elif detail_type.startswith("management_"):
            html += f"<h3>{ManagementTypeNames.get_name(detail_type)}</h3>"
            data = info.get('data', {})
            if data:
                html += f"<p><b>{data.get('name', '')}</b></p>"
                rows = [[f"<b>{key}</b>", value] for key, value in data.items() if key != 'name']
                html += self._build_table([], rows)

        elif detail_type in ("template_graph_root", "event_flow_root", "graph_create_node",
                             "graph_create_and_connect", "graph_create_and_connect_reverse"):
            html += f"<h3>{todo.title}</h3>"
            html += f"<p>{todo.description}</p>"

        elif detail_type == "graph_config_node_merged":
            node_title = info.get('node_title', '')
            params = info.get('params', [])
            html += f"<h3>{todo.title}</h3>"
            html += f"<p>节点：<b>{node_title}</b></p>"
            if params:
                headers = ["参数", "值"]
                rows = [[p.get('param_name', ''), p.get('param_value', '')] for p in params]
                html += self._build_table(headers, rows)

        elif detail_type == "graph_config_branch_outputs":
            node_title = info.get('node_title', '')
            branches = info.get('branches', [])
            html += f"<h3>{todo.title}</h3>"
            html += f"<p>节点：<b>{node_title}</b></p>"
            if branches:
                headers = ["分支端口", "匹配值"]
                rows = [[b.get('port_name', ''), b.get('value', '')] for b in branches]
                html += self._build_table(headers, rows)

        elif detail_type == "graph_connect_merged":
            node1_title = info.get('node1_title', '')
            node2_title = info.get('node2_title', '')
            edges = info.get('edges', [])
            html += f"<h3>{todo.title}</h3>"
            if node1_title or node2_title:
                html += f"<p>{node1_title} → {node2_title}</p>"
            if edges:
                headers = ["源端口", "目标端口"]
                rows = [[e.get('src_port', ''), e.get('dst_port', '')] for e in edges]
                html += self._build_table(headers, rows)

        elif detail_type == "graph_signals_overview":
            html += "<h3>本图信号概览</h3>"
            graph_name = info.get("graph_name", "") or ""
            if graph_name:
                html += f"<p><b>节点图：</b>{graph_name}</p>"
            signals = info.get("signals", []) or []
            if signals:
                headers = ["信号名", "信号ID", "使用节点数", "是否在当前存档定义"]
                rows: List[List[str]] = []
                for entry in signals:
                    signal_name = entry.get("signal_name") or "(未命名信号)"
                    signal_id = entry.get("signal_id") or ""
                    node_count = entry.get("node_count", 0)
                    defined = entry.get("defined_in_package", False)
                    defined_text = "是" if defined else "否"
                    rows.append(
                        [
                            f"<b>{signal_name}</b>",
                            f"<code>{signal_id}</code>",
                            str(node_count),
                            defined_text,
                        ]
                    )
                html += self._build_table(headers, rows)
                html += "<p style='color: #888888; font-size: 10pt;'>双击任务或使用右上角按钮可在编辑器中查看并调整这些信号节点。</p>"

        elif detail_type == "graph_bind_signal":
            html += f"<h3>{todo.title}</h3>"
            node_title = info.get("node_title", "")
            node_id = info.get("node_id", "")
            if node_title or node_id:
                html += "<p><b>目标节点：</b>"
                if node_title:
                    html += node_title
                if node_id:
                    html += f" <code>({node_id})</code>"
                html += "</p>"
            signal_name = info.get("signal_name") or ""
            signal_id = info.get("signal_id") or ""
            if signal_name or signal_id:
                html += "<p><b>当前绑定信号：</b>"
                if signal_name:
                    html += signal_name
                if signal_id:
                    html += f" <code>({signal_id})</code>"
                html += "</p>"
            else:
                html += "<p><b>当前绑定信号：</b><span style='color: #D32F2F;'>未选择</span></p>"

            html += "<p style='color: #888888; font-size: 10pt;'>"
            html += "在节点图中右键该节点，可通过“选择信号…”绑定信号，或通过“打开信号管理器…”调整信号定义。"
            html += "</p>"

        return html


