// 复制粘贴逻辑
function copy() {
    const active = canvas.getActiveObject();
    if (active) {
        active.clone(function(cloned) {
            clipboard = cloned;
        });
    }
}

function paste() {
    if (!clipboard) return;
    clipboard.clone(function(clonedObj) {
        canvas.discardActiveObject();
        clonedObj.set({
            left: clonedObj.left + 20,
            top: clonedObj.top + 20,
            evented: true
        });
        if (clonedObj.type === 'activeSelection') {
            // activeSelection 需要特殊处理
            clonedObj.canvas = canvas;
            clonedObj.forEachObject(function(obj) {
                assignFreshObjectIdsDeep(obj);
                canvas.add(obj);
            });
            clonedObj.setCoords();
        } else {
            assignFreshObjectIdsDeep(clonedObj);
            canvas.add(clonedObj);
        }
        canvas.setActiveObject(clonedObj);
        canvas.requestRenderAll();
        saveToLocal();
        saveHistory();
    });
}

function _cloneAndActivateForAltDrag(root, onDone) {
    if (!root) return;
    root.clone(function(clonedObj) {
        canvas.discardActiveObject();

        if (clonedObj.type === 'activeSelection') {
            // activeSelection 不会直接 add 到 canvas，需要把对象逐个加入，再重建 selection
            clonedObj.canvas = canvas;
            const objs = [];
            clonedObj.forEachObject(function(obj) {
                assignFreshObjectIdsDeep(obj);
                canvas.add(obj);
                objs.push(obj);
            });
            const sel = new fabric.ActiveSelection(objs, { canvas });
            sel.lockSkewingX = true;
            sel.lockSkewingY = true;
            canvas.setActiveObject(sel);
            sel.setCoords();
            canvas.requestRenderAll();
            updatePropPanel();
            updateLayerListUI();
            if (onDone) onDone(sel);
            return;
        }

        assignFreshObjectIdsDeep(clonedObj);
        canvas.add(clonedObj);
        canvas.setActiveObject(clonedObj);
        clonedObj.setCoords();
        canvas.requestRenderAll();
        updatePropPanel();
        updateLayerListUI();
        if (onDone) onDone(clonedObj);
    });
}

function setupAltDuplicateDrag() {
    const upperCanvas = canvas.upperCanvasEl;
    if (!upperCanvas) return;

    // 捕获阶段：先复制出新对象，再让 Fabric 正常进入“拖拽移动”分支（对多选/组同理）
    upperCanvas.addEventListener('mousedown', (e) => {
        if (_altDuplicateDispatching) return;
        if (!e) return;
        if (e.button !== 0) return; // 仅左键
        if (!e.altKey) return;

        const active = canvas.getActiveObject();
        const target = canvas.findTarget(e);
        if (!target) return;

        let root = null;
        // ALT+拖拽：若当前为多选，且点击的是多选成员，则复制整组选择
        if (active && active.type === 'activeSelection' && (target === active || (active.contains && active.contains(target)))) {
            root = active;
        } else if (active && active.type === 'group' && (target === active || (active.getObjects && active.getObjects().includes(target)))) {
            root = active;
        } else {
            root = target;
        }

        if (!root) return;
        if (root.isLocked === true) return;

        // 阻止 Fabric 收到这次 mousedown（否则会先拖动原对象）
        e.preventDefault();
        e.stopImmediatePropagation();
        e.stopPropagation();

        const clientX = e.clientX;
        const clientY = e.clientY;

        _altDuplicateDispatching = true;
        _cloneAndActivateForAltDrag(root, () => {
            saveToLocal();
            saveHistory();

            // 合成一次“普通左键 mousedown”，交还给 Fabric 进入拖拽流程
            const ev2 = new MouseEvent('mousedown', {
                bubbles: true,
                cancelable: true,
                clientX,
                clientY,
                button: 0,
                buttons: 1,
                altKey: false,
                ctrlKey: false,
                metaKey: false,
                shiftKey: e.shiftKey === true
            });
            upperCanvas.dispatchEvent(ev2);
            _altDuplicateDispatching = false;
        });
    }, true);
}

