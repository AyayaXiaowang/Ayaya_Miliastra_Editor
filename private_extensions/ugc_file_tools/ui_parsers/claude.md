## 目录用途
- 存放“UI 相关解析器”：以 dump-json（数值键结构）的 raw JSON 为输入，进一步还原为业务可读/可用的结构化数据（JSON）。
- 解析目标偏向“可落盘 + 可复用”：字段尽量语义化；无法确认的字段保留 code/raw，避免误判。

## 当前状态
- `progress_bars.py`：从 DLL raw dump 中识别并解析“进度条”控件（变量绑定、形状/样式/颜色枚举、RectTransform 各 state 的位置/大小；按固定锚点计算画布坐标；并基于样本将 state_index 映射到设备模板（电脑/手机/主机/手柄主机）以使用不同画布尺寸；输出 `anchor_preset`（九宫格锚点名称）与部分 record['502'] 的二进制元数据用于继续逆向）。识别规则已放宽：允许 current/min/max 的变量名缺失（表示未绑定变量），仍按进度条解析并输出 `is_bound`；颜色枚举 code=0 输出为“默认(绿色)”以对齐编辑器默认色语义；同时输出统一调色板 `hex`（绿/白/黄/蓝/红：`#92CD21/#E2DBCE/#F3C330/#36F3F3/#F47B7B`），用于与主程序 UI 面板/写回链路对齐。
- `layouts.py`：解析“布局注册表（4/9/501）”与每个布局 root 的 children 控件列表（record/503），并识别布局层面的可见性覆盖字段（record/505[1]/503/14/502）。
  - repeated 兼容：DLL dump JSON 在 repeated string 仅 1 个元素时，可能退化为标量 `str`；解析器会归一化为 `list[str]`。
  - 空 children 兼容：children 的 `<binary_data>` 可能以空字符串 `""` 表示（视为无 children）。
- `item_displays.py`：从 DLL raw dump 中识别并解析“道具展示”控件：展示类型、可交互开关、键位码（键鼠/手柄）、无装备时表现、冷却变量、次数开关/隐藏开关/次数变量、数量变量与（模板道具）数量显示/为 0 隐藏开关；并覆盖不同展示类型下的“配置ID变量”所在字段（玩家当前装备：505；模板道具：511；背包内道具：516）。未知字段保留在 `raw_codes` 便于继续对照逆向；按键额外输出 `label_hint`（从控件名推断）与 `code->label_hint` 汇总表，便于建立键位对照。
  - binding 结构兼容：支持从 `<binary_data>` blob 形态识别道具展示；并为“binding 已被展开为 dict message”的样本预留兼容路径（用于与写回/导入侧的双形态兼容保持一致）。

## 注意事项
- 本目录不负责 DLL 调用；只处理已 dump 出来的 Python dict（raw JSON）。
- 不使用 try/except；无法解析的结构用“返回 None/忽略该记录”的方式处理，必要时直接抛错以便定位数据不一致。
- 输出 JSON 默认使用 UTF-8（`ensure_ascii=False`），避免中文字段丢失。