import { escapeHtmlText } from "../utils.js";

export function buildFlattenedInjectionHtml(flatAreaList) {
    var flatAreaHtmlList = [];
    for (var index = 0; index < flatAreaList.length; index++) {
        var item = flatAreaList[index];
        var displayText = item.isDefault ? "block" : "none";
        var sizeKeyText = item.sizeKey ? String(item.sizeKey || "") : "";
        flatAreaHtmlList.push(
            "\n    <!-- 扁平化展示区域 - " + escapeHtmlText(item.label) + " -->\n" +
            '    <div id="flat-display-area-' + item.safeKey + '" class="flat-display-area" data-size="' + escapeHtmlText(item.label) + '" data-size-key="' + escapeHtmlText(sizeKeyText) + '" style="position: absolute; left: 0; top: 0; width: ' + item.width + 'px; height: ' + item.height + 'px; overflow: hidden; display: ' + displayText + ';">\n' +
            "            " + item.divs + "\n" +
            "    </div>"
        );
    }
    var flatDisplayHtml = flatAreaHtmlList.join("\n");

    var injectedCss = [
        "<style>",
        "/* injected by ui_html_workbench: flattened output */",
        "html, body {",
        "  /* 关键：原页面可能对 html/body 设置 padding/flex/transform，扁平层必须强制回到“画布原点坐标系” */",
        "  margin: 0 !important;",
        "  padding: 0 !important;",
        "  overflow: hidden !important;",
        "  width: 100% !important;",
        "  height: 100% !important;",
        "  transform: none !important;",
        "}",
        "body {",
        "  /* 关键：让扁平化展示层脱离原页面 flex/flow，固定锚定在画布原点，避免 padding/flex 导致坐标二次偏移 */",
        "  position: relative !important;",
        "  display: block !important;",
        "  transform: none !important;",
        "}",
        ".flat-display-area {",
        "  background: transparent;",
        "  position: absolute;",
        "  left: 0;",
        "  top: 0;",
        "  /* 建立独立 stacking context，确保外部 fixed 工具条（通常 z-index 很高）不会被扁平层遮住 */",
        "  z-index: 1;",
        "}",
        "/* 兼容：若扁平化输出采用“注入而非替换 body”，则必须隐藏原始内容，避免叠在扁平层上。 */",
        "body > *:not(.flat-display-area):not(.canvas-toolbar):not(.page-switch-toolbar) {",
        "  display: none !important;",
        "}",
        ".flat-shadow, .flat-border, .flat-element, .flat-text {",
        "  position: absolute;",
        "}",
        "/* 交互语义：默认只允许点选文字层（避免矩形底色/阴影盖住文字导致“点不到文字”）。 */",
        ".flat-shadow, .flat-border, .flat-element {",
        "  pointer-events: none;",
        "}",
        ".flat-text, .flat-text * {",
        "  pointer-events: auto;",
        "}",
        "/* 多状态控件：默认只展示 default=1；其它态保持“有盒子但不可见”。",
        "   说明：",
        "   - 扁平化输出会替换/隐藏原始 DOM，因此源码侧的 `visibility:hidden` 规则不会再生效；",
        "   - 这里用 data-ui-state-*（由 dom_extract/flatten_divs 透传）恢复“初始态显隐”；",
        "   - 禁止用 display:none（会丢失几何盒子，影响导出/定位）。 */",
        ".flat-shadow[data-ui-state-group]:not([data-ui-state-default=\"1\"]),",
        ".flat-border[data-ui-state-group]:not([data-ui-state-default=\"1\"]),",
        ".flat-element[data-ui-state-group]:not([data-ui-state-default=\"1\"]),",
        ".flat-text[data-ui-state-group]:not([data-ui-state-default=\"1\"]) {",
        "  visibility: hidden;",
        "}",
        ".flat-debug-box {",
        "  position: absolute;",
        "  pointer-events: none;",
        "  border: 2px dashed rgba(255,255,255,0.55);",
        "  box-sizing: border-box;",
        "}",
        ".flat-debug-group-box {",
        "  position: absolute;",
        "  pointer-events: none;",
        "  outline: 3px solid rgba(255,255,255,0.75);",
        "  outline-offset: -2px;",
        "  box-sizing: border-box;",
        "}",
        ".flat-debug-label {",
        "  position: absolute;",
        "  left: 0;",
        "  top: 0;",
        "  max-width: 100%;",
        "  padding: 1px 4px;",
        "  font: 11px/1.3 Consolas, 'JetBrains Mono', monospace;",
        "  color: #111;",
        "  background: rgba(255,255,255,0.85);",
        "  white-space: nowrap;",
        "  overflow: hidden;",
        "  text-overflow: ellipsis;",
        "}",
        ".flat-debug-group-label {",
        "  top: -16px;",
        "}",
        "</style>",
    ].join("\n");

    // 重要：Workbench 预览 iframe 默认 sandbox 不允许执行脚本（无 allow-scripts）。
    // 因此扁平化输出禁止注入任何 <script>（否则浏览器控制台会持续报错并干扰调试）。
    return injectedCss + "\n" + flatDisplayHtml;
}

