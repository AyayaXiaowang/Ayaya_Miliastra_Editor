import { PREVIEW_VARIANT_SOURCE } from "../config.js";

export var state = {
    // preview mode
    currentPreviewVariant: PREVIEW_VARIANT_SOURCE,
    isPreviewOnlyModeEnabled: false,
    isShadowInspectModeEnabled: false,
    // preview: whether to display data-ui-text bindings instead of sample text (preview only)
    isDynamicTextPreviewEnabled: false,

    // canvas / scaling
    currentSelectedCanvasSizeKey: "1600x900",
    currentPreviewScale: 1,

    // last rendered HTML (iframe srcdoc)
    lastRenderedHtmlText: "",
    lastRenderedSourceHtmlText: "",

    // iframe document + render sequence
    previewDocument: null,
    previewLoadSequence: 0,

    // compute iframe (hidden): used for validation/flatten/export to avoid flicker on visible preview iframe
    computePreviewDocument: null,
    computePreviewLoadSequence: 0,
    computeLastRenderedHtmlText: "",

    // selection
    previewClickListenerCleanup: null,
    currentSelectedPreviewElement: null,
    currentSelectedPreviewGroup: null, // array of Elements
    isReverseRegionModeEnabled: false,

    // drag selection state
    isMouseDownForSelection: false,
    isDraggingSelection: false,
    selectionJustCompleted: false,
    selectionDragThreshold: 5,
    selectionStartCanvasX: 0,
    selectionStartCanvasY: 0,
    selectionCurrentCanvasX: 0,
    selectionCurrentCanvasY: 0,

    // external subscription
    onSelectionChanged: null,
};


