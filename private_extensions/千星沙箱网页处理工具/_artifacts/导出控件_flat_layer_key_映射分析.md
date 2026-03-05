# 导出控件点击高亮错位：`__flat_layer_key` 追踪与根治方案

## 结论（先给结论）

当前“导出控件”面板出现 **点 A 高亮 B** 的根因，不是预览选中框（`src/preview/*`）本身，而是 **“导出控件列表项 ↔ 扁平层（.flat-*）↔ 导出 widget”三者映射并非单一真源**：

- **导出侧**只在部分 widget 上写了 `__flat_layer_key`（可被视为“该 widget 对应哪个扁平层”的唯一标识），**某些 widget 分支明确不写**（尤其是按钮锚点/虚拟控件）。
- **预览页（`ui_app_ui_preview.js`）**在“列表 → 画布”选中时，当前实现 **优先按 rect 相交去猜一个 flat 层**，而不是按 `flat_layer_key` 精确命中；一旦猜中了“同区域的另一个 flat 层”，回流后就会映射到另一个 widget，从而出现错高亮。

要“从根上彻底解决”，必须把映射收敛成 **一一映射（1 widget ↔ 1 flat layer）**，并建立 **明确的降级策略**（对于不能 1:1 的虚拟控件：要么补一个可点选的 flat 层，要么定义它映射到哪个“代表层”，否则它就不该出现在需要定位的列表里）。

---

## 1. `__flat_layer_key` 到底在哪里写？（导出侧追踪）

### 1.1 写入点：`src/ui_export/template_from_layers.js`

`__flat_layer_key` 的写入只发生在 `buildUiControlGroupTemplateFromFlattenedLayers(...)` 里：

- 通过 `flatLayerKeyForPreview(layer)` 计算得到 key，格式为：

```
kind__left__top__width__height__round(z)
```

其中 rect 使用 `toFixed(2)`，z 使用 `Math.round(z)`，并声明必须与 `src/workbench_main/group_tree.js` 的 layerKey 构造一致。

- 对普通扁平层（`layer.kind in ["shadow","border","element","text"]`），都会写：

  - `wShadowTextBox.__flat_layer_key = flatLayerKeyForPreview(layerItem)`
  - `wBorder.__flat_layer_key = flatLayerKeyForPreview(layerItem)`
  - `wRect.__flat_layer_key = flatLayerKeyForPreview(layerItem)`
  - `wText.__flat_layer_key = flatLayerKeyForPreview(layerItem)`
  - 单 ICON 文本导出的道具展示 `wIcon.__flat_layer_key = flatLayerKeyForPreview(layerItem)`

### 1.2 明确不写的分支：按钮锚点（虚拟控件）

在“按钮预处理阶段”，会给按钮创建一个“道具展示”作为交互锚点（`buildItemDisplayWidget(...)`），并注释说明：

> 按钮锚点为“虚拟控件”（不对应单一扁平层），不写 `__flat_layer_key`

也就是说：**交互按钮锚点 widget 目前天然缺失 `__flat_layer_key`**。

这类 widget 之后在预览页里会被纳入“导出控件列表”，但因为缺失 `flat_layer_key`，定位只能走 “groupKey + rect 的候选 + 启发式”——这是错位的第一根火药。

---

## 2. `__flat_layer_key` 为什么会缺失？

在当前代码设计里，缺失主要来自两类“不是 1:1 扁平层”的 widget：

### 2.1 按钮锚点道具展示（最常见，也是最影响交互的）

- 这类 widget 的本质语义是“交互事件源”，它的 `rect` 来自按钮的 `anchorRect`（通常与视觉层重叠，但并非一定有对应的 `.flat-*` 视觉层）。
- 在扁平化层数据中，存在一种专门的 layer：`kind="button_anchor"`（见 `src/flatten/layer_data.js`），它只用于让导出识别按钮语义，但 **扁平输出 HTML（`src/flatten/flatten_divs.js`）目前没有生成对应的 `.flat-*` DOM**。
- 所以即便你想给按钮锚点一个“对应扁平层”，目前也找不到一个“天然存在且可选中”的 DOM 元素。

