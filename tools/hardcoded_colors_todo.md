# 硬编码颜色整改 Todo

下面列出了当前扫描到的所有硬编码颜色位置，建议按文件逐步迁移到 `ThemeManager/Colors` 体系下：

- [ ] `app/ui/composite/preview_scene.py`
  - [ ] L136: `painter.setPen(QtGui.QPen(QtGui.QColor("#FFFFFF"), 1))`

- [ ] `app/ui/foundation/canvas_background.py`
  - [ ] L8: `painter.fillRect(rect, QtGui.QColor("#1E1E1E"))`
  - [ ] L13: `light_grid_pen = QtGui.QPen(QtGui.QColor("#2A2A2A"), 1)`
  - [ ] L26: `thick_grid_pen = QtGui.QPen(QtGui.QColor("#3A3A3A"), 2)`

- [ ] `app/ui/graph/graph_view/overlays/ruler_overlay_painter.py`
  - [ ] L34: `ruler_color = QtGui.QColor('#2B2B2B')`
  - [ ] L36: `text_color = QtGui.QColor('#B0B0B0')`
  - [ ] L37: `line_color = QtGui.QColor('#4A4A4A')`
  - [ ] L124: `painter.fillRect(corner_rect, QtGui.QColor('#3A3A3A'))`

- [ ] `app/ui/graph/graph_view/popups/add_node_popup.py`
  - [ ] L31: `background-color: #2B2B2B;`
  - [ ] L32: `border: 1px solid #3A3A3A;`
  - [ ] L36: `background-color: #1E1E1E;`
  - [ ] L37: `color: #E0E0E0;`
  - [ ] L38: `border: 1px solid #3A3A3A;`
  - [ ] L43: `background-color: #1E1E1E;`
  - [ ] L44: `color: #E0E0E0;`
  - [ ] L45: `border: 1px solid #3A3A3A;`
  - [ ] L105: `"事件节点": "#FF5E9C",`
  - [ ] L106: `"执行节点": "#9CD64B",`
  - [ ] L107: `"查询节点": "#2D5FE3",`
  - [ ] L108: `"运算节点": "#2FAACB",`
  - [ ] L109: `"流程控制节点": "#FF9955",`
  - [ ] L110: `"复合节点": "#AA55FF",  # 紫色，表示复合节点`
  - [ ] L169: `category_color = category_colors.get(category, "#4A9EFF")`
  - [ ] L230: `category_color = category_colors.get(category, "#4A9EFF")`

- [ ] `app/ui/graph/graph_view/top_right/controls_manager.py`
  - [ ] L36: `background-color: #4A9EFF;`
  - [ ] L45: `background-color: #5AAFFF;`
  - [ ] L48: `background-color: #3A8EEF;`
  - [ ] L51: `background-color: #666666;`
  - [ ] L52: `color: #999999;`

- [ ] `app/ui/graph/items/edge_item.py`
  - [ ] L38: `color = QtGui.QColor('#FF6B35')  # 明亮的橙红色`
  - [ ] L42: `color = QtGui.QColor('#00BCD4')  # 明亮的青色`
  - [ ] L48: `color = QtGui.QColor('#4CAF50')  # 绿色`
  - [ ] L52: `color = QtGui.QColor('#F44336')  # 红色`
  - [ ] L56: `color = QtGui.QColor('#FFD700')  # 金黄色`
  - [ ] L60: `color = QtGui.QColor('#5A9FD4')  # 蓝色调`

