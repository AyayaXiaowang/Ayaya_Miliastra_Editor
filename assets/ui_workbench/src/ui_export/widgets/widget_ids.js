import { sanitizeIdPart } from "../keys.js";

export function buildWidgetId(prefix, kind, source, zIndex) {
    var idPart = source && source.id ? sanitizeIdPart(source.id) : "";
    var labelPart = source && source.attributes && source.attributes.dataDebugLabel ? sanitizeIdPart(source.attributes.dataDebugLabel) : "";
    var classPart = source && source.dataLabel ? sanitizeIdPart(source.dataLabel) : "";
    var parts = [prefix, kind];
    if (idPart) {
        parts.push(idPart);
    } else if (labelPart) {
        parts.push(labelPart);
    } else if (classPart) {
        parts.push(classPart);
    } else if (source && Number.isFinite(source.elementIndex)) {
        parts.push("e" + String(source.elementIndex));
    }
    if (Number.isFinite(zIndex)) {
        parts.push("z" + String(Math.trunc(zIndex)));
    }
    return parts.filter(function (part) { return !!part; }).join("_");
}

