"""Dark native window frames and layouts that remain usable in small windows."""
import os
import tkinter as tk
from tkinter import ttk


def dark_titlebar(window, background='#101722', foreground='#e7edf6'):
    if os.name != 'nt':
        return False
    try:
        import ctypes
        from ctypes import wintypes
        window.update_idletasks()
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user32.GetAncestor.restype = wintypes.HWND
        hwnd = user32.GetAncestor(window.winfo_id(), 2)
        dwm = ctypes.WinDLL('dwmapi')
        dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        dwm.DwmSetWindowAttribute.restype = ctypes.c_long
        enabled = ctypes.c_int(1)
        result = dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(enabled), ctypes.sizeof(enabled))
        if result:
            result = dwm.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(enabled), ctypes.sizeof(enabled))
        def color(value):
            r, g, b = (int(value[i:i + 2], 16) for i in (1, 3, 5))
            return ctypes.c_uint(r | (g << 8) | (b << 16))
        results = {20: result}
        for attribute, value in ((35, background), (36, foreground), (34, '#304156')):
            native_color = color(value)
            results[attribute] = dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(native_color), ctypes.sizeof(native_color))
        window._dark_titlebar_results = results
        user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, ctypes.c_int, wintypes.UINT]
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0037)
        user32.RedrawWindow.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.HANDLE, wintypes.UINT]
        user32.RedrawWindow(hwnd, None, None, 0x0501)
        return result == 0
    except (OSError, tk.TclError):
        return False


def install_dark_titlebar(window, background='#101722', foreground='#e7edf6'):
    """Apply to the final HWND after mapping, and again after restoration/activation."""
    pending = set()
    def apply():
        if window.winfo_exists():
            dark_titlebar(window, background, foreground)
    def schedule(delay):
        def run():
            pending.discard(timer)
            apply()
        timer = window.after(delay, run)
        pending.add(timer)
    def mapped(event):
        if event.widget == window:
            schedule(100)
            schedule(400)
    def destroyed(event):
        if event.widget == window:
            for timer in list(pending):
                window.after_cancel(timer)
            pending.clear()
    window.bind('<Map>', mapped, add='+')
    window.bind('<FocusIn>', mapped, add='+')
    window.bind('<Destroy>', destroyed, add='+')
    schedule(100)


class FlowFrame(ttk.Frame):
    """Put controls on additional rows instead of clipping their text."""
    def __init__(self, parent, gap=6, **kwargs):
        super().__init__(parent, **kwargs)
        self.controls = []
        self.gap = gap
        self._pending = None
        self.bind('<Configure>', self.relayout, add='+')
        self.bind('<Destroy>', self._destroy, add='+')

    def _destroy(self, event):
        if event.widget == self and self._pending is not None:
            self.after_cancel(self._pending)
            self._pending = None

    def add(self, control):
        self.controls.append(control)
        self.relayout()

    def relayout(self, event=None):
        if self._pending is None:
            self._pending = self.after_idle(self._layout)

    def _layout(self):
        self._pending = None
        available = max(1, self.winfo_width())
        used = y = row_height = 0
        for control in self.controls:
            if isinstance(control, ttk.Label):
                control.configure(wraplength=max(80, available - self.gap), justify='left')
            width = min(control.winfo_reqwidth(), max(1, available - self.gap))
            height = control.winfo_reqheight()
            if used and used + width > available:
                y += row_height + self.gap
                used = row_height = 0
            control.place(x=used, y=y, width=width, height=height)
            row_height = max(row_height, height)
            used += width + self.gap
        self.configure(height=max(1, y + row_height + self.gap))


class ScrollableFrame(ttk.Frame):
    """Keep content reachable when a window is shorter than its controls."""
    def __init__(self, parent, background='#101722', **kwargs):
        super().__init__(parent, **kwargs)
        self.canvas = tk.Canvas(self, bg=background, highlightthickness=0, bd=0)
        self.scrollbar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.scrollbar.pack(side='right', fill='y')
        self.content = ttk.Frame(self.canvas)
        self.item = self.canvas.create_window(0, 0, window=self.content, anchor='nw')
        self.canvas.bind('<Configure>', self._resize, add='+')
        self.content.bind('<Configure>', self._resize, add='+')
        self.winfo_toplevel().bind('<MouseWheel>', self._wheel, add='+')

    def _resize(self, event=None):
        width = max(1, self.canvas.winfo_width())
        height = max(self.canvas.winfo_height(), self.content.winfo_reqheight())
        self.canvas.itemconfigure(self.item, width=width, height=height)
        self.canvas.configure(scrollregion=(0, 0, width, height))

    def _wheel(self, event):
        widget = event.widget
        while widget is not None:
            if isinstance(widget, (ttk.Treeview, tk.Text)):
                return
            if widget == self:
                self.canvas.yview_scroll(-int(event.delta / 120), 'units')
                return 'break'
            widget = getattr(widget, 'master', None)