- [ ] `app/ui/graph/items/node_item.py`
  - [ ] L537: `content_color = QtGui.QColor('#1F1F1F')`
  - [ ] L541: `QtGui.QColor('#3A3A3A')`
  - [ ] L555: `painter.setPen(QtGui.QColor('#FFFFFF'))`
  - [ ] L570: `painter.setPen(QtGui.QColor('#E0E0E0'))  # 统一使用亮色`
  - [ ] L592: `painter.setPen(QtGui.QColor('#E0E0E0'))  # 确保标签是亮色`
  - [ ] L614: `painter.fillRect(const_rect, QtGui.QColor('#2A2A2A'))`
  - [ ] L615: `painter.setPen(QtGui.QColor('#444444'))`
  - [ ] L619: `painter.setPen(QtGui.QColor('#E0E0E0'))  # 确保标签是亮色`
  - [ ] L648: `warning_color = QtGui.QColor('#FFD700')  # 金黄色`
  - [ ] L650: `warning_color = QtGui.QColor('#FFA500')  # 橙色`
  - [ ] L652: `warning_color = QtGui.QColor('#87CEEB')  # 浅蓝色`
  - [ ] L654: `warning_color = QtGui.QColor('#FFD700')`
  - [ ] L669: `return QtGui.QColor('#AA55FF') if self.node.is_virtual_pin_input else QtGui.QColor('#55AAFF')`
  - [ ] L677: `'查询': QtGui.QColor('#2D5FE3'),`
  - [ ] L678: `'查询节点': QtGui.QColor('#2D5FE3'),`
  - [ ] L679: `'事件': QtGui.QColor('#FF5E9C'),`
  - [ ] L680: `'事件节点': QtGui.QColor('#FF5E9C'),`
  - [ ] L681: `'运算': QtGui.QColor('#2FAACB'),`
  - [ ] L682: `'运算节点': QtGui.QColor('#2FAACB'),`
  - [ ] L683: `'执行': QtGui.QColor('#9CD64B'),`
  - [ ] L684: `'执行节点': QtGui.QColor('#9CD64B'),`
  - [ ] L685: `'流程控制': QtGui.QColor('#FF9955'),`
  - [ ] L686: `'流程控制节点': QtGui.QColor('#FF9955'),`
  - [ ] L690: `return color_map.get(cat, QtGui.QColor('#555555'))`
  - [ ] L697: `return QtGui.QColor('#8833DD') if self.node.is_virtual_pin_input else QtGui.QColor('#3388DD')`
  - [ ] L705: `'查询': QtGui.QColor('#1B3FA8'),`
  - [ ] L706: `'查询节点': QtGui.QColor('#1B3FA8'),`
  - [ ] L707: `'事件': QtGui.QColor('#C23A74'),`
  - [ ] L708: `'事件节点': QtGui.QColor('#C23A74'),`
  - [ ] L709: `'运算': QtGui.QColor('#1D6F8A'),`
  - [ ] L710: `'运算节点': QtGui.QColor('#1D6F8A'),`
  - [ ] L711: `'执行': QtGui.QColor('#6BA633'),`
  - [ ] L712: `'执行节点': QtGui.QColor('#6BA633'),`
  - [ ] L713: `'流程控制': QtGui.QColor('#E87722'),`
  - [ ] L714: `'流程控制节点': QtGui.QColor('#E87722'),`
  - [ ] L718: `return color_map.get(cat, QtGui.QColor('#3A3A3A'))`

- [ ] `app/ui/graph/items/port_item.py`
  - [ ] L178: `color = self.highlight_color if has_custom_highlight else QtGui.QColor('#FFD700')`
  - [ ] L185: `painter.setPen(QtGui.QPen(QtGui.QColor('#FFD700'), 2))`
  - [ ] L188: `painter.setPen(QtGui.QPen(QtGui.QColor('#FFFFFF'), 2))`
  - [ ] L194: `pen_color = self.highlight_color if has_custom_highlight else QtGui.QColor('#00FF00')`
  - [ ] L201: `pen_color = QtGui.QColor('#FFD700')`
  - [ ] L205: `pen_color = QtGui.QColor('#D0D0D0') if self.is_input else QtGui.QColor('#FFFFFF')`
  - [ ] L255: `gradient.setColorAt(0, QtGui.QColor('#FFD700'))`
  - [ ] L256: `gradient.setColorAt(1, QtGui.QColor('#FFA500'))`
  - [ ] L258: `painter.setPen(QtGui.QPen(QtGui.QColor('#CC8800'), 2))`
  - [ ] L269: `painter.setPen(QtGui.QPen(QtGui.QColor('#FFFFFF'), 1))`
  - [ ] L507: `self.setDefaultTextColor(QtGui.QColor('#FFD700'))  # 金黄色，表示这是流程端口相关`
  - [ ] L541: `fmt.setForeground(QtGui.QBrush(QtGui.QColor('#FFD700')))`

- [ ] `app/ui/overlays/scene_overlay.py`
  - [ ] L110: `painter.setBrush(QtGui.QBrush(QtGui.QColor('#FFAA00')))`
  - [ ] L140: `painter.setPen(QtGui.QPen(QtGui.QColor('#000000'), 3))`
  - [ ] L141: `painter.setBrush(QtGui.QBrush(QtGui.QColor('#FFD400')))`
  - [ ] L148: `painter.setPen(QtGui.QPen(QtGui.QColor('#000000')))`
  - [ ] L181: `badge_color = self._all_chain_node_color_map.get(node_id, QtGui.QColor('#FFD400'))`
  - [ ] L182: `painter.setPen(QtGui.QPen(QtGui.QColor('#000000'), 3))`
  - [ ] L189: `painter.setPen(QtGui.QPen(QtGui.QColor('#000000')))`

- [ ] `app/ui/widgets/constant_editors.py`
  - [ ] L23: `self.setDefaultTextColor(QtGui.QColor('#E0E0E0'))  # 使用更亮的颜色，与端口标签一致`
  - [ ] L82: `fmt.setForeground(QtGui.QBrush(QtGui.QColor('#E0E0E0')))`
  - [ ] L141: `background-color: #2A2A2A;`
  - [ ] L142: `color: #E0E0E0;`
  - [ ] L143: `border: 1px solid #3A3A3A;`
  - [ ] L148: `border: 1px solid #5A5A5A;`
  - [ ] L157: `border-top: 5px solid #E0E0E0;`
  - [ ] L236: `color: #A0A0A0;`
  - [ ] L240: `background-color: #2A2A2A;`
  - [ ] L241: `color: #E0E0E0;`
  - [ ] L242: `border: 1px solid #3A3A3A;`
  - [ ] L248: `border: 1px solid #5A5A5A;`