### 2.2 其它“虚拟/偏移”类 widget（次要，但会放大歧义）

例如图标道具展示会用 `pickIconSeatRect(...)` 选择“座位矩形”（widget 的 position/size），但 `__flat_layer_key` 仍指向原 text layer 的 rect/z。

这会导致两种坐标体系并存：

- `flat_layer_key` 对齐的是“扁平层（layerItem.rect）”
- widget 的 `rect` 可能对齐的是“座位矩形（seatRect）”

当预览页在某些回退路径里用 widgetRect 去找 DOM（而不是用 key 去找），就很容易选错“同区域其它层”。

---

## 3. `__flat_layer_key` 为什么会“重复”？（以及真实更常见的问题：不一致）

### 3.1 “重复”的严格含义

严格的重复是指：**两个不同 widget 拥有相同的 `__flat_layer_key`**。

在当前扁平化 z-index 策略里（`elementIndex * 10 + offset`），z 是整数且随 elementIndex 单调增长，所以同一画布下“完全重复”的概率不高。

但“重复”仍可能发生在以下极端场景：

- **非规范层级手工干预 z**：若后续有人改扁平化 z 策略（不再基于 elementIndex，而是复用 CSS z-index），则多个元素可能共享同 z。
- **round(z) 带来的碰撞**：如果未来 z 变成浮点（例如插值动画或其它归一化），`Math.round(z)` 会制造碰撞。
- **同 kind 同 rect 同 z 的层重复出现**：例如某些生成逻辑把同一片段插入两次（理论上不该发生，但一旦发生，key 直接重复）。

### 3.2 当前更现实的问题：**“不一致/非单一真源”比重复更致命**

实际错高亮并不需要重复，只需要：

- 列表点击时选中了错误的 flat DOM；
- 回流映射（flat layer → widget）依据 layerKey 精确映射到了另一个 widget；

这属于“映射链路不收敛”问题，而不是单纯的 key 碰撞问题。

---

## 4. 前因后果：从用户点击到错高亮的完整事件链

以 `ui_app_ui_preview.js` 为准，核心链路是：

1) 用户在左下“导出控件”点击某一项（widgetId=A）

2) 代码调用 `_selectExportWidgetInPreview(widgetId)`：

- 当前实现主要依赖 `targetWidget.rect` 与 flat DOM 的 `style.left/top/width/height` 计算相交面积，选一个 “best” `.flat-*` 元素；
- 这一步 **没有强制使用 `flat_layer_key` 做精确命中**（即使 widget 有）。
- 对于缺失 `flat_layer_key` 的 widget（按钮锚点），只能更依赖此启发式。

3) 调用 `preview.selectPreviewElement(bestFlatEl)` → 触发预览层 `onSelectionChanged`

4) `onSelectionChanged` 回调里 `_applyExportWidgetSelectionFromPreviewElement(flatEl)`：

- 优先取 `flatEl.dataset.layerKey`（由 group_tree 的索引写入）
- 再用 `state.exportWidgetIdByLayerKey[layerKey]` 映射到 widgetId
- 若映射到的 widgetId=B，则左下高亮切换到 B

最终表象就是：你点 A（列表）→ 画布选中了某个 flat 层（其实更像 B）→ 回流后列表高亮就变成 B。

---

## 5. 根治方案：从根上保证“一一映射”的设计

这里给出一个“能彻底解决、且长期可维护”的方案集合。优先级从强到弱：

### 方案 A（推荐）：把“可定位控件”定义为严格的 1:1，并把虚拟控件显式落地为可定位层

#### A1) 明确规则：导出控件列表只展示/只联动“可定位控件”

定义 `可定位控件`：

- 必须有 `flat_layer_key`（最终对外可叫 `flat_layer_key`，内部字段仍可沿用 `__flat_layer_key`）
- 且该 key 必须能在当前画布的 `.flat-*` DOM 中找到对应元素

