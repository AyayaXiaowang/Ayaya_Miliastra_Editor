export function removeEmojiChars(text) {
    var raw = String(text || "");
    if (!raw) {
        return "";
    }
    // 目标：剔除 “💧 这类 icon/emoji” 文字；保留普通中文/英文/数字与常规标点。
    // 注：这里用“常见 emoji 区段”做过滤，避免依赖 Unicode property escape 的兼容性。
    // - 1F000-1FAFF: 大部分表情与图形符号
    // - 2600-27BF : 杂项符号/丁卯符号中常见 emoji-like 字符
    var cleaned = raw.replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, "");
    cleaned = cleaned.replace(/[\u200D\uFE0E\uFE0F]/g, "");
    cleaned = cleaned.replace(/\s+/g, " ").trim();
    return cleaned;
}

export function hasEmojiChars(text) {
    return /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(String(text || ""));
}

function countGraphemeClusters(text) {
    var s = String(text || "");
    if (!s) {
        return 0;
    }
    if (typeof Intl !== "undefined" && Intl && Intl.Segmenter) {
        var seg = new Intl.Segmenter(undefined, { granularity: "grapheme" });
        var count = 0;
        for (var _it = seg.segment(s)[Symbol.iterator](), _step = _it.next(); !_step.done; _step = _it.next()) {
            count += 1;
        }
        return count;
    }
    return Array.from(s).length;
}

export function analyzeTextForIconOnly(text) {
    var raw = String(text || "");
    var trimmed = raw.replace(/\s+/g, " ").trim();
    if (!trimmed) {
        return { kind: "empty", text: "" };
    }
    if (!hasEmojiChars(trimmed)) {
        return { kind: "plain_text", text: trimmed };
    }

    var noSpace = trimmed.replace(/\s+/g, "");
    var nonEmoji = noSpace.replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, "");
    nonEmoji = nonEmoji.replace(/[\u200D\uFE0E\uFE0F]/g, "");
    nonEmoji = String(nonEmoji || "").trim();
    if (nonEmoji) {
        return { kind: "mixed_text_and_icon", text: trimmed, text_without_emoji: removeEmojiChars(trimmed) };
    }

    // 仅 ICON：检查是否为“单个 ICON”
    // - 使用 grapheme cluster 计数（Intl.Segmenter 可把 ZWJ/国旗等算作 1 个可见字符）
    var clusterCount = countGraphemeClusters(noSpace);
    if (clusterCount !== 1) {
        return { kind: "multi_icon_only", text: trimmed, icon_count: clusterCount };
    }
    return { kind: "single_icon_only", text: trimmed };
}

