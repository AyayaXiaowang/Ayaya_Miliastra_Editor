export function createPreviewVariantSwitcher(opts) {
    var o = opts || {};

    var PREVIEW_VARIANT_SOURCE = o.PREVIEW_VARIANT_SOURCE;
    var PREVIEW_VARIANT_FLATTENED = o.PREVIEW_VARIANT_FLATTENED;
    var preview = o.preview;

    var getSourceHtmlText = o.getSourceHtmlText;
    var getSourceHash = o.getSourceHash;
    var getLastGeneratedFlattenedHtmlText = o.getLastGeneratedFlattenedHtmlText;
    var getLastFlattenedSourceHash = o.getLastFlattenedSourceHash;
    var getLastFlattenedErrorText = o.getLastFlattenedErrorText;
    var onFlattenCacheMiss = o.onFlattenCacheMiss;

    var onFlattenedRendered = o.onFlattenedRendered;
    var reportFlattenedError = o.reportFlattenedError;

    var _currentPreviewVariant = PREVIEW_VARIANT_SOURCE;

    // 预览变体切换需要串行化：
    // - 若用户快速“源码/扁平”来回点击，会产生并发渲染，导致状态错乱、甚至出现 iframe 导航到 404 的假象。
    var _previewVariantSwitchInProgress = false;
    var _pendingPreviewVariant = "";
    var _previewVariantSwitchCyclePromise = null;
    var _previewVariantSwitchCycleResolve = null;

    async function switchPreviewVariantTo(previewVariant) {
        var normalizedVariant = previewVariant === PREVIEW_VARIANT_FLATTENED ? PREVIEW_VARIANT_FLATTENED : PREVIEW_VARIANT_SOURCE;
        if (normalizedVariant === PREVIEW_VARIANT_SOURCE) {
            // 预览应以“编辑器当前文本”为准，避免因为 normalize/sanitize 导致 cache key 不一致、
            // 或因为后台流程只更新了 textarea 而可视预览仍停留在旧内容，进而触发错误的重算/空白。
            var sourceHtmlText = getSourceHtmlText();
            if (!String(sourceHtmlText || "").trim()) {
                await preview.renderHtmlIntoPreview(preview.buildEmptyInputPlaceholderHtml(), PREVIEW_VARIANT_SOURCE);
                _currentPreviewVariant = PREVIEW_VARIANT_SOURCE;
                return;
            }
            await preview.renderHtmlIntoPreview(sourceHtmlText, PREVIEW_VARIANT_SOURCE);
            _currentPreviewVariant = PREVIEW_VARIANT_SOURCE;
            return;
        }

        var sourceHtmlText = getSourceHtmlText ? String(getSourceHtmlText() || "") : "";
        if (!String(sourceHtmlText || "").trim()) {
            await preview.renderHtmlIntoPreview(preview.buildEmptyInputPlaceholderHtml(), PREVIEW_VARIANT_FLATTENED);
            _currentPreviewVariant = PREVIEW_VARIANT_FLATTENED;
            return;
        }

        // Pure display switch:
        // - If flattened cache is valid, just render it.
        // - If cache is missing/stale, show a clear placeholder (do NOT start heavy flattening here).
        var expectedSourceHash = getSourceHash ? String(getSourceHash() || "") : "";
        var hasFlattenedCache = !!getLastGeneratedFlattenedHtmlText();
        var isFlattenedCacheFresh = getLastFlattenedSourceHash ? (getLastFlattenedSourceHash() === expectedSourceHash) : true;
        if (!hasFlattenedCache || !isFlattenedCacheFresh) {
            var autoStarted = false;
            if (onFlattenCacheMiss) {
                autoStarted = !!(await onFlattenCacheMiss({
                    expectedSourceHash: expectedSourceHash,
                    hasFlattenedCache: hasFlattenedCache,
                    isFlattenedCacheFresh: isFlattenedCacheFresh
                }));
            }
            await preview.renderHtmlIntoPreview(
                preview.buildStatusPlaceholderHtml(
                    autoStarted ? "正在生成扁平化" : "未生成扁平化",
                    autoStarted
                        ? "检测到扁平缓存缺失或已过期，已自动开始生成。\\n可继续操作，完成后会自动刷新预览。"
                        : "当前扁平缓存不存在或已过期。\\n请点击“生成扁平化”，或先“校验并渲染”（通过后会自动预生成缓存）。"
                ),
                PREVIEW_VARIANT_FLATTENED
            );
            _currentPreviewVariant = PREVIEW_VARIANT_FLATTENED;
            return;
        }
        if (getLastFlattenedErrorText()) {
            if (reportFlattenedError) {
                reportFlattenedError(getLastFlattenedErrorText());
            }
            return;
        }
        var htmlText = getLastGeneratedFlattenedHtmlText();
        if (!htmlText) {
            return;
        }
        await preview.renderHtmlIntoPreview(htmlText, PREVIEW_VARIANT_FLATTENED);
        _currentPreviewVariant = PREVIEW_VARIANT_FLATTENED;
        if (onFlattenedRendered) {
            onFlattenedRendered();
        }
    }

    async function requestPreviewVariantSwitch(previewVariant) {
        var normalizedVariant = previewVariant === PREVIEW_VARIANT_FLATTENED ? PREVIEW_VARIANT_FLATTENED : PREVIEW_VARIANT_SOURCE;
        _pendingPreviewVariant = normalizedVariant;
        if (_previewVariantSwitchInProgress) {
            return _previewVariantSwitchCyclePromise || Promise.resolve();
        }
        _previewVariantSwitchInProgress = true;
        _previewVariantSwitchCyclePromise = new Promise(function (resolve) {
            _previewVariantSwitchCycleResolve = resolve;
        });
        while (_pendingPreviewVariant) {
            var nextVariant = _pendingPreviewVariant;
            _pendingPreviewVariant = "";
            await switchPreviewVariantTo(nextVariant);
        }
        _previewVariantSwitchInProgress = false;
        if (_previewVariantSwitchCycleResolve) {
            _previewVariantSwitchCycleResolve();
        }
        _previewVariantSwitchCycleResolve = null;
        _previewVariantSwitchCyclePromise = null;
    }

    function getCurrentPreviewVariant() {
        return _currentPreviewVariant;
    }

    return {
        requestPreviewVariantSwitch: requestPreviewVariantSwitch,
        switchPreviewVariantTo: switchPreviewVariantTo,
        getCurrentPreviewVariant: getCurrentPreviewVariant
    };
}

