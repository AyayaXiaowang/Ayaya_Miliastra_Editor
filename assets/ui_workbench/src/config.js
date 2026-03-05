// Workbench shared config (browser-side ES Modules).

export var CANVAS_SIZE_CATALOG = [
    { key: "1920x1080", label: "1920 x 1080", width: 1920, height: 1080, contentPadding: 120 },
    { key: "1600x900", label: "1600 x 900", width: 1600, height: 900, contentPadding: 100 },
    { key: "1560x720", label: "1560 x 720", width: 1560, height: 720, contentPadding: 80 },
    { key: "1280x720", label: "1280 x 720", width: 1280, height: 720, contentPadding: 80 },
];

export var FORBIDDEN_CSS_TOKENS = [
    ":hover",
    ":active",
    ":focus",
    ":focus-visible",
    "transition:",
    "animation:",
    "@keyframes",
    "background-image:",
    "linear-gradient(",
    "radial-gradient(",
    "conic-gradient(",
    "url(",
    "text-shadow:",
    "opacity:",
    "skew(",
    "rotate(",
];

export var FORBIDDEN_JS_TOKENS = [
    "setTimeout(",
    "setInterval(",
    "requestAnimationFrame(",
];

export var ALLOWED_BUTTON_ICON_CHARS = "⚒⬆⬇⚙★☆◆◇▶◀▲▼■□●○<>";

// -----------------------------------------------------------------------------
// 游戏区域（挖空 / Cutout）
// -----------------------------------------------------------------------------
export var GAME_CUTOUT_CLASS = "game-cutout";
export var GAME_CUTOUT_NAME_ATTR = "data-game-area";

// -----------------------------------------------------------------------------
// 高亮展示区域（Dim Surroundings）
// -----------------------------------------------------------------------------
// 语义：该元素本身不会出现在扁平化输出中；扁平化会自动生成 4 个“压暗遮罩矩形”
//（上/下/左/右）包围该矩形区域，从而实现“周围变暗、区域高亮”的效果。
//
// 用法：
//   <div class="highlight-display-area" data-highlight-overlay-alpha="0.45"></div>
//
// - alpha 仅允许 0.45 或 0.25（不填默认 0.45）。
export var HIGHLIGHT_DISPLAY_AREA_CLASS = "highlight-display-area";
export var HIGHLIGHT_OVERLAY_ALPHA_ATTR = "data-highlight-overlay-alpha";

export var DIVIDER_CLASSES = [
    "left-controls-divider",
    "stat-divider",
];

export var MULTILINE_TEXT_CLASSES = [
    "blueprint-text",
    "enhance-row-text",
    "enhance-row-meta",
    "reward-info",
];

export var IGNORED_TEXT_CLASSES = [
    "debug-target",
    "green",
    "gold",
    "teal",
    "active",
];

export var CONTAINER_DESCENDANT_SINGLE_LINE_TAGS = {
    "comp-details": ["h3", "span"],
};

export var PREVIEW_VARIANT_SOURCE = "source";
export var PREVIEW_VARIANT_FLATTENED = "flattened";
export var EMPTY_INPUT_PLACEHOLDER_MARKER = "ui-html-workbench-empty-placeholder";

// -----------------------------------------------------------------------------
// 颜色规范（Web-first）
// -----------------------------------------------------------------------------
export var PALETTE_SHADE_OVERLAY_RGBA = "rgba(14, 14, 14, 0.45)";
export var PALETTE_SHADE_OVERLAY_HEX = "#0e0e0e73";
export var PALETTE_SHADE_OVERLAY_RGBA_25 = "rgba(14, 14, 14, 0.25)";
export var PALETTE_SHADE_OVERLAY_HEX_25 = "#0e0e0e40";
export var PALETTE_DARK_HEX = "#0e0e0e";

// 基础色（Base）
export var PALETTE_BASE_HEX_COLORS = [
    "#92cd21", // green
    "#e2dbce", // white (warm)
    "#f3c330", // yellow
    "#36f3f3", // cyan-blue
    "#f47b7b", // red
];

// 结果色（Result）= Base + 45% shade overlay 的近似压暗版本（允许在 HTML 中直接使用，但导出会转回 Base+overlay）
export var PALETTE_DARK2_VARIANT_TO_BASE_HEX = {
    "#577718": "#92cd21",
    "#837f78": "#e2dbce",
    "#8c7221": "#f3c330",
    "#248c8c": "#36f3f3",
    "#8d4a4a": "#f47b7b",
};

// 压暗 1 级（Dark1）= Base + 25% shade overlay 的近似压暗版本（允许在 HTML 中直接使用，但导出会转回 Base+overlay）
export var PALETTE_DARK1_VARIANT_TO_BASE_HEX = {
    "#719d1c": "#92cd21",
    "#ada89e": "#e2dbce",
    "#ba9628": "#f3c330",
    "#2cbaba": "#36f3f3",
    "#ba6060": "#f47b7b",
};

// 压暗 3 级（Dark3）= Base 叠加两层 45% shade overlay 的近似版本（允许在 HTML 中直接使用）。
// 说明：Dark2（压暗 2 级）已经是叠加 1 层；Dark3 是从 Base 推算再叠加第 2 层（即对 Dark2 再叠一次同样的盖色）。
// 导出/写回阶段会把该色归一化为 Base + 两层盖色阴影（保证表现一致）。
export var PALETTE_DARK3_VARIANT_TO_BASE_HEX = {
    "#364814": "#92cd21", // green + 2x shade overlay
    "#4e4c48": "#e2dbce", // white + 2x shade overlay
    "#534518": "#f3c330", // yellow + 2x shade overlay
    "#1a5353": "#36f3f3", // cyan-blue + 2x shade overlay
    "#542f2f": "#f47b7b", // red + 2x shade overlay
};

// Backward compat: historical name == Dark2 (one-layer 45% shade overlay)
export var PALETTE_DARK_VARIANT_TO_BASE_HEX = PALETTE_DARK2_VARIANT_TO_BASE_HEX;

export var PALETTE_ALLOWED_HEX_COLORS = PALETTE_BASE_HEX_COLORS
    .concat(Object.keys(PALETTE_DARK_VARIANT_TO_BASE_HEX))
    .concat(Object.keys(PALETTE_DARK1_VARIANT_TO_BASE_HEX))
    .concat(Object.keys(PALETTE_DARK2_VARIANT_TO_BASE_HEX))
    .concat(Object.keys(PALETTE_DARK3_VARIANT_TO_BASE_HEX))
    .concat([PALETTE_SHADE_OVERLAY_HEX, PALETTE_SHADE_OVERLAY_HEX_25]);

export function getCanvasSizeByKey(canvasSizeKey) {
    var key = String(canvasSizeKey || "").trim();
    for (var index = 0; index < CANVAS_SIZE_CATALOG.length; index++) {
        var canvasSizeOption = CANVAS_SIZE_CATALOG[index];
        if (canvasSizeOption && canvasSizeOption.key === key) {
            return canvasSizeOption;
        }
    }

    // 默认回退到 1600x900（Workbench 默认按钮）
    for (var fallbackIndex = 0; fallbackIndex < CANVAS_SIZE_CATALOG.length; fallbackIndex++) {
        var fallbackOption = CANVAS_SIZE_CATALOG[fallbackIndex];
        if (fallbackOption && fallbackOption.key === "1600x900") {
            return fallbackOption;
        }
    }
    return CANVAS_SIZE_CATALOG[0];
}

