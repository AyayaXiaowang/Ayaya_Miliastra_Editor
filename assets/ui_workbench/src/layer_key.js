// LayerKey: single source of truth for "flat layer" identity.
//
// Format (must stay stable across DOM preview, group_tree and export preview):
//   kind__left__top__width__height__round(z)
//
// Notes:
// - rect values are formatted with toFixed(2) to match flattened DOM style serialization.
// - z is rounded to integer via Math.round to reduce drift across sources.
// - parsing is intentionally tolerant (accepts >=6 parts, ignores extra suffix parts).
//
// This module is browser-side ES Module and must NOT use any Node.js APIs.
function _format2(num) {
  var n = Number(num || 0);
  if (!isFinite(n)) {
    n = 0;
  }
  return n.toFixed(2);
}

function _normalizeKind(kind) {
  var k = String(kind || "").trim();
  return k ? k : "layer";
}

function _normalizeZ(zIndex) {
  var z = Number(zIndex || 0);
  if (!isFinite(z)) {
    z = 0;
  }
  return Math.round(z);
}

export function buildLayerKey(kind, left, top, width, height, zIndex) {
  var k = _normalizeKind(kind);
  var z = _normalizeZ(zIndex);
  return [
    k,
    _format2(left),
    _format2(top),
    _format2(width),
    _format2(height),
    String(z)
  ].join("__");
}

export function buildLayerKeyFromRect(kind, rect, zIndex) {
  var r = rect || {};
  return buildLayerKey(
    kind,
    Number(r.left || 0),
    Number(r.top || 0),
    Number(r.width || 0),
    Number(r.height || 0),
    zIndex
  );
}

export function buildPosKey(kind, left, top, width, height) {
  var k = _normalizeKind(kind);
  // must match layerKey rect precision (no z)
  return [
    k,
    _format2(left),
    _format2(top),
    _format2(width),
    _format2(height),
  ].join("__");
}

export function buildPosKeyFromRect(kind, rect) {
  var r = rect || {};
  return buildPosKey(
    kind,
    Number(r.left || 0),
    Number(r.top || 0),
    Number(r.width || 0),
    Number(r.height || 0),
  );
}

export function parseLayerKey(layerKey) {
  var raw = String(layerKey || "").trim();
  if (!raw) {
    return null;
  }
  var parts = raw.split("__");
  if (!parts || parts.length < 6) {
    return null;
  }
  var kind = String(parts[0] || "").trim();
  var left = Number(parts[1]);
  var top = Number(parts[2]);
  var width = Number(parts[3]);
  var height = Number(parts[4]);
  var z = Number(parts[5]);
  if (!kind) {
    return null;
  }
  if (!isFinite(left) || !isFinite(top) || !isFinite(width) || !isFinite(height) || !isFinite(z)) {
    return null;
  }
  var zi = Math.trunc(z);
  return {
    kind: kind,
    left: left,
    top: top,
    width: width,
    height: height,
    z: zi,
    rect: { left: left, top: top, width: width, height: height },
  };
}

