import { dom, state, setStatusText } from "./context.js";
import { fetchJson } from "./api.js";
import { isDerivedHtmlFileName } from "./helpers.js";
import { isFileChecked, pruneCheckedFilesByCatalogItems, setFileChecked } from "./storage.js";

var _callbacks = {
  selectFile: async function () {},
  onCheckedFilesChanged: function () {},
};

export function setCatalogCallbacks(cb) {
  _callbacks = cb || _callbacks;
}

export function renderFileList() {
  if (!dom.fileList) return;
  var q = String((dom.searchInput && dom.searchInput.value) || "").trim().toLowerCase();

  dom.fileList.innerHTML = "";
  var items = state.items || [];
  var shown = 0;
  var checkedCount = 0;

  for (var i = 0; i < items.length; i++) {
    var it = items[i] || {};
    var fileName = String(it.file_name || it.fileName || "");
    var scope = String(it.scope || "project");
    var isShared = !!(it.is_shared || it.isShared);
    if (!fileName) continue;

    // 永远隐藏派生文件：只展示“原稿 HTML”作为可操作入口
    if (isDerivedHtmlFileName(fileName)) continue;
    if (q && fileName.toLowerCase().indexOf(q) < 0) continue;

    var row = document.createElement("button");
    row.type = "button";
    row.className = "item";
    row.dataset.scope = scope;
    row.dataset.fileName = fileName;

    if (state.selected && state.selected.scope === scope && state.selected.file_name === fileName) {
      row.classList.add("selected");
    }

    var checkWrap = document.createElement("label");
    checkWrap.className = "checkbox";
    checkWrap.style.margin = "0";
    checkWrap.style.cursor = "pointer";
    checkWrap.title = "勾选：导出 GIL 时把该页面一起写入同一份 .gil（可多选）";
    var checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = isFileChecked(scope, fileName);
    checkbox.addEventListener("click", function (ev) {
      // 防止触发 row 的点击（避免误切换预览）
      ev.stopPropagation();
    });
    checkbox.addEventListener("change", function (ev) {
      ev.stopPropagation();
      var el = ev.currentTarget;
      var parentRow = el && el.closest ? el.closest("button.item") : null;
      if (!parentRow) return;
      var s = String(parentRow.dataset.scope || "project");
      var fn = String(parentRow.dataset.fileName || "");
      setFileChecked(s, fn, !!el.checked);
      _callbacks.onCheckedFilesChanged();
      renderFileList();
    });
    checkWrap.appendChild(checkbox);

    var badge = document.createElement("span");
    badge.className = "badge" + (isShared ? " shared" : "");
    badge.textContent = isShared ? "共享" : "项目";

    var title = document.createElement("div");
    title.className = "item-title";
    title.textContent = fileName;

    var meta = document.createElement("div");
    meta.className = "item-meta";
    var cacheKey = scope + ":" + fileName;
    meta.textContent = state.flattened_cache && state.flattened_cache[cacheKey] ? "已扁平" : "自动扁平";

    row.appendChild(checkWrap);
    row.appendChild(badge);
    row.appendChild(title);
    row.appendChild(meta);
    row.addEventListener("click", async function (ev) {
      var el = ev.currentTarget;
      var s = String(el.dataset.scope || "project");
      var fn = String(el.dataset.fileName || "");
      await _callbacks.selectFile(s, fn);
    });

    dom.fileList.appendChild(row);
    shown += 1;
    if (isFileChecked(scope, fileName)) {
      checkedCount += 1;
    }
  }

  if (dom.fileCountText) {
    dom.fileCountText.textContent = checkedCount > 0
      ? (String(shown) + "（勾选 " + String(checkedCount) + "）")
      : String(shown);
  }
  if (shown === 0) {
    var empty = document.createElement("div");
    empty.style.color = "var(--muted)";
    empty.style.padding = "6px";
    empty.textContent = "没有匹配的文件。";
    dom.fileList.appendChild(empty);
  }
}

export async function refreshCatalog() {
  setStatusText("加载列表…");
  var data = await fetchJson("/api/ui_converter/ui_source_catalog");
  if (!data || !data.ok) {
    throw new Error(String((data && data.error) || "加载 UI源码 清单失败"));
  }
  state.items = data.items || [];
  pruneCheckedFilesByCatalogItems(state.items);

  // 永远隐藏派生文件：若用户上次选择的是派生 HTML，这里需要清空选择，
  // 否则会出现“当前已选中但左侧列表看不到”的错觉。
  if (state.selected && isDerivedHtmlFileName(state.selected.file_name || "")) {
    state.selected = null;
  }

  renderFileList();
  setStatusText("就绪");
}

