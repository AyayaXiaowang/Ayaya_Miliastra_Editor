import { extractDisplayElementsData, generateFlattenedDivs } from "/__ui_workbench__/src/flatten.js";

const OVERLAY_ROOT_ID = "local-sim-flatten-overlay";
const MODE_STYLE_ID = "local-sim-flatten-mode-style";
const MODE_ATTR = "data-local-sim-flatten";
const READY_ATTR = "data-local-sim-flatten-ready";

function _getQueryParam(name) {
  const ns = (window && window.__LOCAL_SIM__) ? window.__LOCAL_SIM__ : null;
  if (ns && typeof ns.getQueryParam === "function") {
    return String(ns.getQueryParam(name) || "");
  }
  const sp = new URLSearchParams(String(window.location && window.location.search ? window.location.search : ""));
  return String(sp.get(String(name || "")) || "");
}

function _isEnabledByQuery() {
  const ns = (window && window.__LOCAL_SIM__) ? window.__LOCAL_SIM__ : null;
  const raw = (_getQueryParam("flatten") || _getQueryParam("flat") || "").trim();
  if (ns && typeof ns.isTruthyParam === "function") {
    return !!ns.isTruthyParam(raw);
  }
  const t = raw.toLowerCase();
  return t === "1" || t === "true" || t === "yes" || t === "on";
}

function _ensureModeStyle() {
  let style = document.getElementById(MODE_STYLE_ID);
  if (style) return style;
  style = document.createElement("style");
  style.id = MODE_STYLE_ID;
  style.textContent = `
html[${MODE_ATTR}="1"][${READY_ATTR}="1"] body > *:not(#${OVERLAY_ROOT_ID}):not(#local-sim-badge):not(#local-sim-highlight-dim){
  opacity: 0 !important;
}
#${OVERLAY_ROOT_ID}{
  position: fixed;
  left: 0;
  top: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
  pointer-events: none;
  z-index: 6000;
}
#${OVERLAY_ROOT_ID}, #${OVERLAY_ROOT_ID} *{
  pointer-events: none !important;
}
#${OVERLAY_ROOT_ID} .flat-shadow[data-ui-state-group]:not([data-ui-state-default="1"]),
#${OVERLAY_ROOT_ID} .flat-border[data-ui-state-group]:not([data-ui-state-default="1"]),
#${OVERLAY_ROOT_ID} .flat-element[data-ui-state-group]:not([data-ui-state-default="1"]),
#${OVERLAY_ROOT_ID} .flat-text[data-ui-state-group]:not([data-ui-state-default="1"]),
#${OVERLAY_ROOT_ID} .flat-button-anchor[data-ui-state-group]:not([data-ui-state-default="1"]){
  visibility: hidden;
}
`;
  document.head.appendChild(style);
  return style;
}

function _removeOverlayIfAny() {
  const existing = document.getElementById(OVERLAY_ROOT_ID);
  if (existing) existing.remove();
}

function _renderOnce() {
  if (!_isEnabledByQuery()) return;
  if (!document || !document.body) return;

  _ensureModeStyle();
  document.documentElement.setAttribute(MODE_ATTR, "1");
  document.documentElement.setAttribute(READY_ATTR, "0");

  // 重要：先移除旧 overlay，避免 extraction 把 overlay 自己也算进去，越跑越大。
  _removeOverlayIfAny();

  const w = Math.max(1, window.innerWidth || 1);
  const h = Math.max(1, window.innerHeight || 1);
  const sizeKey = String(w) + "---" + String(h);

  // 排除 local_sim 自己的固定层，避免被扁平化进去重复显示。
  const badge = document.getElementById("local-sim-badge");
  const badgePrevDisplay = badge ? String(badge.style.display || "") : "";
  if (badge) badge.style.display = "none";
  const dim = document.getElementById("local-sim-highlight-dim");
  const dimPrevDisplay = dim ? String(dim.style.display || "") : "";
  if (dim) dim.style.display = "none";

  const elementsData = extractDisplayElementsData(document);
  const divsHtml = generateFlattenedDivs(elementsData, sizeKey, {
    diagnostics: null,
    debug_show_groups: false,
    ui_key_prefix: "",
  });

  if (badge) badge.style.display = badgePrevDisplay;
  if (dim) dim.style.display = dimPrevDisplay;

  const root = document.createElement("div");
  root.id = OVERLAY_ROOT_ID;
  root.setAttribute("aria-hidden", "true");
  root.innerHTML = String(divsHtml || "");
  document.body.appendChild(root);
  document.documentElement.setAttribute(READY_ATTR, "1");
}

let _resizeTimer = 0;
function _onResize() {
  if (_resizeTimer) window.clearTimeout(_resizeTimer);
  _resizeTimer = window.setTimeout(() => {
    _resizeTimer = 0;
    _renderOnce();
  }, 120);
}

function _scheduleInitialRender() {
  // 给浏览器 2 帧时间完成 layout（避免早期 getBoundingClientRect 为 0 的偶发场景）。
  window.requestAnimationFrame(() => {
    window.requestAnimationFrame(() => {
      _renderOnce();
    });
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    _scheduleInitialRender();
  });
} else {
  _scheduleInitialRender();
}

window.addEventListener("resize", _onResize);