def wrap_labels(container, inset=0):
    """Wrap full text to its allocated width, including long paths."""
    def resize(event):
        width = max(80, event.width - inset)
        for child in container.winfo_children():
            if isinstance(child, ttk.Label):
                child.configure(wraplength=width, justify='left')
    container.bind('<Configure>', resize, add='+')


def configure_dark_controls(style, background, card, text, accent):
    style.configure('TNotebook', background=background, borderwidth=0, tabmargins=(0, 0, 0, 6),
                    bordercolor=background, lightcolor=background, darkcolor=background)
    style.configure('TNotebook.Tab', background=card, foreground='#a8b8ca', padding=(14, 8), borderwidth=0,
                    bordercolor=background, lightcolor=background, darkcolor=background)
    style.map('TNotebook.Tab', background=[('selected', '#203d5d'), ('active', '#263b51')],
              foreground=[('selected', text), ('active', text)],
              padding=[('selected', (18, 9)), ('!selected', (12, 6))])
    style.configure('TEntry', fieldbackground='#172233', foreground=text, insertcolor=text,
                    bordercolor='#35475e', lightcolor='#35475e', darkcolor='#35475e', padding=8)
    style.map('TEntry', bordercolor=[('focus', accent)], lightcolor=[('focus', accent)],
              darkcolor=[('focus', accent)], fieldbackground=[('disabled', card)])
    style.configure('Compact.TEntry', padding=(7, 5))
    style.configure('TCheckbutton', background=background, foreground=text, padding=(0, 4),
                    indicatorbackground=card, indicatorforeground=text, indicatorcolor=card,
                    lightcolor='#35475e', darkcolor='#35475e', bordercolor='#35475e')
    style.map('TCheckbutton', background=[('active', background)], foreground=[('disabled', '#8495a9')],
              indicatorbackground=[('selected', accent), ('active', '#304156')])
    for direction in ('Vertical', 'Horizontal'):
        name = direction + '.TScrollbar'
        style.configure(name, background='#354b63', troughcolor=background, bordercolor=background,
                        lightcolor=background, darkcolor=background, arrowcolor='#a8b8ca', borderwidth=0)
        style.map(name, background=[('active', '#506b88'), ('pressed', accent)])


class TreeTooltip:
    """Expose complete filenames, status and errors without widening the window."""
    def __init__(self, tree, describe):
        self.tree = tree
        self.describe = describe
        self.window = None
        self.pending = None
        self.row = None
        self.bind(tree)

    def bind(self, widget):
        widget.bind('<Motion>', self.motion, add='+')
        for sequence in ('<Leave>', '<ButtonPress>', '<MouseWheel>', '<Destroy>'):
            widget.bind(sequence, self.hide, add='+')

    def motion(self, event):
        y = event.y_root - self.tree.winfo_rooty()
        row = self.tree.identify_row(y)
        if not row:
            self.hide()
            return
        if row != self.row:
            self.hide()
            self.row = row
            x, y = event.x_root, event.y_root
            self.pending = self.tree.after(550, lambda: self.show(x, y))

    def show(self, x, y):
        self.pending = None
        text = self.describe(self.row)
        if not text:
            return
        self.window = tk.Toplevel(self.tree)
        self.window.overrideredirect(True)
        self.window.attributes('-topmost', True)
        tk.Label(self.window, text=text, justify='left', background='#1b2738', foreground='#e7edf6',
                 wraplength=min(580, self.tree.winfo_screenwidth() - 40), padx=12, pady=8,
                 font=('Segoe UI', 9)).pack()
        self.window.update_idletasks()
        x = min(x + 12, self.tree.winfo_screenwidth() - self.window.winfo_reqwidth() - 10)
        y = min(y + 20, self.tree.winfo_screenheight() - self.window.winfo_reqheight() - 10)
        self.window.geometry(f'+{max(0, x)}+{max(0, y)}')

    def hide(self, event=None):
        if self.pending:
            self.tree.after_cancel(self.pending)
            self.pending = None
        if self.window:
            self.window.destroy()
            self.window = None
        self.row = None


def entry_context_menu(entry):
    menu = tk.Menu(entry, tearoff=False, bg='#172233', fg='#e7edf6',
                   activebackground='#203d5d', activeforeground='#ffffff')
    def edit(action):
        entry.focus_set()
        entry.event_generate(action)
    for label, action in (('Cortar', '<<Cut>>'), ('Copiar', '<<Copy>>'), ('Pegar', '<<Paste>>')):
        menu.add_command(label=label, command=lambda action=action: edit(action))
    menu.add_separator()
    menu.add_command(label='Seleccionar todo', command=lambda: (entry.focus_set(), entry.selection_range(0, 'end')))
    def popup(event):
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return 'break'
    entry.bind('<Button-3>', popup, add='+')
    entry.context_menu = menu


def install_entry_context_menus(root):
    """Include classic entries used by Tk's built-in prompt dialogs."""
    def popup(event):
        entry = event.widget
        if not hasattr(entry, 'context_menu'):
            entry_context_menu(entry)
        try:
            entry.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            entry.context_menu.grab_release()
        return 'break'
    for widget_class in ('Entry', 'TEntry'):
        root.bind_class(widget_class, '<Button-3>', popup)
