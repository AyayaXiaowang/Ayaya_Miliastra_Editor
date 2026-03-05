// 快捷键
function setupHotkeys() {
    document.addEventListener('keydown', (e) => {
        // 如果焦点在输入框，不触发快捷键
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

        const key = String(e && e.key ? e.key : '').toLowerCase();
        const isPixelModal = (typeof isPixelWorkbenchVisible === 'function') ? !!isPixelWorkbenchVisible() : false;
        if (isPixelModal) {
            // Pixel workbench is modal: block canvas hotkeys to avoid accidents.
            if (key === 'escape') {
                e.preventDefault();
                if (typeof _pxSetMidView === 'function') {
                    _pxSetMidView('canvas');
                }
                return;
            }

            if ((e.ctrlKey || e.metaKey) && !e.shiftKey && key === 'z') {
                e.preventDefault();
                if (typeof _pxUndoLastPixelEdit === 'function') {
                    _pxUndoLastPixelEdit();
                }
                return;
            }
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && key === 'z') {
                e.preventDefault();
                return;
            }

            if (key === 'delete' || key === 'backspace') {
                e.preventDefault();
                return;
            }

            if ((e.ctrlKey || e.metaKey) && (key === 'c' || key === 'v')) {
                e.preventDefault();
                return;
            }

            return;
        }

        // Ctrl+Shift+Z 取消撤销
        if ((e.ctrlKey || e.metaKey) && e.shiftKey && key === 'z') {
            e.preventDefault();
            redo();
            return;
        }
        // Ctrl+Z 撤销
        if ((e.ctrlKey || e.metaKey) && key === 'z') {
            e.preventDefault();
            undo();
        }
        
        // Ctrl+C 复制
        if ((e.ctrlKey || e.metaKey) && key === 'c') {
            e.preventDefault(); // 防止浏览器默认复制行为
            copy();
        }

        // Ctrl+V 粘贴
        if ((e.ctrlKey || e.metaKey) && key === 'v') {
            e.preventDefault();
            paste();
        }

        // Delete 删除
        if (key === 'delete' || key === 'backspace') {
            deleteSelected();
        }
    });
}

