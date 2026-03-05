import { escapeHtmlText } from "../utils.js";
import { flattenGroupTreeController, state } from "./context.js";

function _widgetToRect(widget) {
  var pos = widget && widget.position ? widget.position : null;
  var size = widget && widget.size ? widget.size : null;
  if (!pos || !size || pos.length !== 2 || size.length !== 2) return null;
  var left = Number(pos[0] || 0);
  var top = Number(pos[1] || 0);
  var width = Number(size[0] || 0);
  var height = Number(size[1] || 0);
  if (!isFinite(left) || !isFinite(top) || !isFinite(width) || !isFinite(height)) return null;
  return { left: left, top: top, width: width, height: height };
}

export function applyExportExcludesToBundlePayload(bundlePayload) {
  var bundle = bundlePayload || {};
  if (!flattenGroupTreeController || !flattenGroupTreeController.isGroupExcluded) {
    return bundle;
  }
  var templates = Array.isArray(bundle.templates) ? bundle.templates : [];
  if (!templates || templates.length <= 0) {
    return bundle;
  }

  function _shouldExcludeWidget(groupKey, rect, widget) {
    var gk = String(groupKey || "").trim();
    if (!gk || gk === "__no_group_key__") return false;
    if (flattenGroupTreeController.isGroupExcluded && flattenGroupTreeController.isGroupExcluded(gk)) return true;
    // 单控件排除（严格）：只认导出端写入的 flat_layer_key/__flat_layer_key（与扁平层一一对应）。
    // 不允许按 rect/groupKey 推导，否则会产生“选中/显隐按 layerKey，但排除按推导 key”的分叉。
    var explicitLayerKey = widget ? String(widget.__flat_layer_key || widget.flat_layer_key || "").trim() : "";
    if (explicitLayerKey && flattenGroupTreeController.isLayerExcluded) {
      return !!flattenGroupTreeController.isLayerExcluded(explicitLayerKey);
    }
    return false;
  }

  var newTemplates = [];
  for (var ti = 0; ti < templates.length; ti++) {
    var tpl = templates[ti] || {};
    var ws = Array.isArray(tpl.widgets) ? tpl.widgets : [];
    var kept = [];
    for (var wi = 0; wi < ws.length; wi++) {
      var w = ws[wi] || {};
      var gk = String(w.__html_component_key || "").trim() || "__no_group_key__";
      var rect = _widgetToRect(w);
      if (_shouldExcludeWidget(gk, rect, w)) {
        continue;
      }
      kept.push(w);
    }
    if (kept.length > 0) {
      newTemplates.push(Object.assign({}, tpl, { widgets: kept }));
    }
  }
  return Object.assign({}, bundle, { templates: newTemplates, __export_excludes_applied: true });
}

