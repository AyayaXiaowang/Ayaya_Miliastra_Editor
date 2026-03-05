## 目录用途
- `src/flatten/internal/`：承载 `src/flatten.js` 的内部实现细节（几何计算 / cutout 切分 / 遮挡剔除 / 调试 overlay 等），用于把超长文件按“算法域”拆分，保持 `flatten.js` 对外 API 稳定。

## 当前状态
- `rects.js`：几何/矩形工具（right/bottom/intersects/containsPoint/采样点/数值去重）。
- `cutouts.js`：游戏区域挖空（`.game-cutout`）相关：识别 cutout 元素、收集 cutout rect、对矩形执行 cutout 切分并尽量合并碎片。
- `highlight_areas.js`：高亮展示区域（`.highlight-display-area`）相关：识别 marker、读取压暗强度、并把“画布减去高亮区域”拆成 4 个遮罩矩形（上/下/左/右），供扁平化输出 shadow layers。
- `occlusion.js`：**遮挡剔除（已禁用）**。历史上用于“降噪优化”（剔除被上层完全覆盖的组），但在多状态控件与透明交互锚点场景副作用过大（导出丢交互语义/丢非默认态模板）；当前策略为**正确性优先**：恒等返回，不做任何剔除。

## 注意事项
- **内部模块**：仅供 `flatten.js` 使用，不保证 API 稳定；对外稳定 API 以 `src/flatten.js` 为准。
- **浏览器侧**：禁止引入 Node.js API。
- **Cutout 语义**：`.game-cutout` 用于“游戏视口挖空”，会裁剪/切分其下方绘制的背景矩形，避免遮住游戏画面；不会裁剪其上方覆盖 UI。
  - 层级判定：优先按“组件/DOM 顺序”（`componentOwnerElementIndex` 跨组件 + dom_extract 先序 index），并用 `z-index` 作为“置顶覆盖层”的补充信号；**仅当 z-index 与顺序都表明该元素在 cutout 之上时**才跳过裁剪，避免容器用 z-index 做局部层级却导致挖空失效。
  - 为避免误用导致整页被裁空，仍建议避免多个 cutout 互相重叠（并由 `validation.js` 做 overlap 校验）。

---
注意：本文件不记录任何修改历史。请始终保持对“目录用途、当前状态、注意事项”的实时描述。