export function normalizeSizeKeyForCssClass(canvasSizeLabel) {
    if (!canvasSizeLabel) {
        return "default";
    }
    return String(canvasSizeLabel).replace(/\s+/g, "-").replace(/x/gi, "-");
}

function shouldRewriteUrl(urlValue) {
    var trimmed = String(urlValue || "").trim();
    if (!trimmed) {
        return false;
    }
    if (trimmed.startsWith("#")) {
        return false;
    }
    if (trimmed.startsWith("data:")) {
        return false;
    }
    if (trimmed.startsWith("javascript:")) {
        return false;
    }
    if (trimmed.startsWith("//")) {
        return false;
    }
    if (trimmed.startsWith("/")) {
        return false;
    }
    if (/^[a-zA-Z][a-zA-Z0-9+\-.]*:/.test(trimmed)) {
        return false;
    }
    return true;
}

export function rewriteResourcePathsForFlattenedOutput(htmlText) {
    var relativePrefix = "../";
    var scriptSrcDoublePattern = /(<script[^>]*\bsrc\s*=\s*")([^"]+)(")/gi;
    var scriptSrcSinglePattern = /(<script[^>]*\bsrc\s*=\s*')([^']+)(')/gi;
    var linkHrefDoublePattern = /(<link[^>]*\bhref\s*=\s*")([^"]+)(")/gi;
    var linkHrefSinglePattern = /(<link[^>]*\bhref\s*=\s*')([^']+)(')/gi;

    function buildNewUrl(originalUrl) {
        var normalizedUrl = String(originalUrl || "");
        if (normalizedUrl.startsWith("../")) {
            return normalizedUrl;
        }
        if (normalizedUrl.startsWith("./")) {
            normalizedUrl = normalizedUrl.slice(2);
        }
        return relativePrefix + normalizedUrl;
    }

    function rewriteMatch(matchText, prefix, urlValue, suffix) {
        if (!shouldRewriteUrl(urlValue)) {
            return matchText;
        }
        var newUrlValue = buildNewUrl(urlValue);
        return prefix + newUrlValue + suffix;
    }

    var updatedHtmlText = htmlText.replace(scriptSrcDoublePattern, function (matchText, prefix, urlValue, suffix) {
        return rewriteMatch(matchText, prefix, urlValue, suffix);
    });
    updatedHtmlText = updatedHtmlText.replace(scriptSrcSinglePattern, function (matchText, prefix, urlValue, suffix) {
        return rewriteMatch(matchText, prefix, urlValue, suffix);
    });
    updatedHtmlText = updatedHtmlText.replace(linkHrefDoublePattern, function (matchText, prefix, urlValue, suffix) {
        return rewriteMatch(matchText, prefix, urlValue, suffix);
    });
    updatedHtmlText = updatedHtmlText.replace(linkHrefSinglePattern, function (matchText, prefix, urlValue, suffix) {
        return rewriteMatch(matchText, prefix, urlValue, suffix);
    });

    return updatedHtmlText;
}

