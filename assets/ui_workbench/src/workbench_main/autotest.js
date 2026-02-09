export function parseWorkbenchQueryParams() {
    var searchText = window.location && window.location.search ? String(window.location.search) : "";
    if (!searchText) {
        return new URLSearchParams("");
    }
    return new URLSearchParams(searchText);
}

export async function runAutoTestIfRequested(opts) {
    var o = opts || {};
    var inputHtmlTextAreaElement = o.inputHtmlTextAreaElement;
    var preview = o.preview;
    var handleValidateAndRender = o.handleValidateAndRender;
    var handleGenerateFlattened = o.handleGenerateFlattened;
    var switchToFlattened = o.switchToFlattened;
    var waitForNextFrame = o.waitForNextFrame;

    var params = parseWorkbenchQueryParams();
    var autoTestName = String(params.get("autotest") || "").trim();
    if (!autoTestName) {
        return;
    }
    if (!inputHtmlTextAreaElement) {
        return;
    }

    var samplePath = "";
    if (autoTestName === "p5_style") {
        samplePath = "../ui_mockups/p5_style_mockup.html";
    } else {
        samplePath = String(params.get("autofile") || "").trim();
    }
    if (!samplePath) {
        console.log("[AUTOTEST] unknown autotest:", autoTestName);
        return;
    }

    var enableShadowInspect = String(params.get("shadowInspect") || "").trim() !== "0";
    console.log("[AUTOTEST] loading:", samplePath);

    var response = await fetch(samplePath);
    var htmlText = await response.text();
    inputHtmlTextAreaElement.value = htmlText;
    console.log("[AUTOTEST] loaded html length:", htmlText.length);

    await handleValidateAndRender();
    await handleGenerateFlattened();
    await switchToFlattened();
    preview.setShadowInspectModeEnabled(enableShadowInspect);

    await waitForNextFrame();
    await waitForNextFrame();

    var previewDocument = preview.getPreviewDocument();
    if (!previewDocument) {
        console.log("[AUTOTEST] no previewDocument after flattened render");
        return;
    }
    var flatAreas = previewDocument.querySelectorAll(".flat-display-area");
    var flatElements = previewDocument.querySelectorAll(".flat-display-area .flat-element");
    var flatShadows = previewDocument.querySelectorAll(".flat-display-area .flat-shadow");
    var flatTexts = previewDocument.querySelectorAll(".flat-display-area .flat-text");
    console.log("[AUTOTEST] flat areas:", flatAreas.length, "flat elements:", flatElements.length, "flat shadows:", flatShadows.length);
    if (flatShadows.length > 0) {
        var sampleCount = Math.min(3, flatShadows.length);
        for (var index = 0; index < sampleCount; index++) {
            console.log("[AUTOTEST] shadow[" + index + "]", flatShadows[index].getAttribute("style") || "");
        }
    }
    if (flatTexts.length > 0 && previewDocument.defaultView) {
        var textStyle = previewDocument.defaultView.getComputedStyle(flatTexts[0]);
        console.log("[AUTOTEST] text sample z-index:", textStyle ? textStyle.zIndex : "");
        console.log("[AUTOTEST] text sample color:", textStyle ? textStyle.color : "", "hex:", preview.formatColorTextAsHex(textStyle ? textStyle.color : ""));
    }
}

