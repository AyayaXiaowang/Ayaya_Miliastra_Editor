export { extractDisplayElementsData } from "./flatten/dom_extract.js";
export { generateFlattenedDivs } from "./flatten/flatten_divs.js";
export { buildFlattenedLayerData } from "./flatten/layer_data.js";
export {
    buildFlattenedInjectionHtml,
    normalizeSizeKeyForCssClass,
    rewriteResourcePathsForFlattenedOutput,
    rewritePageSwitchLinksForFlattenedOutput,
    injectContentIntoBody,
    replaceBodyInnerHtml
} from "./flatten/output.js";
