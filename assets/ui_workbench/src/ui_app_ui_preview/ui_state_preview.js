import { dom, state } from "./context.js";
import * as preview from "../preview/index.js";

function _cssEscapeText(text) {
  var raw = String(text || "");
  if (window.CSS && typeof window.CSS.escape === "function") {
    return window.CSS.escape(raw);
  }
  // 简易兜底：覆盖引号/反斜杠等常见字符即可
  return raw.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

function _parseUiStateBool(text) {
  var lowered = String(text || "").trim().toLowerCase();
  if (!lowered) return false;
  return lowered === "1" || lowered === "true" || lowered === "yes" || lowered === "on";
}

function _getEffectiveUiStateGroup(el) {
  if (!el) return "";
  if (el.getAttribute && el.hasAttribute && el.hasAttribute("data-ui-state-group")) {
    return String(el.getAttribute("data-ui-state-group") || "").trim();
  }
  var cur = el.parentElement;
  while (cur) {
    if (cur.getAttribute && cur.hasAttribute && cur.hasAttribute("data-ui-state-group")) {
      return String(cur.getAttribute("data-ui-state-group") || "").trim();
    }
    cur = cur.parentElement;
  }
  return "";
}

function _scanUiStateInitialOverridesFromDocument(doc) {
  if (!doc || !doc.querySelector) return null;
  // 约定：页面可在任意元素上声明预览初始状态覆盖（仅预览，不影响导出/写回）。
  // 优先读取 data-ui-preview-initial-states；兼容 data-ui-initial-states 作为简写。
  var el = doc.querySelector("[data-ui-preview-initial-states]") || doc.querySelector("[data-ui-initial-states]");
  if (!el || !el.getAttribute) return null;
  var raw = String(
    el.getAttribute("data-ui-preview-initial-states")
    || el.getAttribute("data-ui-initial-states")
    || ""
  ).trim();
  if (!raw) return null;

  // 格式（推荐）：
  //   tutorial_overlay=hidden; tutorial_countdown_state=hidden; help_btn_state=show
  // 分隔符：; , | 换行（含中文；/，）
  // 键值分隔：= 或 :
  var parts = raw.split(/[;,\n|；，]+/g);
  var out = {};
  for (var i = 0; i < parts.length; i++) {
    var p = String(parts[i] || "").trim();
    if (!p) continue;
    var idx = p.indexOf("=");
    if (idx < 0) idx = p.indexOf(":");
    if (idx < 0) continue;
    var g = String(p.slice(0, idx) || "").trim();
    var st = String(p.slice(idx + 1) || "").trim();
    if (!g) continue;
    out[g] = st;
  }
  return Object.keys(out).length > 0 ? out : null;
}

function _scanUiStateInitialOverridesFromHtmlText(htmlText) {
  var raw = String(htmlText || "").trim();
  if (!raw) return null;
  // 注意：不吞错。DOMParser 在标准浏览器下不会抛错，只会返回一个可查询的 Document。
  var doc = new DOMParser().parseFromString(raw, "text/html");
  return _scanUiStateInitialOverridesFromDocument(doc);
}

function _scanUiStatePreviewBaseOverridesFromDocument(doc) {
  if (!doc || !doc.querySelector) return null;
  // 约定：页面可声明“状态预览基底”（仅预览，不影响导出/写回）。
  // 当用户在工具条选择了某个状态组进行预览时，会先应用该基底（通常用于隐藏遮罩/教程等干扰层），
  // 再应用用户选择的“单组覆盖”。
  var el = doc.querySelector("[data-ui-preview-state-preview-base-states]") || doc.querySelector("[data-ui-state-preview-base-states]");
  if (!el || !el.getAttribute) return null;
  var raw = String(
    el.getAttribute("data-ui-preview-state-preview-base-states")
    || el.getAttribute("data-ui-state-preview-base-states")
    || ""
  ).trim();
  if (!raw) return null;

  var parts = raw.split(/[;,\n|；，]+/g);
  var out = {};
  for (var i = 0; i < parts.length; i++) {
    var p = String(parts[i] || "").trim();
    if (!p) continue;
    var idx = p.indexOf("=");
    if (idx < 0) idx = p.indexOf(":");
    if (idx < 0) continue;
    var g = String(p.slice(0, idx) || "").trim();
    var st = String(p.slice(idx + 1) || "").trim();
    if (!g) continue;
    out[g] = st;
  }
  return Object.keys(out).length > 0 ? out : null;
}

function _scanUiStatePreviewBaseOverridesFromHtmlText(htmlText) {
  var raw = String(htmlText || "").trim();
  if (!raw) return null;
  var doc = new DOMParser().parseFromString(raw, "text/html");
  return _scanUiStatePreviewBaseOverridesFromDocument(doc);
}

function _scanUiStateCatalogFromDocument(doc) {
  if (!doc || !doc.querySelectorAll) {
    return { groups: [] };
  }
  // 兼容两种写法：
  // 1) 逐 state 元素声明：data-ui-state-group + data-ui-state（常见：enabled/disabled 按钮）
  // 2) 组根节点声明 group：data-ui-state-group 写在父容器，子节点仅写 data-ui-state（常见：overlay 多页）
  // 因此 catalog 必须从“state 节点”扫描，并按“最近 state-group 祖先”归属到组。
  var nodes = doc.querySelectorAll("[data-ui-state]");
  var groupMap = {}; // group -> { statesSet: {state:1}, defaultState: string|null }
  for (var i = 0; i < nodes.length; i++) {
    var el = nodes[i];
    if (!el || !el.getAttribute) continue;
    var group = _getEffectiveUiStateGroup(el);
    if (!group) continue;
    var st = String(el.getAttribute("data-ui-state") || "").trim();
    var isDefault = _parseUiStateBool(el.getAttribute("data-ui-state-default"));
    if (!groupMap[group]) {
      groupMap[group] = { statesSet: {}, defaultState: null };
    }
    groupMap[group].statesSet[st] = 1;
    if (isDefault && groupMap[group].defaultState === null) {
      groupMap[group].defaultState = st;
    }
  }
  var groups = [];
  var groupKeys = Object.keys(groupMap).sort(function (a, b) { return a.localeCompare(b); });
  for (var gi = 0; gi < groupKeys.length; gi++) {
    var g = groupKeys[gi];
    var entry = groupMap[g];
    var states = Object.keys(entry.statesSet).sort(function (a, b) { return a.localeCompare(b); });
    groups.push({ group: g, states: states, defaultState: entry.defaultState });
  }
  return { groups: groups };
}

export function resetAllUiStatePreviewOverrides(doc) {
  if (!doc || !doc.querySelectorAll) return;
  var nodes = doc.querySelectorAll("[data-ui-state-preview-override='1']");
  for (var i = 0; i < nodes.length; i++) {
    var el = nodes[i];
    if (!el || !el.style) continue;
    var origVis = el.getAttribute ? String(el.getAttribute("data-ui-state-preview-orig-visibility") || "") : "";
    var origPe = el.getAttribute ? String(el.getAttribute("data-ui-state-preview-orig-pointer-events") || "") : "";
    el.style.visibility = origVis;
    el.style.pointerEvents = origPe;
    el.removeAttribute("data-ui-state-preview-override");
    el.removeAttribute("data-ui-state-preview-orig-visibility");
    el.removeAttribute("data-ui-state-preview-orig-pointer-events");
  }
}

function _applyUiStateOverride(doc, group, stateName) {
  if (!doc || !doc.querySelectorAll) return;
  var g = String(group || "").trim();
  if (!g) return;
  var desired = String(stateName || "").trim();
  // 注意：只对“state 节点”应用覆盖，不能把 group 根节点本身当 state 去隐藏，
  // 否则会导致 overlay 根容器（无 data-ui-state）被错误隐藏。
  var nodes = doc.querySelectorAll("[data-ui-state]");
  for (var i = 0; i < nodes.length; i++) {
    var el = nodes[i];
    if (!el || !el.getAttribute || !el.style) continue;
    var group0 = _getEffectiveUiStateGroup(el);
    if (group0 !== g) continue;
    var st = String(el.getAttribute("data-ui-state") || "").trim();
    var isMatch = st === desired;
    if (!el.getAttribute("data-ui-state-preview-override")) {
      // 记录原始 inline style（避免 reset 时丢失作者写死的 visibility/pointer-events）
      el.setAttribute("data-ui-state-preview-orig-visibility", String(el.style.visibility || ""));
      el.setAttribute("data-ui-state-preview-orig-pointer-events", String(el.style.pointerEvents || ""));
    }
    el.setAttribute("data-ui-state-preview-override", "1");
    el.style.visibility = isMatch ? "visible" : "hidden";
    el.style.pointerEvents = isMatch ? "" : "none";
  }
}

export function renderUiStateSelectorsFromCatalog(catalog) {
  if (!dom.uiStateGroupSelect || !dom.uiStateValueSelect) return;
  var groups = (catalog && catalog.groups) ? catalog.groups : [];

  function setOptions(selectEl, options, selectedValue) {
    selectEl.innerHTML = "";
    for (var i = 0; i < options.length; i++) {
      var opt = options[i];
      var o = document.createElement("option");
      o.value = String(opt.value);
      o.textContent = String(opt.label);
      selectEl.appendChild(o);
    }
    selectEl.value = String(selectedValue || "");
  }

  if (!groups || groups.length <= 0) {
    setOptions(dom.uiStateGroupSelect, [{ value: "", label: "（无多状态）" }], "");
    setOptions(dom.uiStateValueSelect, [{ value: "", label: "（-）" }], "");
    dom.uiStateGroupSelect.disabled = true;
    dom.uiStateValueSelect.disabled = true;
    return;
  }

  dom.uiStateGroupSelect.disabled = false;
  var groupOptions = [{ value: "", label: "（按页面初始态）" }];
  for (var gi = 0; gi < groups.length; gi++) {
    groupOptions.push({ value: groups[gi].group, label: groups[gi].group });
  }

  var curGroup = String(state.uiStatePreview.group || "").trim();
  var groupExists = false;
  for (var g0 = 0; g0 < groupOptions.length; g0++) {
    if (String(groupOptions[g0].value) === curGroup) { groupExists = true; break; }
  }
  if (!groupExists) curGroup = "";
  setOptions(dom.uiStateGroupSelect, groupOptions, curGroup);

  if (!curGroup) {
    setOptions(dom.uiStateValueSelect, [{ value: "", label: "（-）" }], "");
    dom.uiStateValueSelect.disabled = true;
    return;
  }

  dom.uiStateValueSelect.disabled = false;
  var groupEntry = null;
  for (var gx = 0; gx < groups.length; gx++) {
    if (groups[gx].group === curGroup) { groupEntry = groups[gx]; break; }
  }
  var states = groupEntry ? (groupEntry.states || []) : [];
  var stateOptions = [];
  for (var si = 0; si < states.length; si++) {
    var sv = String(states[si] || "");
    stateOptions.push({ value: sv, label: sv ? sv : "（默认/空）" });
  }

  var curState = String(state.uiStatePreview.state || "");
  var stateExists = false;
  for (var s0 = 0; s0 < stateOptions.length; s0++) {
    if (String(stateOptions[s0].value) === curState) { stateExists = true; break; }
  }
  if (!stateExists) {
    curState = (groupEntry && groupEntry.defaultState !== null)
      ? String(groupEntry.defaultState || "")
      : (stateOptions.length > 0 ? String(stateOptions[0].value) : "");
    state.uiStatePreview.state = curState;
  }
  setOptions(dom.uiStateValueSelect, stateOptions, curState);
}

export function syncUiStatePreviewUiAndApply() {
  var doc = preview.getPreviewDocument ? preview.getPreviewDocument() : null;
  if (!doc) return;
  var catalog = _scanUiStateCatalogFromDocument(doc);
  renderUiStateSelectorsFromCatalog(catalog);

  // 覆盖应用顺序：
  // 1) reset（清空上次预览覆盖）
  // 2) 页面声明的“预览初始态覆盖”（可多组叠加）
  // 3) 临时状态预览覆盖（单组；用于临时切换某个状态组）
  resetAllUiStatePreviewOverrides(doc);

  var initial = _scanUiStateInitialOverridesFromDocument(doc);
  // 关键：扁平化预览会“替换 <body> 内容”为 flat layers，源码中的根容器可能已不存在。
  // 因此若在预览 DOM 中找不到声明，则回退从“源 HTML 文本”解析声明。
  if (!initial) {
    var sourceHtmlText = state && state.selected ? String(state.selected.source_html || "") : "";
    if (String(sourceHtmlText || "").trim()) {
      initial = _scanUiStateInitialOverridesFromHtmlText(sourceHtmlText);
    }
  }
  if (initial) {
    var keys = Object.keys(initial).sort(function (a, b) { return a.localeCompare(b); });
    for (var i = 0; i < keys.length; i++) {
      var g = String(keys[i] || "").trim();
      if (!g) continue;
      _applyUiStateOverride(doc, g, initial[g]);
    }
  }

  var activeGroup = String(state.uiStatePreview.group || "").trim();
  if (activeGroup) {
    // 当用户开启“状态预览”（选择了某个 group）时，先应用页面声明的“预览基底”，
    // 用于自动隐藏教程/遮罩等干扰层，避免必须手动切多个组。
    var base0 = _scanUiStatePreviewBaseOverridesFromDocument(doc);
    if (!base0) {
      var sourceHtmlText = state && state.selected ? String(state.selected.source_html || "") : "";
      if (String(sourceHtmlText || "").trim()) {
        base0 = _scanUiStatePreviewBaseOverridesFromHtmlText(sourceHtmlText);
      }
    }
    if (base0) {
      var baseKeys = Object.keys(base0).sort(function (a, b) { return a.localeCompare(b); });
      for (var bi = 0; bi < baseKeys.length; bi++) {
        var bg = String(baseKeys[bi] || "").trim();
        if (!bg) continue;
        _applyUiStateOverride(doc, bg, base0[bg]);
      }
    }
  }

  if (activeGroup) {
    _applyUiStateOverride(doc, state.uiStatePreview.group, state.uiStatePreview.state);
  }
}

