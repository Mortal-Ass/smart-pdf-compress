"""Chinese desktop interface for the PDF compressor."""
import os
import queue
import threading
import sys
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from smart_pdf_compress import compress_pdf


class App:
    def __init__(self, root):
        self.root = root
        root.title("PDF 压缩助手")
        icon = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'app_icon.ico'
        if icon.exists():
            root.iconbitmap(str(icon))
        root.geometry("760x580")
        root.minsize(620, 480)
        self.events = queue.Queue()
        self.running = False
        self.result = None
        self.path = tk.StringVar()
        self.folder = tk.StringVar()
        self.size_first = tk.BooleanVar(value=False)
        self.focus_pages = tk.StringVar()
        self.status = tk.StringVar(value="请先选择一个 PDF 文件")
        box = ttk.Frame(root, padding=24)
        box.pack(fill="both", expand=True)
        ttk.Label(box, text="PDF 压缩助手", font=("Microsoft YaHei UI", 22, "bold")).pack(anchor="w")
        ttk.Label(box, text="目标：1024 KB 以内 · 保留全部页面和方向 · 原文件不会被覆盖").pack(anchor="w", pady=(6, 18))
        self.buttons = []
        for title, var, action in [("选择 PDF", self.path, self.choose), ("保存到…", self.folder, self.choose_folder)]:
            row = ttk.Frame(box)
            row.pack(fill="x", pady=5)
            ttk.Entry(row, textvariable=var, state="readonly").pack(side="left", fill="x", expand=True)
            button = ttk.Button(row, text=title, command=action)
            button.pack(side="right", padx=(8, 0))
            self.buttons.append(button)
        ttk.Label(box, text="无法达标时会保存本次最小结果并标注超限；图片、小字和印章请放大复核。", wraplength=680).pack(anchor="w", pady=12)
        self.mode = ttk.Checkbutton(box, text="优先达标：允许转成图片（文字不可复制，链接丢失，小字及二维码可能变糊）", variable=self.size_first)
        self.mode.pack(anchor="w", pady=(0, 8))
        self.buttons.append(self.mode)
        ttk.Label(box, text="重点清晰页（可选，如 3,11；需勾选优先达标）").pack(anchor="w")
        self.focus_entry = ttk.Entry(box, textvariable=self.focus_pages)
        self.focus_entry.pack(fill="x", pady=(0, 8))
        self.buttons.append(self.focus_entry)
        self.start_button = ttk.Button(box, text="开始压缩", command=self.start)
        self.start_button.pack(anchor="w")
        self.buttons.append(self.start_button)
        self.bar = ttk.Progressbar(box, mode="indeterminate")
        self.bar.pack(fill="x", pady=12)
        ttk.Label(box, textvariable=self.status, wraplength=680).pack(anchor="w")
        self.logs = tk.Text(box, height=10, state="disabled", font=("Microsoft YaHei UI", 9))
        self.logs.pack(fill="both", expand=True, pady=10)
        row = ttk.Frame(box)
        row.pack(fill="x")
        self.open_button = ttk.Button(row, text="打开结果 PDF", command=self.open_result, state="disabled")
        self.open_button.pack(side="left")
        self.folder_button = ttk.Button(row, text="打开所在文件夹", command=self.open_folder, state="disabled")
        self.folder_button.pack(side="left", padx=8)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.poll)

    def choose(self):
        name = filedialog.askopenfilename(filetypes=[("PDF 文件", "*.pdf")])
        if name:
            self.path.set(name)
            self.folder.set(str(Path(name).parent))

    def choose_folder(self):
        name = filedialog.askdirectory()
        if name:
            self.folder.set(name)

    def start(self):
        if not self.path.get():
            messagebox.showinfo("先选文件", "请点击“选择 PDF”，选择要压缩的文件。")
            return
        self.running = True
        self.result = None
        for button in self.buttons + [self.open_button, self.folder_button]:
            button.configure(state="disabled")
        self.logs.configure(state="normal")
        self.logs.delete("1.0", "end")
        self.logs.configure(state="disabled")
        self.status.set("正在压缩，大文件可能需要几分钟，请等待进度更新……")
        self.bar.start()
        source, folder = self.path.get(), self.folder.get()
        threading.Thread(target=self.work, args=(source, folder, self.size_first.get(), self.focus_pages.get()), daemon=True).start()

    def work(self, source, folder, size_first, focus_pages):
        try:
            result = compress_pdf(source, folder, log=lambda *values, **kw: self.events.put(("log", " ".join(map(str, values)))), size_first=size_first, focus_pages=focus_pages)
            self.events.put(("done", result))
        except BaseException as exc:
            self.events.put(("error", str(exc)))

    def poll(self):
        for _ in range(100):
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.logs.configure(state="normal")
                self.logs.insert("end", value + "\n")
                self.logs.see("end")
                self.logs.configure(state="disabled")
            else:
                self.running = False
                self.bar.stop()
                for button in self.buttons:
                    button.configure(state="normal")
                if kind == "error":
                    self.status.set("压缩未完成，原文件未修改。")
                    messagebox.showerror("未能完成", value)
                else:
                    self.result = value
                    text = f"{'压缩达标' if value['within_limit'] else '已完成，但超过 1024 KB'}：{value['bytes']/1024:.1f} KB，共 {value['pages']} 页。"
                    self.status.set(text)
                    self.open_button.configure(state="normal")
                    self.folder_button.configure(state="normal")
                    messagebox.showinfo("处理结果", text + "\n\n" + value["risk"] + "\n\n保存位置：" + value["output"])
        self.root.after(100, self.poll)

    def open_result(self):
        self.open_path(self.result["output"])

    def open_folder(self):
        self.open_path(str(Path(self.result["output"]).parent))

    def open_path(self, path):
        try:
            os.startfile(path)
        except OSError as exc:
            messagebox.showerror("无法打开", str(exc))

    def close(self):
        if self.running:
            messagebox.showinfo("正在处理", "请等待处理完成后再关闭窗口。")
        else:
            self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    if len(sys.argv) == 4 and sys.argv[1] in ("--self-test", "--self-test-size-first"):
        root.withdraw()
        result = compress_pdf(sys.argv[2], Path(sys.argv[3]).parent, log=lambda *a, **k: None,
                              size_first=sys.argv[1] == "--self-test-size-first")
        Path(sys.argv[3]).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        root.destroy()
        raise SystemExit(0)
    ttk.Style().theme_use("vista")
    App(root)
    root.mainloop()
