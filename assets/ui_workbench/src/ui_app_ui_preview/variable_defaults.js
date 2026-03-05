export function extractVariableDefaultsFromHtmlText(htmlText) {
  // 从“源码文本”提取 data-ui-variable-defaults。
  //
  // 约定：任意元素可声明：
  //   data-ui-variable-defaults='{"关卡.foo":1,"lv.level_01_name":"第一关","lv.UI选关_列表":{"cleared_count":0}}'
  //
  // 多个声明会按 DOM 顺序合并，后者覆盖前者同名 key。
  // 注意：必须基于 source_html（而非 computeDoc.outerHTML），避免极端情况下 compute iframe/autofix 序列化丢失自定义属性。
  var raw = String(htmlText || "");
  if (!raw.trim()) {
    return {};
  }
  if (typeof DOMParser === "undefined") {
    return {};
  }
  var parser = new DOMParser();
  var doc = parser.parseFromString(raw, "text/html");
  if (!doc || !doc.querySelectorAll) {
    return {};
  }
  var nodes = doc.querySelectorAll("[data-ui-variable-defaults]");
  if (!nodes || nodes.length <= 0) {
    return {};
  }
  var out = {};
  for (var i = 0; i < nodes.length; i++) {
    var el = nodes[i];
    if (!el || !el.getAttribute) {
      continue;
    }
    var text = String(el.getAttribute("data-ui-variable-defaults") || "").trim();
    if (!text) {
      continue;
    }
    var parsed = JSON.parse(text);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("data-ui-variable-defaults 必须是 JSON object，例如 {\"关卡.hp\":100}。");
    }
    for (var k in parsed) {
      if (!Object.prototype.hasOwnProperty.call(parsed, k)) {
        continue;
      }
      var key = String(k || "").trim();
      if (!key) {
        continue;
      }
      out[key] = parsed[k];
    }
  }
  return out;
}

