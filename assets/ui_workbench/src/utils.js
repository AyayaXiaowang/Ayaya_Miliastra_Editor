// Small browser-side helpers (no Node.js APIs).

export function waitForNextFrame() {
    return new Promise(function (resolve) {
        requestAnimationFrame(function () {
            resolve();
        });
    });
}

export function copyTextToClipboard(text) {
    var s = String(text || "");
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
        return navigator.clipboard.writeText(s);
    }

    // Fallback (older browsers): temporary textarea + execCommand
    var textarea = document.createElement("textarea");
    textarea.value = s;
    textarea.setAttribute("readonly", "readonly");
    textarea.style.position = "fixed";
    textarea.style.left = "-9999px";
    textarea.style.top = "0";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    document.body.removeChild(textarea);
    return Promise.resolve();
}

export function getBasenameFromPath(pathText) {
    var s = String(pathText || "").trim();
    if (!s) {
        return "";
    }
    // Support both Windows "\" and URL "/" separators.
    var parts = s.split(/[/\\]+/g);
    return String(parts && parts.length > 0 ? parts[parts.length - 1] : s).trim();
}

var _SUCCESS_BEEP_AUDIO_CTX = null;

export function ensureSuccessBeepAudioUnlocked() {
    // Best-effort unlock: must be called from a user gesture (click) to reliably resume audio.
    if (_SUCCESS_BEEP_AUDIO_CTX) {
        if (_SUCCESS_BEEP_AUDIO_CTX.state === "suspended" && typeof _SUCCESS_BEEP_AUDIO_CTX.resume === "function") {
            _SUCCESS_BEEP_AUDIO_CTX.resume();
        }
        return _SUCCESS_BEEP_AUDIO_CTX;
    }
    var AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) {
        return null;
    }
    _SUCCESS_BEEP_AUDIO_CTX = new AudioCtx();
    if (_SUCCESS_BEEP_AUDIO_CTX.state === "suspended" && typeof _SUCCESS_BEEP_AUDIO_CTX.resume === "function") {
        _SUCCESS_BEEP_AUDIO_CTX.resume();
    }
    return _SUCCESS_BEEP_AUDIO_CTX;
}

export function playSuccessBeep() {
    var ctx = ensureSuccessBeepAudioUnlocked();
    if (!ctx) {
        return;
    }

    var now = ctx.currentTime || 0;
    var osc = ctx.createOscillator();
    var gain = ctx.createGain();

    osc.type = "sine";
    osc.frequency.value = 880;

    // Keep volume low; this is a tool notification.
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.03, now + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.14);

    osc.connect(gain);
    gain.connect(ctx.destination);

    osc.start(now);
    osc.stop(now + 0.15);
}

export function escapeHtmlText(text) {
    var s = String(text || "");
    return s
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

export function splitCssByTopLevelCommas(valueText) {
    // Split by commas, but ignore commas inside parentheses.
    var s = String(valueText || "");
    if (!s) {
        return [];
    }

    var parts = [];
    var buf = "";
    var depth = 0;
    for (var i = 0; i < s.length; i++) {
        var ch = s[i];
        if (ch === "(") depth += 1;
        if (ch === ")") depth = Math.max(0, depth - 1);

        if (ch === "," && depth === 0) {
            parts.push(buf.trim());
            buf = "";
            continue;
        }
        buf += ch;
    }
    if (buf.trim()) {
        parts.push(buf.trim());
    }
    return parts;
}

// Fast, deterministic hash for cache keys (no crypto APIs required).
// FNV-1a 32-bit, returned as 8-char lowercase hex.
export function hashTextFNV1a32Hex(text) {
    var s = String(text || "");
    // 32-bit FNV-1a
    var hash = 0x811c9dc5; // 2166136261
    for (var i = 0; i < s.length; i++) {
        hash ^= s.charCodeAt(i);
        // hash *= 16777619 (but keep 32-bit overflow behavior)
        hash = (hash + ((hash << 1) + (hash << 4) + (hash << 7) + (hash << 8) + (hash << 24))) >>> 0;
    }
    var hex = (hash >>> 0).toString(16);
    return ("00000000" + hex).slice(-8);
}

