export function rectIntersectionArea(a, b) {
  if (!a || !b) return 0;
  var left = Math.max(Number(a.left || 0), Number(b.left || 0));
  var top = Math.max(Number(a.top || 0), Number(b.top || 0));
  var right = Math.min(Number(a.left || 0) + Number(a.width || 0), Number(b.left || 0) + Number(b.width || 0));
  var bottom = Math.min(Number(a.top || 0) + Number(a.height || 0), Number(b.top || 0) + Number(b.height || 0));
  var w = right - left;
  var h = bottom - top;
  if (!isFinite(w) || !isFinite(h) || w <= 0 || h <= 0) return 0;
  return w * h;
}

export function getFlatRectFromElementStyle(el) {
  if (!el || !el.style) return null;
  function _parsePx(text) {
    var raw = String(text || "").trim().toLowerCase();
    if (!raw) return null;
    if (raw.endsWith("px")) raw = raw.slice(0, -2);
    var n = Number(raw);
    return isFinite(n) ? n : null;
  }
  var left = _parsePx(el.style.left);
  var top = _parsePx(el.style.top);
  var width = _parsePx(el.style.width);
  var height = _parsePx(el.style.height);
  if (left === null || top === null || width === null || height === null) return null;
  if (width <= 0 || height <= 0) return null;
  return { left: Number(left), top: Number(top), width: Number(width), height: Number(height) };
}

export function parseZIndexFromFlatElementStyle(el) {
  if (!el || !el.style) return 0;
  var raw = String(el.style.zIndex || "").trim().toLowerCase();
  if (!raw || raw === "auto") return 0;
  var n = Number(raw);
  if (!isFinite(n)) return 0;
  return Math.trunc(n);
}

export function areaOfRect(r) {
  if (!r) return 0;
  var w = Number(r.width || 0);
  var h = Number(r.height || 0);
  if (!isFinite(w) || !isFinite(h) || w <= 0 || h <= 0) return 0;
  return w * h;
}

export function scoreWidgetMatchForFlatSelection(selectedRect, selectedZ, widgetRect, widgetZ) {
  // Goal: when user clicks a visible top-layer text, do NOT map to an oversized background/group widget.
  // Prefer:
  // - higher overlap ratio (relative to smaller of the two)
  // - closer z-index / layer_index
  // - more "specific" rect (smaller / closer to selected rect size)
  if (!selectedRect || !widgetRect) {
    return null;
  }
  var inter = rectIntersectionArea(selectedRect, widgetRect);
  if (!(inter > 0)) {
    return null;
  }
  var aSel = areaOfRect(selectedRect);
  var aWid = areaOfRect(widgetRect);
  if (!(aSel > 0) || !(aWid > 0)) {
    return null;
  }
  var denom = Math.min(aSel, aWid);
  var ratio = denom > 0 ? (inter / denom) : 0;
  var z0 = Number(selectedZ || 0);
  var z1 = Number(widgetZ || 0);
  if (!isFinite(z0)) z0 = 0;
  if (!isFinite(z1)) z1 = 0;
  var zDist = Math.abs(z1 - z0);
  var areaDist = Math.abs(aWid - aSel);
  return {
    ratio: ratio,
    inter: inter,
    zDist: zDist,
    areaDist: areaDist,
    areaWid: aWid,
  };
}