对不满足者：

- 要么补齐其 `flat_layer_key` 与可选中 DOM（见 A2）
- 要么不进入“导出控件”列表（或进入但显示为“不可定位”，点击只做解释/不触发画布定位）

#### A2) 对按钮锚点：输出一个“透明的锚点扁平层”供定位

做法：

- 在 `src/flatten/flatten_divs.js` 中，当 `layer_data.js` 产出了 `kind="button_anchor"` 时，同步输出一个 `.flat-element`（或新增 `.flat-anchor`）：
  - `left/top/width/height` 为按钮 rect
  - `background-color: transparent; border: 1px dashed rgba(..., 0.0)`（或完全透明）
  - `pointer-events: none`
  - 带上 `data-ui-state-*`（与按钮的 state 绑定一致）
  - 带上一个可复用的 `data-debug-label="button-anchor-e<index>"`

然后在导出侧：

- 按钮锚点 widget 也写 `__flat_layer_key = flatLayerKeyForPreview(button_anchor_layer)`

这样按钮锚点就从“虚拟控件”变成了“可定位控件”，链路闭环。

### 方案 B（必须做，即使采用 A）：预览页“列表 → 画布”必须优先用 `flat_layer_key` 精确定位

不管你是否补了按钮锚点层，只要一个 widget 拥有 `flat_layer_key`，点击列表项就应该：

1) 用 `flat_layer_key` 在 `.flat-display-area` 内寻找 `el.dataset.layerKey == flat_layer_key` 的 `.flat-*`；
2) 找到则直接选中该 el；
3) 找不到才允许回退为 rect 相交启发式。

这样可以从根本上杜绝“点 A 但画布选中了 B 的 flat 层”。

### 方案 C（工程化加强）：把 layerKey 从“几何拼字符串”升级为“唯一 ID + 几何 Key 并存”

当前 key 设计是 geometry-only（kind+rect+z），一旦未来 z 策略改变或出现同 rect 同 z 的情况，就会产生碰撞风险。

更稳健的做法是引入双 key：

- `layer_uid`：唯一 ID（建议包含 `source.elementIndex`、cutout seg index、kind、以及必要的 state 维度）
- `layer_geom_key`：现有 kind+rect+z（用于容差匹配/调试）

并让：

- `__flat_layer_key` 指向 `layer_uid`
- DOM 上写 `data-layer-uid`
- 调试/排障仍展示 geom_key

这属于“未来-proof”的工程化升级，适合在系统稳定后做一次统一迁移。

---

## 6. 彻底解决后的验收标准（你应该能观察到什么）

实现方案 A+B 后，验收标准应当是：

- **列表点击**：点哪个控件，画布必定选中同一个控件对应的 flat 层（不再靠相交猜）。
- **画布点击**：点哪个 flat 层，列表必定高亮其唯一对应的 widget。
- **按钮锚点**：即便按钮本体“视觉为空”（透明，内容在子层），仍能在画布上被定位（因为存在透明锚点层）。
- **缺失 key 不再静默**：如果某 widget 仍缺 `flat_layer_key`，应在导出控件列表中明确标注“不可定位”，并在控制台/diagnostics 输出具体 widgetId/ui_key，便于修复。

---

## 7. 建议的落地步骤（按风险从低到高）

1) **先做 B**：预览页列表点击优先按 `flat_layer_key` 精确定位（最小风险，立竿见影）。
2) **对按钮锚点补齐 key（A2 的一半）**：哪怕暂时不生成透明扁平层，也先给按钮锚点写 `__flat_layer_key` 指向“最合理的代表层”（例如按钮底色/文本层）。这能显著减少错位，但无法保证所有按钮都可定位。
3) **补齐透明锚点扁平层（A2 完整）**：让 button_anchor 有真实 DOM，可 100% 精确定位。
4) **工程化升级（C）**：引入 layer_uid，彻底消除未来 key 碰撞隐患。

