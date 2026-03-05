function clampByte(value) {
    var numberValue = Number(value);
    if (!isFinite(numberValue)) {
        return 0;
    }
    if (numberValue <= 0) {
        return 0;
    }
    if (numberValue >= 255) {
        return 255;
    }
    return Math.round(numberValue);
}

function toTwoDigitHex(byteValue) {
    var hex = clampByte(byteValue).toString(16);
    return hex.length === 1 ? "0" + hex : hex;
}

function parseHexColorText(colorText) {
    var trimmed = String(colorText || "").trim();
    if (!trimmed) {
        return null;
    }
    var match = /^#([a-fA-F0-9]{3,8})$/.exec(trimmed);
    if (!match) {
        return null;
    }
    var hex = match[1];
    if (hex.length === 3) {
        return {
            r: parseInt(hex[0] + hex[0], 16),
            g: parseInt(hex[1] + hex[1], 16),
            b: parseInt(hex[2] + hex[2], 16),
            a: 255,
        };
    }
    if (hex.length === 4) {
        return {
            r: parseInt(hex[0] + hex[0], 16),
            g: parseInt(hex[1] + hex[1], 16),
            b: parseInt(hex[2] + hex[2], 16),
            a: parseInt(hex[3] + hex[3], 16),
        };
    }
    if (hex.length === 6) {
        return {
            r: parseInt(hex.slice(0, 2), 16),
            g: parseInt(hex.slice(2, 4), 16),
            b: parseInt(hex.slice(4, 6), 16),
            a: 255,
        };
    }
    if (hex.length === 8) {
        return {
            r: parseInt(hex.slice(0, 2), 16),
            g: parseInt(hex.slice(2, 4), 16),
            b: parseInt(hex.slice(4, 6), 16),
            a: parseInt(hex.slice(6, 8), 16),
        };
    }
    return null;
}

function parseRgbChannelText(channelText) {
    var trimmed = String(channelText || "").trim();
    if (!trimmed) {
        return null;
    }
    if (trimmed.endsWith("%")) {
        var percentValue = Number.parseFloat(trimmed.slice(0, -1));
        if (!isFinite(percentValue)) {
            return null;
        }
        return clampByte(Math.max(0, Math.min(100, percentValue)) * 2.55);
    }
    var numberValue = Number.parseFloat(trimmed);
    if (!isFinite(numberValue)) {
        return null;
    }
    return clampByte(numberValue);
}

function parseAlphaChannelText(alphaText) {
    var trimmed = String(alphaText || "").trim();
    if (!trimmed) {
        return null;
    }
    if (trimmed.endsWith("%")) {
        var percentValue = Number.parseFloat(trimmed.slice(0, -1));
        if (!isFinite(percentValue)) {
            return null;
        }
        return clampByte(Math.max(0, Math.min(100, percentValue)) * 2.55);
    }
    var numberValue = Number.parseFloat(trimmed);
    if (!isFinite(numberValue)) {
        return null;
    }
    if (numberValue >= 0 && numberValue <= 1) {
        return clampByte(numberValue * 255);
    }
    return clampByte(numberValue);
}

function parseRgbColorText(colorText) {
    var trimmed = String(colorText || "").trim();
    if (!trimmed) {
        return null;
    }
    var match = /^rgba?\(([^)]+)\)$/i.exec(trimmed);
    if (!match) {
        return null;
    }
    var tokenPattern = /[+-]?\d*\.?\d+%?/g;
    var tokens = String(match[1] || "").match(tokenPattern) || [];
    if (tokens.length < 3) {
        return null;
    }
    var r = parseRgbChannelText(tokens[0]);
    var g = parseRgbChannelText(tokens[1]);
    var b = parseRgbChannelText(tokens[2]);
    if (r === null || g === null || b === null) {
        return null;
    }
    var a = 255;
    if (tokens.length >= 4) {
        var alphaByte = parseAlphaChannelText(tokens[3]);
        if (alphaByte === null) {
            return null;
        }
        a = alphaByte;
    }
    return { r: r, g: g, b: b, a: a };
}

export function formatColorTextAsHex(colorText) {
    var trimmed = String(colorText || "").trim();
    if (!trimmed) {
        return "";
    }
    if (trimmed.toLowerCase() === "transparent") {
        return "#00000000";
    }

    var parsed = parseHexColorText(trimmed) || parseRgbColorText(trimmed);
    if (!parsed) {
        return trimmed;
    }
    var hexText = "#" + toTwoDigitHex(parsed.r) + toTwoDigitHex(parsed.g) + toTwoDigitHex(parsed.b);
    if (parsed.a !== 255) {
        hexText += toTwoDigitHex(parsed.a);
    }
    return hexText;
}

