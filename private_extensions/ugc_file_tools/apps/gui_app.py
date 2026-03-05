from __future__ import annotations

import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import tkinter as tk
from tkinter import filedialog, ttk

from ugc_file_tools.output_paths import resolve_out_dir
from ugc_file_tools.repo_paths import repo_root
from ugc_file_tools.tool_registry import TOOL_SPECS, ToolSpec


@dataclass(frozen=True, slots=True)
class _RunResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


def _workspace_root() -> Path:
    return repo_root()


def _parse_user_args_text(text: str) -> list[str]:
    t = str(text or "").strip()
    if t == "":
        return []
    lines = [line.strip() for line in t.splitlines() if line.strip()]
    if len(lines) >= 2:
        # 多行模式：每行一个 arg，避免 Windows 引号/转义规则差异
        return lines
    return [str(x) for x in shlex.split(t, posix=False)]


def _run_subprocess(*, argv: list[str], cwd: Path) -> _RunResult:
    completed = subprocess.run(
        list(argv),
        cwd=str(Path(cwd).resolve()),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return _RunResult(
        argv=list(argv),
        returncode=int(completed.returncode),
        stdout=str(completed.stdout or ""),
        stderr=str(completed.stderr or ""),
    )


def _infer_graph_generater_root_from_package_dir(package_dir: Path) -> Path:
    p = Path(package_dir).resolve()
    for candidate in [p] + list(p.parents):
        if (candidate / "engine").is_dir() and (candidate / "app").is_dir() and (candidate / "assets").is_dir():
            return candidate
    raise FileNotFoundError(f"无法从项目目录推断 Graph_Generater 根目录：{str(p)}")


def _is_graph_generater_package_dir(package_dir: Path) -> bool:
    p = Path(package_dir).resolve()
    return (p / "节点图").is_dir()


class UGCFileToolsGUI:
    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._root.title("UGC File Tools GUI")
        self._root.geometry("1120x780")

        self._workspace_root = _workspace_root()

        self._tool_specs_by_section: dict[str, list[ToolSpec]] = {}
        for spec in TOOL_SPECS:
            self._tool_specs_by_section.setdefault(str(spec.section), []).append(spec)

        self._build_ui()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self._root, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        top_bar = ttk.Frame(outer)
        top_bar.pack(fill=tk.X)

        ttk.Label(top_bar, text=f"workspace: {str(self._workspace_root)}").pack(side=tk.LEFT)
        ttk.Button(top_bar, text="清空输出", command=self._clear_output).pack(side=tk.RIGHT)

        body = ttk.PanedWindow(outer, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        left = ttk.Frame(body)
        right = ttk.Frame(body)
        body.add(left, weight=1)
        body.add(right, weight=2)

        self._notebook = ttk.Notebook(left)
        self._notebook.pack(fill=tk.BOTH, expand=True)

        self._tab_pack = ttk.Frame(self._notebook, padding=10)
        self._tab_tool = ttk.Frame(self._notebook, padding=10)
        self._tab_raw = ttk.Frame(self._notebook, padding=10)
        self._notebook.add(self._tab_pack, text="一键生成 GIL")
        self._notebook.add(self._tab_tool, text="工具（tool）")
        self._notebook.add(self._tab_raw, text="高级：直接输入子命令")

        self._build_tab_pack(self._tab_pack)
        self._build_tab_tool(self._tab_tool)
        self._build_tab_raw(self._tab_raw)

        # 输出区
        out_frame = ttk.Frame(right)
        out_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(out_frame, text="输出").pack(anchor=tk.W)
        text_frame = ttk.Frame(out_frame)
        text_frame.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

        self._output = tk.Text(text_frame, wrap=tk.NONE)
        y_scroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self._output.yview)
        x_scroll = ttk.Scrollbar(text_frame, orient=tk.HORIZONTAL, command=self._output.xview)
        self._output.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self._output.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)

        self._append_output("GUI ready.\n")

    def _build_tab_pack(self, parent: ttk.Frame) -> None:
        # 项目目录（Graph_Generater/assets/资源库/项目存档/<package>）
        row = 0

        ttk.Label(parent, text="项目存档目录（包含“节点图/”）").grid(row=row, column=0, sticky="w")
        self._pack_package_dir_var = tk.StringVar(value="")
        entry_pkg = ttk.Entry(parent, textvariable=self._pack_package_dir_var)
        entry_pkg.grid(row=row, column=1, sticky="ew", padx=(8, 8))
        ttk.Button(parent, text="选择目录…", command=self._pick_package_dir).grid(row=row, column=2, sticky="ew")
        row += 1

        ttk.Label(parent, text="Graph_Generater 根目录").grid(row=row, column=0, sticky="w", pady=(8, 0))
        self._pack_gg_root_var = tk.StringVar(value="")
        entry_gg = ttk.Entry(parent, textvariable=self._pack_gg_root_var)
        entry_gg.grid(row=row, column=1, sticky="ew", padx=(8, 8), pady=(8, 0))
        ttk.Button(parent, text="选择目录…", command=self._pick_gg_root_dir).grid(row=row, column=2, sticky="ew", pady=(8, 0))
        row += 1

        ttk.Label(parent, text="package_id").grid(row=row, column=0, sticky="w", pady=(8, 0))
        self._pack_package_id_var = tk.StringVar(value="")
        ttk.Entry(parent, textvariable=self._pack_package_id_var).grid(row=row, column=1, sticky="ew", padx=(8, 8), pady=(8, 0))
        row += 1

        ttk.Label(parent, text="scope").grid(row=row, column=0, sticky="w", pady=(8, 0))
        self._pack_scope_var = tk.StringVar(value="all")
        ttk.Combobox(
            parent,
            textvariable=self._pack_scope_var,
            values=["all", "server", "client"],
            state="readonly",
        ).grid(row=row, column=1, sticky="w", padx=(8, 8), pady=(8, 0))
        row += 1

        self._pack_scan_all_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(parent, text="scan-all（扫描 节点图/**.py）", variable=self._pack_scan_all_var).grid(
            row=row, column=1, sticky="w", padx=(8, 8), pady=(8, 0)
        )
        row += 1

        ttk.Label(parent, text="output_gil（写入 ugc_file_tools/out/）").grid(row=row, column=0, sticky="w", pady=(8, 0))
        self._pack_output_gil_var = tk.StringVar(value="test2_all_graphs.scan_all.writeback.gil")
        ttk.Entry(parent, textvariable=self._pack_output_gil_var).grid(row=row, column=1, sticky="ew", padx=(8, 8), pady=(8, 0))
        row += 1

        ttk.Label(parent, text="output_model_dir（写入 ugc_file_tools/out/）").grid(row=row, column=0, sticky="w", pady=(8, 0))
        self._pack_output_model_dir_var = tk.StringVar(value="test2_graph_models_scan_all")
        ttk.Entry(parent, textvariable=self._pack_output_model_dir_var).grid(
            row=row, column=1, sticky="ew", padx=(8, 8), pady=(8, 0)
        )
        row += 1

        run_bar = ttk.Frame(parent)
        run_bar.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        ttk.Button(run_bar, text="生成 GIL", command=self._run_pack).pack(side=tk.LEFT)
        ttk.Button(run_bar, text="打开 out 目录", command=self._open_out_dir).pack(side=tk.LEFT, padx=(10, 0))

        parent.columnconfigure(1, weight=1)

    def _build_tab_tool(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="选择工具（等价于：python -m ugc_file_tools tool <name> ...）").pack(anchor=tk.W)

        split = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        split.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        left = ttk.Frame(split)
        right = ttk.Frame(split)
        split.add(left, weight=1)
        split.add(right, weight=2)

        self._tool_tree = ttk.Treeview(left, show="tree")
        y_scroll = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self._tool_tree.yview)
        self._tool_tree.configure(yscrollcommand=y_scroll.set)
        self._tool_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        y_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._tool_tree.bind("<<TreeviewSelect>>", lambda _evt: self._on_tool_selected())

        # build tree
        for section, specs in sorted(self._tool_specs_by_section.items(), key=lambda x: x[0]):
            sec_item = self._tool_tree.insert("", tk.END, text=str(section), open=True)
            for spec in sorted(specs, key=lambda s: s.name):
                self._tool_tree.insert(sec_item, tk.END, text=str(spec.name), values=(spec.name,))

        self._tool_selected_var = tk.StringVar(value="")
        self._tool_risk_var = tk.StringVar(value="")
        self._tool_summary_var = tk.StringVar(value="")

        info = ttk.Frame(right)
        info.pack(fill=tk.X)
        ttk.Label(info, text="tool").grid(row=0, column=0, sticky="w")
        ttk.Label(info, textvariable=self._tool_selected_var).grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Label(info, text="risk").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Label(info, textvariable=self._tool_risk_var).grid(row=1, column=1, sticky="w", padx=(8, 0), pady=(6, 0))
        ttk.Label(info, text="summary").grid(row=2, column=0, sticky="nw", pady=(6, 0))
        ttk.Label(info, textvariable=self._tool_summary_var, wraplength=520, justify="left").grid(
            row=2, column=1, sticky="w", padx=(8, 0), pady=(6, 0)
        )
        info.columnconfigure(1, weight=1)

        ttk.Label(right, text="参数（可单行，也可多行：每行一个 arg）").pack(anchor=tk.W, pady=(12, 0))
        self._tool_args_text = tk.Text(right, height=7)
        self._tool_args_text.pack(fill=tk.X, pady=(6, 0))

        run_bar = ttk.Frame(right)
        run_bar.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(run_bar, text="运行", command=self._run_selected_tool).pack(side=tk.LEFT)

    def _build_tab_raw(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="输入 ugc_file_tools 子命令（例如：ui dump-json --input-gil xxx.gil）").pack(anchor=tk.W)
        self._raw_args_text = tk.Text(parent, height=10)
        self._raw_args_text.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        run_bar = ttk.Frame(parent)
        run_bar.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(run_bar, text="运行", command=self._run_raw_command).pack(side=tk.LEFT)

    def _append_output(self, text: str) -> None:
        self._output.insert(tk.END, str(text))
        self._output.see(tk.END)

    def _clear_output(self) -> None:
        self._output.delete("1.0", tk.END)

    def _open_out_dir(self) -> None:
        out_dir = resolve_out_dir().resolve()
        # Windows: os.startfile 最简单
        import os

        os.startfile(str(out_dir))

    def _pick_package_dir(self) -> None:
        chosen = filedialog.askdirectory()
        if not chosen:
            return
        p = Path(chosen).resolve()
        self._pack_package_dir_var.set(str(p))

        if _is_graph_generater_package_dir(p):
            self._pack_package_id_var.set(str(p.name))
            gg_root = _infer_graph_generater_root_from_package_dir(p)
            self._pack_gg_root_var.set(str(gg_root))

            package_id = str(p.name)
            self._pack_output_gil_var.set(f"{package_id}_all_graphs.scan_all.writeback.gil")
            self._pack_output_model_dir_var.set(f"{package_id}_graph_models_scan_all")

    def _pick_gg_root_dir(self) -> None:
        chosen = filedialog.askdirectory()
        if not chosen:
            return
        self._pack_gg_root_var.set(str(Path(chosen).resolve()))

    def _run_pack(self) -> None:
        package_dir_text = str(self._pack_package_dir_var.get() or "").strip()
        if package_dir_text == "":
            raise ValueError("请先选择项目存档目录")

        gg_root_text = str(self._pack_gg_root_var.get() or "").strip()
        package_id = str(self._pack_package_id_var.get() or "").strip()
        if gg_root_text == "":
            gg_root_text = str(_infer_graph_generater_root_from_package_dir(Path(package_dir_text)))
            self._pack_gg_root_var.set(gg_root_text)
        if package_id == "":
            package_id = str(Path(package_dir_text).name)
            self._pack_package_id_var.set(package_id)

        scope = str(self._pack_scope_var.get() or "all").strip()
        output_gil = str(self._pack_output_gil_var.get() or "").strip() or f"{package_id}_all_graphs.scan_all.writeback.gil"
        output_model_dir = str(self._pack_output_model_dir_var.get() or "").strip() or f"{package_id}_graph_models_scan_all"

        from tkinter import messagebox

        ok = messagebox.askyesno(
            "危险写盘确认",
            "该操作会生成/写回 .gil 文件（危险写盘）。\n"
            "请确认你已备份目标文件，并明确知道自己在做什么。\n\n"
            f"package_id: {package_id}\n"
            f"scope: {scope}\n"
            f"output_gil: {output_gil}\n"
            f"output_model_dir: {output_model_dir}\n",
            parent=self._root,
        )
        if not ok:
            self._append_output("\n[cancelled] 用户取消生成 GIL。\n")
            return

        argv: list[str] = [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "ugc_file_tools.commands.write_graph_generater_package_test2_graphs_to_gil",
            "--graph-generater-root",
            gg_root_text,
            "--package-id",
            package_id,
            "--scope",
            scope,
            "--output-gil",
            output_gil,
            "--output-model-dir",
            output_model_dir,
        ]
        if bool(self._pack_scan_all_var.get()):
            argv.append("--scan-all")

        self._append_output("\n" + "=" * 80 + "\n")
        self._append_output("RUN (pack GIL)\n")
        self._append_output("argv:\n  " + " ".join(argv) + "\n\n")
        result = _run_subprocess(argv=argv, cwd=self._workspace_root)
        self._append_output(result.stdout)
        if result.stderr.strip():
            self._append_output("\n[stderr]\n" + result.stderr)
        self._append_output(f"\n[exit_code] {result.returncode}\n")
        self._append_output("=" * 80 + "\n")

    def _on_tool_selected(self) -> None:
        selected = self._tool_tree.selection()
        if not selected:
            return
        item_id = selected[0]
        parent = self._tool_tree.parent(item_id)
        if parent == "":
            # section node
            return
        name = str(self._tool_tree.item(item_id, "text") or "").strip()
        if not name:
            return

        spec = self._find_tool_spec(name)
        self._tool_selected_var.set(str(spec.name))
        self._tool_risk_var.set(str(spec.risk))
        self._tool_summary_var.set(str(spec.summary))

    def _find_tool_spec(self, name: str) -> ToolSpec:
        for spec in TOOL_SPECS:
            if str(spec.name) == str(name):
                return spec
        raise KeyError(f"未找到工具：{name!r}")

    def _run_selected_tool(self) -> None:
        tool_name = str(self._tool_selected_var.get() or "").strip()
        if tool_name == "":
            raise ValueError("请先在左侧选择一个 tool")

        spec = self._find_tool_spec(tool_name)
        is_dangerous = "危险" in str(spec.risk)
        if is_dangerous:
            from tkinter import messagebox

            ok = messagebox.askyesno(
                "危险写盘确认",
                "该工具标记为【危险写盘】。\n"
                "请确认你已备份目标文件，并明确知道自己在做什么。\n\n"
                f"tool: {spec.name}\n"
                f"summary: {spec.summary}\n",
                parent=self._root,
            )
            if not ok:
                self._append_output("\n[cancelled] 用户取消运行危险写盘工具。\n")
                return

        extra_args_text = self._tool_args_text.get("1.0", tk.END)
        extra_args = _parse_user_args_text(extra_args_text)

        argv = (
            [sys.executable, "-X", "utf8", "-m", "ugc_file_tools", "tool", "--dangerous", tool_name]
            if is_dangerous
            else [sys.executable, "-X", "utf8", "-m", "ugc_file_tools", "tool", tool_name]
        ) + list(extra_args)
        self._append_output("\n" + "=" * 80 + "\n")
        self._append_output(f"RUN (tool): {tool_name}\n")
        self._append_output("argv:\n  " + " ".join(argv) + "\n\n")
        result = _run_subprocess(argv=argv, cwd=self._workspace_root)
        self._append_output(result.stdout)
        if result.stderr.strip():
            self._append_output("\n[stderr]\n" + result.stderr)
        self._append_output(f"\n[exit_code] {result.returncode}\n")
        self._append_output("=" * 80 + "\n")

    def _run_raw_command(self) -> None:
        raw_text = self._raw_args_text.get("1.0", tk.END)
        args = _parse_user_args_text(raw_text)
        if not args:
            raise ValueError("请输入子命令，例如：ui dump-json --input-gil xxx.gil")

        argv = [sys.executable, "-X", "utf8", "-m", "ugc_file_tools"] + list(args)
        self._append_output("\n" + "=" * 80 + "\n")
        self._append_output("RUN (ugc_file_tools)\n")
        self._append_output("argv:\n  " + " ".join(argv) + "\n\n")
        result = _run_subprocess(argv=argv, cwd=self._workspace_root)
        self._append_output(result.stdout)
        if result.stderr.strip():
            self._append_output("\n[stderr]\n" + result.stderr)
        self._append_output(f"\n[exit_code] {result.returncode}\n")
        self._append_output("=" * 80 + "\n")


def main(argv: Optional[Iterable[str]] = None) -> None:
    # GUI 不解析 argv；这里只保留签名便于统一入口调用
    _ = list(argv) if argv is not None else None
    root = tk.Tk()
    _ = UGCFileToolsGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()


