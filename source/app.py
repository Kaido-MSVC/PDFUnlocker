from __future__ import annotations

import os
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk
from core import Qpdf, ProcessingError, discover, process_batch

# Tk polygons also work when Windows blocks private font registration.
if ctk.DrawEngine.preferred_drawing_method == 'circle_shapes':
    ctk.DrawEngine.preferred_drawing_method = 'polygon_shapes'

VERSION = '1.0.2'
APP_NAME = 'PDF 批次解鎖（PDFUnlocker）'
PUBLISHER = 'Kaido-MSVC'


def resource(name):
    return Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / name


def asset(name):
    return resource('assets') / name


def read_document(name):
    try:
        return resource(name).read_text(encoding='utf-8')
    except OSError:
        return f'找不到 {name}，請完整解壓分享包並保留 _internal 資料夾。'


class TextDialog(ctk.CTkToplevel):
    def __init__(self, master, title, text):
        super().__init__(master)
        self.title(title)
        self.geometry('720x560')
        self.minsize(480, 320)
        self.transient(master)
        self.after(100, lambda: self.iconbitmap(str(asset('app.ico'))))
        box = ctk.CTkTextbox(self, wrap='word', font=('Consolas', 12))
        box.pack(fill='both', expand=True, padx=16, pady=(16, 8))
        box.insert('0.0', text)
        box.configure(state='disabled')
        ctk.CTkButton(self, text='關閉', width=110, command=self.destroy).pack(pady=(4, 14))
        self.bind('<Escape>', lambda e: self.destroy())
        self.focus_set()


