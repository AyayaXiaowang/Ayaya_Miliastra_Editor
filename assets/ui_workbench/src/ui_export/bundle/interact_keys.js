import { rectFromWidget } from "./rect_utils.js";

function normalizeInteractKeyCode(raw) {
    if (raw === null || raw === undefined) {
        return 0;
    }
    if (typeof raw === "number") {
        if (!isFinite(raw)) {
            return 0;
        }
        return Math.trunc(raw);
    }
    var text = String(raw || "").trim();
    if (!text) {
        return 0;
    }
    if (!/^[0-9]+$/.test(text)) {
        return 0;
    }
    var n = Math.trunc(Number(text));
    return isFinite(n) ? n : 0;
}

function getAnchorInteractKeyCode(anchorWidget) {
    var s = anchorWidget && anchorWidget.settings ? anchorWidget.settings : null;
    if (!s) {
        return 0;
    }
    var kbm = normalizeInteractKeyCode(s.keybind_kbm_code);
    var pad = normalizeInteractKeyCode(s.keybind_gamepad_code);
    if (kbm > 0 && pad > 0 && kbm !== pad) {
        throw new Error("可交互按钮按键码必须一致（键鼠/手柄必须同号）：[" + String(anchorWidget.widget_name || "") + "] kbm=" + String(kbm) + " pad=" + String(pad));
    }
    return kbm > 0 ? kbm : (pad > 0 ? pad : 0);
}

function setAnchorInteractKeyCode(anchorWidget, code) {
    if (!anchorWidget.settings) {
        anchorWidget.settings = {};
    }
    anchorWidget.settings.keybind_kbm_code = code;
    anchorWidget.settings.keybind_gamepad_code = code;
}

export function ensureUniqueInteractiveKeybindsForPage(anchorList) {
    var MAX = 14;
    var OVERFLOW_CODE = 14;

    var entries = [];
    for (var i = 0; i < anchorList.length; i++) {
        var a = anchorList[i];
        if (!a) {
            continue;
        }
        var r = rectFromWidget(a);
        var code = getAnchorInteractKeyCode(a);
        // 容错策略：
        // - 不再因为“数量 > 14 / code 重复 / code 超范围”阻断导出（CLI 会因 unhandledrejection 中断）。
        // - 超出 1..14 的 code：统一归一化到 OVERFLOW_CODE（默认 14）。
        // - 未指定 code（0）：稍后尽量分配唯一 1..14；若已用尽则同样落到 OVERFLOW_CODE。
        if (code < 1) {
            code = 0;
        } else if (code > MAX) {
            code = OVERFLOW_CODE;
            setAnchorInteractKeyCode(a, OVERFLOW_CODE);
        }
        entries.push({ anchor: a, x: Number(r.x || 0), y: Number(r.y || 0), code: code });
    }
    entries.sort(function (a, b) {
        if (a.y !== b.y) return a.y - b.y;
        return a.x - b.x;
    });

    // used_unique 仅用于“尽量分配唯一键位”，不再强制“同页唯一”。
    var used_unique = new Set();
    for (var j = 0; j < entries.length; j++) {
        var e = entries[j];
        if (!e) continue;
        if (e.code <= 0) continue;
        // 上面已归一化，这里只记录“已占用的唯一键位”，方便后续分配。
        if (e.code >= 1 && e.code <= MAX) {
            if (!used_unique.has(e.code)) {
                used_unique.add(e.code);
            }
        }
    }

    var next = 1;
    for (var k = 0; k < entries.length; k++) {
        var e2 = entries[k];
        if (!e2) continue;
        if (e2.code > 0) continue;
        while (next <= MAX && used_unique.has(next)) {
            next += 1;
        }
        if (next > MAX) {
            setAnchorInteractKeyCode(e2.anchor, OVERFLOW_CODE);
            e2.code = OVERFLOW_CODE;
            continue;
        }
        setAnchorInteractKeyCode(e2.anchor, next);
        used_unique.add(next);
        e2.code = next;
        next += 1;
    }
}

