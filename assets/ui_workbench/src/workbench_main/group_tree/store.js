export function createFlattenGroupTreeStore() {
  return {
    // selection (tree)
    selectedLayerKey: "",
    selectedGroupKey: "",

    // stable prefix for component keys (must match export/writeback)
    uiKeyPrefix: "",

    // visibility/exclude toggles (true source: layerKey)
    hiddenLayerKeySet: new Set(), // layerKey -> hidden
    excludedLayerKeySet: new Set(), // layerKey -> excluded-from-export
    excludedGroupKeySet: new Set(), // groupKey -> excluded-from-export

    // derived maps from last render
    groupKeyByLayerKey: new Map(), // layerKey -> groupKey
    layerEntriesByGroupKey: new Map(), // groupKey -> Array<{ layerKey, rect }>
    groupDisplayNameByKey: new Map(), // groupKey -> displayName

    // expanded/collapsed state
    expandedGroupKeySet: new Set(), // groupKey -> expanded (open)
    expandedUngrouped: true,

    // filter
    treeFilterText: "",

    // last render inputs
    lastLayerList: null,
    lastCanvasSizeKey: "",
  };
}