class AboutDialog(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title('關於')
        self.geometry('680x600')
        self.minsize(520, 440)
        self.transient(master)
        self.after(100, lambda: self.iconbitmap(str(asset('app.ico'))))
        ctk.CTkLabel(self, text=APP_NAME, font=('Microsoft JhengHei UI', 22, 'bold')).pack(pady=(20, 4))
        ctk.CTkLabel(self, text=f'版本 {VERSION}').pack()
        ctk.CTkLabel(self, text=f'作者／發行者：{PUBLISHER}').pack(pady=(2, 0))
        license_row = ctk.CTkFrame(self, fg_color='transparent')
        license_row.pack(pady=8)
        ctk.CTkLabel(license_row, text=f'授權：MIT License　Copyright (c) 2026 {PUBLISHER}').pack(side='left', padx=(0, 10))
        ctk.CTkButton(license_row, text='檢視 LICENSE 全文', width=150,
                      command=lambda: TextDialog(self, 'LICENSE', read_document('LICENSE'))).pack(side='left')
        ctk.CTkLabel(self, text='第三方元件授權', font=('Microsoft JhengHei UI', 14, 'bold')).pack(anchor='w', padx=20, pady=(8, 2))
        notices = ctk.CTkTextbox(self, wrap='none', font=('Consolas', 11))
        notices.pack(fill='both', expand=True, padx=20)
        notices.insert('0.0', read_document('THIRD_PARTY_NOTICES.txt'))
        notices.configure(state='disabled')
        ctk.CTkButton(self, text='關閉', width=110, command=self.destroy).pack(pady=14)
        self.bind('<Escape>', lambda e: self.destroy())
        self.focus_set()


class PasswordDialog(ctk.CTkToplevel):
    def __init__(self, master, path, reason, callback):
        super().__init__(master)
        self.callback = callback
        self.title('個別 PDF 密碼')
        self.geometry('550x270')
        self.resizable(False, False)
        self.transient(master)
        self.after(100, lambda: self.iconbitmap(str(asset('app.ico'))))
        ctk.CTkLabel(self, text='需要開啟密碼', font=('Microsoft JhengHei UI', 20, 'bold')).pack(pady=(18, 6))
        ctk.CTkLabel(self, text=path.name, wraplength=500).pack()
        ctk.CTkLabel(self, text=reason, text_color='#fbbf24').pack(pady=6)
        self.entry = ctk.CTkEntry(self, width=480, show='●', placeholder_text='密碼僅用於此檔案')
        self.entry.pack(pady=8)
        buttons = ctk.CTkFrame(self, fg_color='transparent')
        buttons.pack(pady=10)
        ctk.CTkButton(buttons, text='解鎖', command=lambda: self.finish(self.entry.get())).pack(side='left', padx=6)
        ctk.CTkButton(buttons, text='跳過此檔', fg_color='#475569', command=lambda: self.finish(None)).pack(side='left', padx=6)
        ctk.CTkButton(buttons, text='取消剩餘', fg_color='#92400e', command=self.cancel_all).pack(side='left', padx=6)
        self.protocol('WM_DELETE_WINDOW', lambda: self.finish(None))
        self.bind('<Return>', lambda e: self.finish(self.entry.get()))
        self.bind('<Escape>', lambda e: self.finish(None))
        self.grab_set()
        self.entry.focus_set()

    def cancel_all(self):
        self.master.cancel_remaining()

    def finish(self, value):
        if value is not None and any(c in value for c in ('\r', '\n', '\x00')):
            self.entry.delete(0, 'end')
            messagebox.showerror('密碼格式', '密碼不能包含換行或 NUL 字元。', parent=self)
            return
        self.entry.delete(0, 'end')
        self.grab_release()
        self.destroy()
        self.callback(value)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f'PDF 批次解鎖 v{VERSION}')
        self.geometry('1060x740')
        self.minsize(860, 620)
        self.iconbitmap(str(asset('app.ico')))
        self.events = queue.Queue()
        self.cancel_event = threading.Event()
        self.paths = []
        self.path_keys = set()
        self.running = False
        self.closing = False
        self.dialog = None
        self.response = None
        self.counts = {'success': 0, 'fail': 0, 'skip': 0}
        self.row_by_path = {}
        self.about = None
        menubar = tk.Menu(self)
        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label='關於', command=self.show_about)
        menubar.add_cascade(label='說明', menu=help_menu)
        self.configure(menu=menubar)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        header = ctk.CTkFrame(self, fg_color='transparent')
        header.grid(row=0, column=0, sticky='ew', padx=24, pady=(20, 8))
        ctk.CTkLabel(header, text='PDF 批次解鎖', font=('Microsoft JhengHei UI', 27, 'bold')).pack(anchor='w')
        ctk.CTkLabel(header, text='依序處理 · 原檔旁的 Unlocked 資料夾 · 同名自動編號', text_color='#a8b6c9').pack(anchor='w')
        controls = ctk.CTkFrame(self)
        controls.grid(row=1, column=0, sticky='ew', padx=24, pady=8)
        self.add_files = ctk.CTkButton(controls, text='加入 PDF（多選）', command=self.choose_files)
        self.add_files.pack(side='left', padx=12, pady=12)
        self.add_folder = ctk.CTkButton(controls, text='加入資料夾（含子目錄）', width=185, command=self.choose_folder)
        self.add_folder.pack(side='left', padx=4)
        self.clear_button = ctk.CTkButton(controls, text='清空清單', width=110, fg_color='#475569', command=self.clear)
        self.clear_button.pack(side='left', padx=12)
        self.selected_label = ctk.CTkLabel(controls, text='0 個 PDF')
        self.selected_label.pack(side='right', padx=12)
        security = ctk.CTkFrame(self)
        security.grid(row=2, column=0, sticky='ew', padx=24, pady=8)
        ctk.CTkLabel(security, text='共用密碼（選填）').pack(side='left', padx=12, pady=16)
        self.password = ctk.CTkEntry(security, show='●', width=250, placeholder_text='需要開啟密碼時先試')
        self.password.pack(side='left', padx=4)
        ctk.CTkLabel(security, text='不寫入檔案或紀錄；開始後清空輸入欄', text_color='#a8b6c9').pack(side='left', padx=12)
        table_frame = ctk.CTkFrame(self)
        table_frame.grid(row=3, column=0, sticky='nsew', padx=24, pady=8)
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('Treeview', background='#172231', fieldbackground='#172231', foreground='#e5edf6', rowheight=34, font=('Microsoft JhengHei UI', 10), borderwidth=0)
        style.configure('Treeview.Heading', background='#25354a', foreground='white', font=('Microsoft JhengHei UI', 10, 'bold'))
        style.map('Treeview', background=[('selected', '#285b8a')])
        self.tree = ttk.Treeview(table_frame, columns=('file', 'state', 'detail'), show='headings')
        for col, label, width in [('file', '檔案（雙擊查看完整路徑）', 350), ('state', '狀態', 85), ('detail', '類型／結果', 490)]:
            self.tree.heading(col, text=label)
            self.tree.column(col, width=width, minwidth=70, stretch=col != 'state')
        self.tree.grid(row=0, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(table_frame, orient='vertical', command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky='ns')
        horizontal = ttk.Scrollbar(table_frame, orient='horizontal', command=self.tree.xview)
        horizontal.grid(row=1, column=0, sticky='ew')
        self.tree.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)
        self.tree.bind('<Double-1>', self.show_path)
        footer = ctk.CTkFrame(self, fg_color='transparent')
        footer.grid(row=4, column=0, sticky='ew', padx=24, pady=(8, 20))
        self.status = ctk.CTkLabel(footer, text='就緒。資料夾掃描會略過 Unlocked 與目錄連結。', anchor='w', wraplength=780)
        self.status.pack(fill='x')
        self.progress = ctk.CTkProgressBar(footer)
        self.progress.set(0)
        self.progress.pack(fill='x', pady=10)
        self.counter = ctk.CTkLabel(footer, text='成功 0　失敗 0　跳過 0')
        self.counter.pack(side='left')
        self.start_button = ctk.CTkButton(footer, text='開始解鎖', command=self.start)
        self.start_button.pack(side='right', padx=(8, 0))
        self.cancel_button = ctk.CTkButton(footer, text='取消剩餘工作', fg_color='#92400e', state='disabled', command=self.cancel_remaining)
        self.cancel_button.pack(side='right')
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(60, self.poll)

    def set_busy(self, busy):
        self.running = busy
        for button in (self.add_files, self.add_folder, self.clear_button, self.start_button, self.password):
            button.configure(state='disabled' if busy else 'normal')
        self.cancel_button.configure(state='normal' if busy else 'disabled')

    def choose_files(self):
        files = filedialog.askopenfilenames(parent=self, title='選擇 PDF', filetypes=[('PDF 文件', '*.pdf')])
        if files:
            self.scan([Path(p) for p in files])

    def choose_folder(self):
        folder = filedialog.askdirectory(parent=self, title='選擇資料夾（包含子目錄）')
        if folder:
            self.scan([Path(folder)])

    def scan(self, items):
        self.cancel_event.clear()
        self.set_busy(True)
        self.status.configure(text='正在掃描 PDF… 可取消。')
        def worker():
            try:
                paths, ignored = discover(items, self.cancel_event)
                for offset in range(0, len(paths), 100):
                    self.events.put(('discovered', paths[offset:offset + 100]))
                self.events.put(('scan_summary', (len(paths), ignored)))
            except Exception:
                self.events.put(('error', '掃描失敗，請檢查資料夾權限。'))
            finally:
                self.events.put(('done_scan', None))
        threading.Thread(target=worker, daemon=True).start()

    def add_paths(self, paths):
        for path in paths:
            if os.path.normcase(str(path)) in self.path_keys:
                continue
            self.path_keys.add(os.path.normcase(str(path)))
            self.paths.append(path)
            row = self.tree.insert('', 'end', values=(path.name, '待處理', str(path.parent)))
            self.row_by_path[path] = row
        self.selected_label.configure(text=f'{len(self.paths)} 個 PDF')

    def clear(self):
        self.paths.clear()
        self.path_keys.clear()
        self.row_by_path.clear()
        self.tree.delete(*self.tree.get_children())
        self.selected_label.configure(text='0 個 PDF')
        self.progress.set(0)

    def start(self):
        if not self.paths:
            messagebox.showinfo('尚未選擇', '請先加入 PDF 或資料夾。', parent=self)
            return
        try:
            engine = Qpdf()
        except ProcessingError as exc:
            messagebox.showerror('qpdf', str(exc), parent=self)
            return
        common = self.password.get()
        if any(c in common for c in ('\r', '\n', '\x00')):
            self.password.delete(0, 'end')
            messagebox.showerror('密碼格式', '密碼不能包含換行或 NUL 字元。', parent=self)
            return
        self.password.delete(0, 'end')
        self.cancel_event.clear()
        self.counts = dict.fromkeys(self.counts, 0)
        self.update_counts()
        self.progress.set(0)
        self.set_busy(True)
        for path, row in self.row_by_path.items():
            self.tree.item(row, values=(path.name, '待處理', str(path.parent)))
        def ask(path, reason):
            response = queue.Queue(maxsize=1)
            self.events.put(('ask', (path, reason, response)))
            while not self.cancel_event.is_set():
                try:
                    return response.get(timeout=0.1)
                except queue.Empty:
                    pass
            return None
        def worker(secret):
            outcome = 'completed'
            try:
                process_batch(list(self.paths), secret, self.cancel_event, ask,
                              lambda event, value: self.events.put((event, value)), engine)
                if self.cancel_event.is_set():
                    outcome = 'cancelled'
            except Exception:
                outcome = 'error'
                self.events.put(('error', '工作發生非預期錯誤，請重新啟動後重試。'))
            finally:
                secret = ''
                self.events.put(('done', outcome))
        threading.Thread(target=worker, args=(common,), daemon=True).start()
        common = ''

    def respond(self, value):
        if self.response is not None:
            self.response.put(value)
        self.response = None
        self.dialog = None

    def cancel_remaining(self):
        self.cancel_event.set()
        self.cancel_button.configure(state='disabled')
        self.status.configure(text='已取消剩餘工作；目前的 qpdf 操作會先完成（每次最多 5 分鐘）。')
        if self.dialog is not None:
            self.dialog.finish(None)

    def update_counts(self):
        c = self.counts
        self.counter.configure(text=f'成功 {c["success"]}　失敗 {c["fail"]}　跳過 {c["skip"]}')

    def show_about(self):
        if self.about is not None and self.about.winfo_exists():
            self.about.lift()
            self.about.focus_set()
            return
        self.about = AboutDialog(self)

    def show_path(self, _event=None):
        selected = self.tree.selection()
        if selected:
            row = selected[0]
            path = next((p for p, r in self.row_by_path.items() if r == row), None)
            if path:
                messagebox.showinfo('檔案路徑', str(path), parent=self)

    def poll(self):
        # Bound each polling turn so large queues cannot starve Tk's event loop.
        deadline = time.monotonic() + .02
        for _ in range(100):
            if time.monotonic() >= deadline:
                break
            try:
                event, value = self.events.get_nowait()
            except queue.Empty:
                break
            if event == 'discovered':
                self.add_paths(value)
            elif event == 'scan_summary':
                count, ignored = value
                self.status.configure(text=f'掃描完成：候選 {count} 個 PDF；無法讀取的檔案／資料夾已略過 {ignored} 個。')
            elif event == 'current':
                number, path = value
                self.status.configure(text=f'處理 {number} / {len(self.paths)}：{path.name[:95]}')
                self.tree.item(self.row_by_path[path], values=(path.name, '處理中', '辨識加密類型…'))
            elif event == 'result':
                self.counts[value.state] += 1
                detail = value.detail + (f' → {value.output}' if value.output else '')
                self.tree.item(self.row_by_path[value.path], values=(value.path.name, {'success': '成功', 'fail': '失敗', 'skip': '跳過'}[value.state], detail))
                self.update_counts()
                self.progress.set(sum(self.counts.values()) / max(1, len(self.paths)))
            elif event == 'ask':
                path, reason, response = value
                if self.cancel_event.is_set():
                    response.put(None)
                else:
                    self.response = response
                    self.dialog = PasswordDialog(self, path, reason, self.respond)
            elif event == 'error':
                self.status.configure(text=value)
                messagebox.showerror('處理錯誤', value, parent=self)
            elif event in ('done', 'done_scan'):
                self.set_busy(False)
                if event == 'done':
                    if value == 'error':
                        unfinished = 0
                        for path, row in self.row_by_path.items():
                            state = self.tree.item(row, 'values')[1]
                            if state in ('待處理', '處理中'):
                                unfinished += 1
                                label = '未完成' if state == '處理中' else '未處理'
                                self.tree.item(row, values=(path.name, label, '批次異常中止；未取得處理結果，請確認後重試。'))
                        self.status.configure(text=f'批次異常中止；{unfinished} 個項目未取得處理結果。請確認後重新啟動重試。')
                    elif value == 'cancelled':
                        self.status.configure(text='已取消；目前工作已結束。')
                    else:
                        self.status.configure(text='批次完成。雙擊清單可查看原檔完整路徑。')
                if self.closing:
                    self.destroy()
                    return
        self.after(60, self.poll)

    def close(self):
        if self.running:
            self.closing = True
            self.cancel_remaining()
            self.status.configure(text='正在結束目前工作並清理暫存檔，完成後自動關閉…')
        else:
            self.password.delete(0, 'end')
            self.destroy()


def main():
    ctk.set_appearance_mode('dark')
    ctk.set_default_color_theme('blue')
    App().mainloop()


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--smoke-test':
        from smoke import run
        run(Path(sys.argv[2]))
    else:
        main()
