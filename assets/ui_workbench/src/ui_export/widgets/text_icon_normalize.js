import { analyzeTextForIconOnly, removeEmojiChars } from "../text_icon.js";

export function normalizeIconAndTextLayer(rawText, layerItem, warnings) {
    var raw = String(rawText || "");
    var analysis = analyzeTextForIconOnly(raw);
    if (analysis.kind === "single_icon_only") {
        return { kind: "single_icon_only", text: raw, analysis: analysis };
    }
    if (analysis.kind === "mixed_text_and_icon") {
        if (warnings) {
            warnings.push("文本与 ICON 混排不支持：将忽略 ICON，仅保留文本（如需 ICON，请单独放一个元素）：[" + String(layerItem && layerItem.debugLabel ? layerItem.debugLabel : "") + "] " + String(raw || ""));
        }
        return { kind: "plain_text", text: String(analysis.text_without_emoji || "").trim(), analysis: analysis };
    }
    if (analysis.kind === "multi_icon_only") {
        if (warnings) {
            warnings.push("检测到多个 ICON（" + String(analysis.icon_count || 0) + " 个），无法自动转换为道具展示；请拆分为多个元素：[" + String(layerItem && layerItem.debugLabel ? layerItem.debugLabel : "") + "] " + String(raw || ""));
        }
        return { kind: "empty", text: "", analysis: analysis };
    }
    return { kind: "plain_text", text: removeEmojiChars(raw), analysis: analysis };
}

