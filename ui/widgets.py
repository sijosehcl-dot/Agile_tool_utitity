import tkinter as tk
from tkinter import ttk

class EditableTree(ttk.Treeview):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.bind("<Double-1>", self._edit)
        self._editor = None

    def _edit(self, event):
        region = self.identify("region", event.x, event.y)
        if region != "cell":
            return
        row = self.identify_row(event.y)
        col = self.identify_column(event.x)
        if not row or not col:
            return
        x, y, w, h = self.bbox(row, col)
        value = self.set(row, col)
        self._editor = tk.Entry(self)
        self._editor.insert(0, value)
        self._editor.place(x=x, y=y, width=w, height=h)
        self._editor.focus()
        def on_return(e=None):
            self.set(row, col, self._editor.get())
            self._editor.destroy()
            self._editor = None
        self._editor.bind("<Return>", on_return)
        self._editor.bind("<FocusOut>", on_return)