export function buildExportWidgetPreviewModelFromBundle(bundlePayload) {
  var bundle = bundlePayload || {};
  var layout = bundle.layout || {};
  var templates = bundle.templates || [];

  // 关键：为了复用“扁平分组”的隐藏状态，需要按 __html_component_key 分组（与 group_tree 的 groupKey 对齐）。
  var groups = [];
  var groupByKey = new Map(); // groupKey -> entry
  // UI 多状态索引：__ui_state_group -> Set(__ui_state)
  // 用于判断“是否多状态控件”（一个 state_group 下出现 >= 2 个不同 state）。
  var uiStateGroupToStates = new Map();

  var totalWidgets = 0;
  var totalInteractiveButtons = 0;

  for (var ti = 0; ti < templates.length; ti++) {
    var tpl = templates[ti] || {};
    var ws = tpl.widgets || [];
    for (var wi = 0; wi < ws.length; wi++) {
      var w = ws[wi] || {};
      var groupKey = String(w.__html_component_key || "").trim();
      if (!groupKey) {
        groupKey = "__no_group_key__";
      }

      var entry = groupByKey.get(groupKey);
      if (!entry) {
        entry = { group_key: groupKey, widgets: [] };
        groupByKey.set(groupKey, entry);
        groups.push(entry);
      }

      var widgetType = String(w.widget_type || "");
      var settings = w.settings || null;
      var canInteract = (widgetType === "道具展示" && settings && settings.can_interact === true);
      var interactCode = 0;
      if (canInteract && settings) {
        var kbm = Number(settings.keybind_kbm_code || 0);
        var pad = Number(settings.keybind_gamepad_code || 0);
        var best = kbm > 0 ? kbm : (pad > 0 ? pad : 0);
        interactCode = isFinite(best) ? Math.trunc(best) : 0;
      }
      if (canInteract) totalInteractiveButtons += 1;
      totalWidgets += 1;

      // UI 多状态元数据（来自 data-ui-state-*，由导出链路写入 widget payload）
      var uiStateGroup = String(w.__ui_state_group || "").trim();
      var uiState = String(w.__ui_state || "").trim();
      var uiStateDefault = !!w.__ui_state_default;
      if (uiStateGroup) {
        var set0 = uiStateGroupToStates.has(uiStateGroup) ? uiStateGroupToStates.get(uiStateGroup) : null;
        if (!set0) {
          set0 = new Set();
          uiStateGroupToStates.set(uiStateGroup, set0);
        }
        // state 允许为空（例如只声明 group）；仍视作一个 state key
        set0.add(uiState);
      }
      var rect0 = _widgetToRect(w);
      // 严格口径：只认导出端写入的 flat_layer_key / __flat_layer_key（与扁平层一一对应），
      // 不再做“按 widget_type/widget_name/rect/z 推断”的兼容猜测，避免误映射。
      var flatKey0 = String(w.__flat_layer_key || w.flat_layer_key || "").trim();
      entry.widgets.push({
        widget_id: String(w.widget_id || ""),
        widget_type: widgetType,
        widget_name: String(w.widget_name || ""),
        ui_key: String(w.ui_key || ""),
        layer_index: (w.layer_index === undefined ? 0 : (isFinite(Number(w.layer_index)) ? Math.trunc(Number(w.layer_index)) : 0)),
        flat_layer_key: flatKey0,
        can_interact: canInteract,
        interact_code: interactCode,
        rect: rect0,
        group_key: groupKey,
        ui_state_group: uiStateGroup,
        ui_state: uiState,
        ui_state_default: uiStateDefault,
        initial_visible: (w.initial_visible === undefined ? true : !!w.initial_visible),
        // 下面两个字段会在二次遍历时补齐（依赖全局 uiStateGroupToStates）
        is_multi_state: false,
        ui_state_count: 0,
        is_multi_state_inferred: false,
      });
    }
  }

  // 二次遍历：补齐 is_multi_state / ui_state_count（需要看到全量 widgets 才能判断）
  function _getUiStateCount(groupText) {
    var g = String(groupText || "").trim();
    if (!g) return 0;
    var set1 = uiStateGroupToStates.has(g) ? uiStateGroupToStates.get(g) : null;
    if (!set1) return 0;
    // Set.size 在老环境也支持；这里做兜底以防被 polyfill 覆盖
    var n = Number(set1.size || 0);
    return isFinite(n) ? Math.max(0, Math.trunc(n)) : 0;
  }
  for (var gi2 = 0; gi2 < groups.length; gi2++) {
    var g2 = groups[gi2] || {};
    var ws2 = g2.widgets || [];
    for (var wi2 = 0; wi2 < ws2.length; wi2++) {
      var ww = ws2[wi2] || {};
      var cnt = _getUiStateCount(ww.ui_state_group);
      ww.ui_state_count = cnt;
      ww.is_multi_state_inferred = false;
      ww.is_multi_state = !!(ww.ui_state_group && cnt >= 2);
    }
  }

  // 稳定顺序：按“视觉顺序”大致排序（y->x），兜底按 group_key 字符串。
  groups.sort(function (a, b) {
    var aw = a && a.widgets ? a.widgets[0] : null;
    var bw = b && b.widgets ? b.widgets[0] : null;
    var ar = aw && aw.rect ? aw.rect : null;
    var br = bw && bw.rect ? bw.rect : null;
    var ay = ar ? Number(ar.top || 0) : 0;
    var by = br ? Number(br.top || 0) : 0;
    if (ay !== by) return ay - by;
    var ax = ar ? Number(ar.left || 0) : 0;
    var bx = br ? Number(br.left || 0) : 0;
    if (ax !== bx) return ax - bx;
    return String(a.group_key || "").localeCompare(String(b.group_key || ""));
  });
  for (var gi = 0; gi < groups.length; gi++) {
    var g = groups[gi];
    if (!g || !g.widgets) continue;
    g.widgets.sort(function (l, r) {
      var lr = l && l.rect ? l.rect : null;
      var rr = r && r.rect ? r.rect : null;
      var ly = lr ? Number(lr.top || 0) : 0;
      var ry = rr ? Number(rr.top || 0) : 0;
      if (ly !== ry) return ly - ry;
      var lx = lr ? Number(lr.left || 0) : 0;
      var rx = rr ? Number(rr.left || 0) : 0;
      if (lx !== rx) return lx - rx;
      return String(l.widget_id || "").localeCompare(String(r.widget_id || ""));
    });
  }

  return {
    canvas_size_key: String(bundle.canvas_size_key || ""),
    canvas_size_label: String(bundle.canvas_size_label || ""),
    layout_name: String(layout.layout_name || ""),
    groups: groups,
    totals: {
      templates: groups.length,
      widgets: totalWidgets,
      interactive_buttons: totalInteractiveButtons
    }
  };
}