export function rewritePageSwitchLinksForFlattenedOutput(htmlText) {
    // 预览 iframe 默认禁用脚本（sandbox 无 allow-scripts），不能依赖注入脚本动态重写链接；
    // 因此这里在生成扁平化输出时，直接把“页面切换按钮”的 href 重写为 *_flattened.html。
    var raw = String(htmlText || "");
    if (!raw) {
        return raw;
    }
    // 仅处理 class 含 page-switch-btn 且 href 为相对 .html 的链接
    var pattern = /(<a\b[^>]*\bclass\s*=\s*["'][^"']*\bpage-switch-btn\b[^"']*["'][^>]*\bhref\s*=\s*["'])([^"']+)(["'][^>]*>)/gi;

    function shouldRewriteHref(hrefValue) {
        var trimmed = String(hrefValue || "").trim();
        if (!trimmed) {
            return false;
        }
        if (trimmed.indexOf("://") !== -1) {
            return false;
        }
        if (trimmed.charAt(0) === "#") {
            return false;
        }
        if (trimmed.startsWith("data:")) {
            return false;
        }
        if (trimmed.startsWith("javascript:")) {
            return false;
        }
        if (trimmed.startsWith("//")) {
            return false;
        }
        if (trimmed.startsWith("/")) {
            return false;
        }
        if (!/\.html($|[?#])/.test(trimmed)) {
            return false;
        }
        return true;
    }

    function rewriteOne(hrefValue) {
        var href = String(hrefValue || "");
        if (!shouldRewriteHref(href)) {
            return href;
        }
        var hrefWithoutHash = href.split("#")[0];
        var hashPart = href.substring(hrefWithoutHash.length);
        var hrefWithoutQuery = hrefWithoutHash.split("?")[0];
        var queryPart = hrefWithoutHash.substring(hrefWithoutQuery.length);
        if (hrefWithoutQuery.indexOf("_flattened.html") !== -1) {
            return href;
        }
        var flattenedFileName = hrefWithoutQuery.replace(/\.html$/, "_flattened.html");
        return flattenedFileName + queryPart + hashPart;
    }

    return raw.replace(pattern, function (_m, prefix, hrefValue, suffix) {
        return prefix + rewriteOne(hrefValue) + suffix;
    });
}

export function injectContentIntoBody(htmlText, injectedContentHtml) {
    var bodyMatch = /<body[^>]*>/i.exec(htmlText);
    if (!bodyMatch) {
        return null;
    }
    var bodyStartIndex = bodyMatch.index + bodyMatch[0].length;
    return htmlText.slice(0, bodyStartIndex) + "\n" + injectedContentHtml + "\n" + htmlText.slice(bodyStartIndex);
}

export function replaceBodyInnerHtml(htmlText, newBodyInnerHtml) {
    var raw = String(htmlText || "");
    var injected = String(newBodyInnerHtml || "");
    if (!raw) {
        return null;
    }

    var bodyOpenMatch = /<body\b[^>]*>/i.exec(raw);
    if (!bodyOpenMatch) {
        return null;
    }
    var bodyInnerStartIndex = bodyOpenMatch.index + bodyOpenMatch[0].length;

    // 取第一个 </body> 作为闭合点（预览侧已剔除 <script> 与 meta refresh，避免误命中文本中的 </body>）
    var afterOpen = raw.slice(bodyInnerStartIndex);
    var bodyCloseMatch = /<\/body\s*>/i.exec(afterOpen);
    if (!bodyCloseMatch) {
        return null;
    }
    var bodyInnerEndIndex = bodyInnerStartIndex + bodyCloseMatch.index;

    return raw.slice(0, bodyInnerStartIndex) + "\n" + injected + "\n" + raw.slice(bodyInnerEndIndex);
}

