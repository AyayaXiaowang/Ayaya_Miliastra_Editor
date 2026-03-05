export function isAutotestSelectEnabled() {
  // 保持与旧实现一致：支持 ?autotest_select=1/true/yes
  // 注意：不吞错，URLSearchParams 若异常会直接抛出，便于暴露环境问题。
  var sp = new URLSearchParams(String(window.location && window.location.search ? window.location.search : ""));
  var v = String(sp.get("autotest_select") || "").trim();
  var lowered = v.toLowerCase();
  return v === "1" || lowered === "true" || lowered === "yes";
}

export function isDerivedHtmlFileName(fileName) {
  var n = String(fileName || "").toLowerCase();
  return n.endsWith(".flattened.html") || n.indexOf(".autofix.flattened.html") >= 0;
}

export function removeHtmlExt(fileName) {
  return String(fileName || "").replace(/\.html?$/i, "");
}

export function pickFlattenedCandidate(baseFileName, allItems) {
  // 优先级：
  // 1) <stem>.autofix.flattened.html
  // 2) <stem>.flattened.html
  // 3) null
  var stem = removeHtmlExt(baseFileName);
  var autoFixName = stem + ".autofix.flattened.html";
  var flattenedName = stem + ".flattened.html";
  var i;
  for (i = 0; i < allItems.length; i++) {
    if (String(allItems[i].file_name || "") === autoFixName) return autoFixName;
  }
  for (i = 0; i < allItems.length; i++) {
    if (String(allItems[i].file_name || "") === flattenedName) return flattenedName;
  }
  return null;
}