export function renderExportWidgetPreviewHtml(model) {
  var m = model || null;
  if (!m) {
    return '<div class="wb-tree-empty">未生成。</div>';
  }
  var q = String(state.leftBottomFilterText || "").trim().toLowerCase();
  function _match(s) {
    if (!q) return true;
    return String(s || "").toLowerCase().indexOf(q) >= 0;
  }
  function _stateTagHtmlForWidget(w) {
    var ww = w || {};
    var isMulti = !!ww.is_multi_state;
    var g = String(ww.ui_state_group || "").trim();
    var s = String(ww.ui_state || "").trim();
    var cnt = Number(ww.ui_state_count || 0);
    var extra = "该控件属于多状态。";
    if (isMulti && g) {
      extra = "状态组: " + g + (s ? (" | 状态: " + s) : "") + (isFinite(cnt) && cnt >= 2 ? (" | 状态数: " + String(Math.trunc(cnt))) : "");
    }
    var isDefault = !!ww.ui_state_default;
    if (!isMulti) {
      // 单态：不显示文字/按钮，避免“满屏单态”污染信息密度；仅保留占位保证右侧列对齐
      return '<span class="wb-tree-state-placeholder" aria-hidden="true"></span>';
    }
    var title = extra + (isDefault ? "（默认态）" : "（非默认态：初始隐藏）");
    // 重要：不要只靠 hover 提示，列表里直接显示“默认/隐藏”，否则用户会误以为“另一种状态没导出”
    var visibleLabel = isDefault ? "默认" : "隐藏";
    // 右侧独立控件：不参与选中/定位；仅提示状态信息
    return (
      '<button type="button" class="wb-tree-toggle wb-tree-state" data-toggle-kind="state"' +
      ' data-has-multi-state="1"' +
      ' data-ui-state-group="' + escapeHtmlText(g) + '"' +
      ' data-ui-state="' + escapeHtmlText(s) + '"' +
      ' data-ui-state-default="' + (isDefault ? "1" : "0") + '"' +
      ' title="' + escapeHtmlText(title) + '">' +
      '<span class="wb-tree-state-text">多态·' + escapeHtmlText(visibleLabel) + "</span>" +
      '<span class="wb-tree-state-dot" aria-hidden="true"></span>' +
      "</button>"
    );
  }
  function _stateTagHtmlForGroupWidgets(widgetList) {
    var ws = Array.isArray(widgetList) ? widgetList : [];
    if (!ws || ws.length <= 0) return "";
    // 组级：只要组内存在任意多状态 widget，就显示“多态”标签（并尽量取默认态/状态名作为提示）
    var picked = null;
    var groupStateGroup = "";
    var groupStateGroupMixed = false;
    var groupStateCount = 0;
    for (var i = 0; i < ws.length; i++) {
      if (ws[i] && ws[i].is_multi_state) {
        picked = ws[i];
        // 偏向默认态，让 summary 更直观
        if (ws[i].ui_state_default) break;
      }
      if (ws[i] && ws[i].ui_state_group) {
        var g = String(ws[i].ui_state_group || "").trim();
        if (g) {
          if (!groupStateGroup) {
            groupStateGroup = g;
          } else if (groupStateGroup !== g) {
            groupStateGroupMixed = true;
          }
          var n = Number(ws[i].ui_state_count || 0);
          if (isFinite(n)) groupStateCount = Math.max(groupStateCount, Math.trunc(n));
        }
      }
    }
    if (!picked) return '<span class="wb-tree-state-placeholder" aria-hidden="true"></span>';
    var base = _stateTagHtmlForWidget(picked);
    // 额外提示：在 summary 上直接解释“为什么这些条目在一个组里”
    // - 当前分组规则按 __html_component_key（组件键）分组；
    // - 多状态控件通常会复用同一个 data-ui-key，并在同一状态组下产生多个互斥 state。
    if (groupStateGroupMixed) {
      return base + '<span class="muted" style="margin-left:6px">状态组：多个</span>';
    }
    if (groupStateGroup) {
      var cntText = (groupStateCount >= 2) ? ("（" + String(groupStateCount) + "态）") : "";
      return base + '<span class="muted" style="margin-left:6px">状态组：' + escapeHtmlText(groupStateGroup) + cntText + "</span>";
    }
    return base;
  }
  var htmlParts = [];
  htmlParts.push(
    '<div class="wb-tree-meta">画布：' + escapeHtmlText(String(m.canvas_size_label || m.canvas_size_key || "")) +
    " | 模板：" + String((m.totals && m.totals.templates) ? m.totals.templates : 0) +
    " | 控件：" + String((m.totals && m.totals.widgets) ? m.totals.widgets : 0) +
    " | 交互按钮：" + String((m.totals && m.totals.interactive_buttons) ? m.totals.interactive_buttons : 0) +
    "</div>"
  );

  var groups = m.groups || [];
  if (!groups || groups.length <= 0) {
    htmlParts.push('<div class="wb-tree-empty">空：未生成任何控件（可能扁平提取为空/被过滤）。</div>');
    return htmlParts.join("\n");
  }

  for (var gi = 0; gi < groups.length; gi++) {
    var g = groups[gi] || {};
    var groupKey = String(g.group_key || "");
    var widgets = g.widgets || [];

    var groupLayerKeys = [];
    for (var gwi = 0; gwi < widgets.length; gwi++) {
      var lkList = _getLayerKeysForWidget(widgets[gwi]);
      for (var li = 0; li < lkList.length; li++) {
        var lk = String(lkList[li] || "").trim();
        if (lk) groupLayerKeys.push(lk);
      }
    }
    // 去重（避免重复 key 造成误判为“全部隐藏”）
    if (groupLayerKeys.length > 1) {
      var seen = {};
      var uniq = [];
      for (var gi2 = 0; gi2 < groupLayerKeys.length; gi2++) {
        var k2 = String(groupLayerKeys[gi2] || "");
        if (!k2) continue;
        if (seen[k2]) continue;
        seen[k2] = 1;
        uniq.push(k2);
      }
      groupLayerKeys = uniq;
    }
    var isHidden = _isAllLayerKeysHidden(groupLayerKeys);
    function _buildEyeIconHtml(isHiddenFlag) {
      var hiddenAttr = isHiddenFlag ? ' data-hidden="1"' : "";
      return (
        '<span class="wb-eye-icon"' + hiddenAttr + ' aria-hidden="true">' +
        '<svg viewBox="0 0 24 24" width="14" height="14" focusable="false">' +
        '<path class="wb-eye-shape" d="M12 5c5.6 0 9.7 4.5 10.6 6.1.2.3.2.5 0 .8C21.7 13.5 17.6 18 12 18S2.3 13.5 1.4 11.9c-.2-.3-.2-.5 0-.8C2.3 9.5 6.4 5 12 5Zm0 2C7.8 7 4.4 10.2 3.5 11.5 4.4 12.8 7.8 16 12 16s7.6-3.2 8.5-4.5C19.6 10.2 16.2 7 12 7Zm0 2.2A2.8 2.8 0 1 1 12 15a2.8 2.8 0 0 1 0-5.6Zm0 1.8a1 1 0 1 0 0 2 1 1 0 0 0 0-2Z"></path>' +
        '<path class="wb-eye-slash" d="M4 4l16 16" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"></path>' +
        "</svg>" +
        "</span>"
      );
    }

    function _buildTrashIconHtml(isExcludedFlag) {
      var excludedAttr = isExcludedFlag ? ' data-excluded="1"' : "";
      return (
        '<span class="wb-trash-icon"' + excludedAttr + ' aria-hidden="true">' +
        '<svg viewBox="0 0 24 24" width="14" height="14" focusable="false">' +
        '<path d="M9 3h6l1 2h4v2H4V5h4l1-2Zm1.2 6h1.6v9h-1.6V9Zm4 0h1.6v9h-1.6V9ZM6.8 9h1.6v9H6.8V9ZM7 21h10a2 2 0 0 0 2-2V7H5v12a2 2 0 0 0 2 2Z" fill="currentColor"></path>' +
        "</svg>" +
        "</span>"
      );
    }

    function _isAllLayerKeysHidden(keys) {
      var arr = Array.isArray(keys) ? keys : [];
      if (!flattenGroupTreeController || !flattenGroupTreeController.isLayerHidden) return false;
      if (!arr || arr.length <= 0) return false;
      for (var i = 0; i < arr.length; i++) {
        if (!flattenGroupTreeController.isLayerHidden(String(arr[i] || ""))) {
          return false;
        }
      }
      return true;
    }

    function _isAllLayerKeysExcluded(keys) {
      var arr = Array.isArray(keys) ? keys : [];
      if (!flattenGroupTreeController || !flattenGroupTreeController.isLayerExcluded) return false;
      if (!arr || arr.length <= 0) return false;
      for (var i = 0; i < arr.length; i++) {
        if (!flattenGroupTreeController.isLayerExcluded(String(arr[i] || ""))) {
          return false;
        }
      }
      return true;
    }

    function _getLayerKeysForWidget(w) {
      if (!w) return [];
      // 严格口径：导出控件与扁平层一一对应（导出端写入 __flat_layer_key -> flat_layer_key）
      var explicit = String(w.flat_layer_key || "").trim();
      if (explicit) {
        return [explicit];
      }
      return [];
    }

    function _getBestLayerKeyForWidget(w) {
      if (!w) return "";
      // 优先：导出端写入的精确映射（__flat_layer_key -> flat_layer_key）
      var explicit = String(w.flat_layer_key || "").trim();
      if (explicit) return explicit;
      return "";
    }

    var groupToggleHtml = (groupKey && groupKey !== "__no_group_key__")
      ? (
        '<button type="button" class="wb-tree-toggle wb-tree-eye" data-toggle-kind="group" data-group-key="' + escapeHtmlText(groupKey) + '" aria-label="' + (isHidden ? "显示" : "隐藏") + '" title="' + (isHidden ? "点击显示" : "点击隐藏") + '">' +
        _buildEyeIconHtml(isHidden) +
        "</button>"
      )
      : "";
    var isGroupExcluded = !!(flattenGroupTreeController && flattenGroupTreeController.isGroupExcluded && groupKey && groupKey !== "__no_group_key__" && flattenGroupTreeController.isGroupExcluded(groupKey));
    var groupTrashHtml = (groupKey && groupKey !== "__no_group_key__")
      ? (
        '<button type="button" class="wb-tree-toggle wb-tree-trash" data-toggle-kind="group" data-toggle-action="exclude" data-group-key="' + escapeHtmlText(groupKey) + '" aria-label="' + (isGroupExcluded ? "取消排除" : "排除导出") + '" title="' + (isGroupExcluded ? "点击取消排除" : "点击排除导出（GIL/GIA）") + '">' +
        _buildTrashIconHtml(isGroupExcluded) +
        "</button>"
      )
      : "";
    var niceGroupTitle = "";
    if (flattenGroupTreeController && flattenGroupTreeController.getGroupDisplayName && groupKey && groupKey !== "__no_group_key__") {
      niceGroupTitle = String(flattenGroupTreeController.getGroupDisplayName(groupKey) || "").trim();
    }
    var title = groupKey === "__no_group_key__" ? "（无分组 key）" : (niceGroupTitle || groupKey);
    // 完全对齐 group_tree：details/summary 结构 + tag + wb-tree-meta
    var willGroup = widgets.length >= 2;
    var tagHtml = willGroup ? '<span class="tag">组</span>' : '<span class="tag warn">单项</span>';
    var stateTagHtml = _stateTagHtmlForGroupWidgets(widgets);
    var expanderHtml = '<button type="button" class="wb-tree-expander" data-expander="1" aria-label="展开/折叠" title="展开/折叠"></button>';
    var titleHtml = escapeHtmlText(title);
    if (niceGroupTitle && niceGroupTitle !== groupKey) {
      titleHtml += ' <span class="muted">(' + escapeHtmlText(groupKey) + ")</span>";
    }
    var summaryText =
      '<span class="wb-tree-row">' +
      groupToggleHtml +
      groupTrashHtml +
      expanderHtml +
      tagHtml +
      '<span class="wb-tree-title">' + titleHtml + "</span>" +
      ' <span class="wb-tree-meta">(' + String(widgets.length) + ")</span>" +
      stateTagHtml +
      "</span>";
    if (q) {
      var hitGroup = _match(groupKey) || _match(title);
      if (!hitGroup) {
        var anyHit = false;
        for (var wi0 = 0; wi0 < widgets.length; wi0++) {
          var w0 = widgets[wi0] || {};
          if (_match(w0.widget_name) || _match(w0.widget_id) || _match(w0.ui_key) || _match(w0.widget_type)) {
            anyHit = true;
            break;
          }
        }
        if (!anyHit) {
          continue;
        }
      }
    }

    // 单项：不要渲染为“组块(details)”样式，直接渲染为单行条目
    if (!willGroup) {
      var only = widgets && widgets.length > 0 ? widgets[0] : null;
      if (only && String(only.widget_id || "").trim()) {
        var wid0 = String(only.widget_id || "");
        var wt0 = String(only.widget_type || "");
        var wn0 = String(only.widget_name || "");
        var uiKey0 = String(only.ui_key || "");
        var display0 = wn0 || wid0 || uiKey0 || "widget";
        var stateHtml0 = _stateTagHtmlForWidget(only);
        var layerKeys0 = _getLayerKeysForWidget(only);
        var bestKey0 = _getBestLayerKeyForWidget(only);
        var isSelected0 = !!(state && String(state.exportSelectedWidgetId || "") === wid0);
        // 语义拆分：
        // - 眼睛图标：仅表示“调试显隐（display:none）”，不表达初始态/状态预览；
        // - 初始隐藏（initial_visible=false）用列表行底色做提示（见 wb-tree-initial-hidden）。
        var isInitialHidden0 = !!(only && only.is_multi_state && only.initial_visible === false);
        var isWidgetHidden0 = isHidden || (bestKey0 && flattenGroupTreeController && flattenGroupTreeController.isLayerHidden ? !!flattenGroupTreeController.isLayerHidden(bestKey0) : _isAllLayerKeysHidden(layerKeys0));
        var isWidgetExcluded0 = isGroupExcluded || (bestKey0 && flattenGroupTreeController && flattenGroupTreeController.isLayerExcluded ? !!flattenGroupTreeController.isLayerExcluded(bestKey0) : _isAllLayerKeysExcluded(layerKeys0));
        var widgetToggle0 = (groupKey && groupKey !== "__no_group_key__" && wid0)
          ? (
            '<button type="button" class="wb-tree-toggle wb-tree-eye" data-toggle-kind="widget" data-widget-id="' + escapeHtmlText(wid0) + '" data-group-key="' + escapeHtmlText(groupKey) + '" aria-label="' + (isWidgetHidden0 ? "显示" : "隐藏") + '" title="' + (isWidgetHidden0 ? "点击显示" : "点击隐藏") + '">' +
            _buildEyeIconHtml(isWidgetHidden0) +
            "</button>"
          )
          : "";
        var widgetTrash0 = (groupKey && groupKey !== "__no_group_key__" && wid0)
          ? (
            '<button type="button" class="wb-tree-toggle wb-tree-trash" data-toggle-kind="widget" data-toggle-action="exclude" data-widget-id="' + escapeHtmlText(wid0) + '" data-group-key="' + escapeHtmlText(groupKey) + '" aria-label="' + (isWidgetExcluded0 ? "取消排除" : "排除导出") + '" title="' + (isWidgetExcluded0 ? "点击取消排除" : "点击排除导出（GIL/GIA）") + '">' +
            _buildTrashIconHtml(isWidgetExcluded0) +
            "</button>"
          )
          : "";
        htmlParts.push(
          '<div class="wb-tree-item' + (isSelected0 ? " selected" : "") + (isInitialHidden0 ? " wb-tree-initial-hidden" : "") + '" role="button" tabindex="0"' +
          ' data-export-widget="1"' +
          ' data-widget-id="' + escapeHtmlText(wid0) + '"' +
          (uiKey0 ? (' data-ui-key="' + escapeHtmlText(uiKey0) + '"') : "") +
          ' data-flat-layer-key="' + escapeHtmlText(String(bestKey0 || "")) + '"' +
          ' data-group-key="' + escapeHtmlText(groupKey) + '"' +
          ' title="' + escapeHtmlText(display0) + '">' +
          widgetToggle0 +
          widgetTrash0 +
          '<span class="wb-tree-item-main">' +
          (wt0 ? ('<span class="muted">[' + escapeHtmlText(wt0) + "]</span> ") : "") +
          escapeHtmlText(display0) +
          (uiKey0 ? (' <span class="muted">(' + escapeHtmlText(uiKey0) + ")</span>") : "") +
          "</span>" +
          stateHtml0 +
          "</div>"
        );
      }
      continue;
    }

    htmlParts.push('<details open data-group-key="' + escapeHtmlText(groupKey) + '">');
    htmlParts.push("<summary>" + summaryText + "</summary>");
    htmlParts.push('<div class="wb-tree-children">');

    for (var wi = 0; wi < widgets.length; wi++) {
      var w = widgets[wi] || {};
      var wt = String(w.widget_type || "");
      var wn = String(w.widget_name || "");
      var wid = String(w.widget_id || "");
      var uiKey = String(w.ui_key || "");
      var isInteractive = !!w.can_interact;
      var code = Number(w.interact_code || 0);
      var leftMeta = wt;
      if (isInteractive && code > 0) leftMeta = leftMeta ? (leftMeta + " · 交互#" + String(code)) : ("交互#" + String(code));
      if (isInteractive && code <= 0) leftMeta = leftMeta ? (leftMeta + " · 交互") : "交互";

      var displayName = wn || wid || uiKey || ("widget_" + String(wi));
      var isSelected = !!(state.exportSelectedWidgetId && wid && String(state.exportSelectedWidgetId) === wid);
      var stateHtml = _stateTagHtmlForWidget(w);
      var layerKeysForWidget = _getLayerKeysForWidget(w);
      var bestKeyForWidget = _getBestLayerKeyForWidget(w);
      var isInitialHidden = !!(w && w.is_multi_state && w.initial_visible === false);
      var isWidgetHidden = isHidden || (bestKeyForWidget && flattenGroupTreeController && flattenGroupTreeController.isLayerHidden ? !!flattenGroupTreeController.isLayerHidden(bestKeyForWidget) : _isAllLayerKeysHidden(layerKeysForWidget));
      var isWidgetExcluded = isGroupExcluded || (bestKeyForWidget && flattenGroupTreeController && flattenGroupTreeController.isLayerExcluded ? !!flattenGroupTreeController.isLayerExcluded(bestKeyForWidget) : _isAllLayerKeysExcluded(layerKeysForWidget));
      var widgetToggleHtml = (groupKey && groupKey !== "__no_group_key__" && wid)
        ? (
          '<button type="button" class="wb-tree-toggle wb-tree-eye" data-toggle-kind="widget" data-widget-id="' + escapeHtmlText(wid) + '" data-group-key="' + escapeHtmlText(groupKey) + '" aria-label="' + (isWidgetHidden ? "显示" : "隐藏") + '" title="' + (isWidgetHidden ? "点击显示" : "点击隐藏") + '">' +
          _buildEyeIconHtml(isWidgetHidden) +
          "</button>"
        )
        : "";
      var widgetTrashHtml = (groupKey && groupKey !== "__no_group_key__" && wid)
        ? (
          '<button type="button" class="wb-tree-toggle wb-tree-trash" data-toggle-kind="widget" data-toggle-action="exclude" data-widget-id="' + escapeHtmlText(wid) + '" data-group-key="' + escapeHtmlText(groupKey) + '" aria-label="' + (isWidgetExcluded ? "取消排除" : "排除导出") + '" title="' + (isWidgetExcluded ? "点击取消排除" : "点击排除导出（GIL/GIA）") + '">' +
          _buildTrashIconHtml(isWidgetExcluded) +
          "</button>"
        )
        : "";

      if (q && !_match(displayName) && !_match(wid) && !_match(uiKey) && !_match(wt) && !_match(w.ui_state_group) && !_match(w.ui_state)) {
        continue;
      }
      htmlParts.push(
        '<div class="wb-tree-item' + (isSelected ? " selected" : "") + (isInitialHidden ? " wb-tree-initial-hidden" : "") + '" role="button" tabindex="0"' +
        ' data-export-widget="1"' +
        ' data-widget-id="' + escapeHtmlText(wid) + '"' +
        (uiKey ? (' data-ui-key="' + escapeHtmlText(uiKey) + '"') : "") +
        ' data-flat-layer-key="' + escapeHtmlText(String(bestKeyForWidget || "")) + '"' +
        ' data-group-key="' + escapeHtmlText(groupKey) + '"' +
        ' title="' + escapeHtmlText(displayName) + '">' +
        widgetToggleHtml +
        widgetTrashHtml +
        '<span class="wb-tree-item-main">' +
        (leftMeta ? ('<span class="muted">[' + escapeHtmlText(leftMeta) + "]</span> ") : "") +
        escapeHtmlText(displayName) +
        (uiKey ? (' <span class="muted">(' + escapeHtmlText(uiKey) + ")</span>") : "") +
        "</span>" +
        stateHtml +
        "</div>"
      );
    }
    htmlParts.push("</div>");
    htmlParts.push("</details>");
  }

  return htmlParts.join("\n");
}

