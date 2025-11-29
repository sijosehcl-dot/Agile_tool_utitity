import tkinter as tk
from tkinter import ttk, messagebox
from ui.widgets import EditableTree
import firestore

class SprintCapacityPage(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        ttk.Label(self, text="Sprint Name").grid(row=0, column=0, sticky="w", padx=8)
        self.sprint_name = ttk.Entry(self)
        self.sprint_name.grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Label(self, text="Total Days").grid(row=1, column=0, sticky="w", padx=8)
        self.total_days = ttk.Entry(self)
        self.total_days.grid(row=1, column=1, sticky="ew", padx=8)
        ttk.Label(self, text="Haircut %").grid(row=2, column=0, sticky="w", padx=8)
        self.haircut = ttk.Entry(self)
        self.haircut.grid(row=2, column=1, sticky="ew", padx=8)
        ttk.Label(self, text="Resources").grid(row=3, column=0, sticky="w", padx=8)
        self.resources_n = ttk.Entry(self)
        self.resources_n.grid(row=3, column=1, sticky="ew", padx=8)
        add = ttk.Button(self, text="Create Grid", command=self._create_grid)
        add.grid(row=3, column=2, sticky="w", padx=8)
        calc = ttk.Button(self, text="Calculate Sprint Capacity", command=self._calc)
        calc.grid(row=3, column=3, sticky="w", padx=8)
        save = ttk.Button(self, text="Save", command=self._save)
        save.grid(row=3, column=4, sticky="w", padx=8)
        cols = ("Name","Role","Tech","Leave")
        self.res = EditableTree(self, columns=cols, show="headings")
        for c in cols:
            self.res.heading(c, text=c)
            self.res.column(c, width=160, anchor="w")
        self.res.grid(row=4, column=0, columnspan=5, sticky="nsew", padx=8, pady=8)
        cols2 = ("Name","Role","Tech","Avail Days","Avail Hours","Leave")
        self.out = ttk.Treeview(self, columns=cols2, show="headings")
        for c in cols2:
            self.out.heading(c, text=c)
            self.out.column(c, width=160, anchor="w")
        self.out.grid(row=5, column=0, columnspan=5, sticky="nsew", padx=8, pady=8)
        self.sum_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.sum_var).grid(row=6, column=0, columnspan=5, sticky="w", padx=8)
        self.rowconfigure(4, weight=1)
        self.rowconfigure(5, weight=1)
        self.columnconfigure(1, weight=1)

    def _create_grid(self):
        try:
            n = int(self.resources_n.get())
        except Exception:
            n = 0
        for i in self.res.get_children():
            self.res.delete(i)
        for i in range(n):
            self.res.insert("", "end", values=("", "DEV", "", "0"))

    def _calc(self):
        try:
            total = float(self.total_days.get())
        except Exception:
            total = 0.0
        try:
            hc = float(self.haircut.get())
        except Exception:
            hc = 0.0
        hcd = (hc / 100.0) * total
        leaves_total = 0.0
        for iid in self.res.get_children():
            vals = self.res.item(iid, "values")
            try:
                leaves_total += float(vals[3])
            except Exception:
                pass
        avail_days = max(0.0, total - (hcd + leaves_total))
        avail_hours = avail_days * 8.0
        for i in self.out.get_children():
            self.out.delete(i)
        for iid in self.res.get_children():
            name, role, tech, leave = self.res.item(iid, "values")
            try:
                ld = float(leave)
            except Exception:
                ld = 0.0
            r_days = max(0.0, total - (hcd + ld))
            r_hours = r_days * 8.0
            self.out.insert("", "end", values=(name, role, tech, f"{r_days:.2f}", f"{r_hours:.2f}", f"{ld:.2f}"))
        self.sum_var.set(f"Capacity Days: {avail_days:.2f} | Hours: {avail_hours:.2f} | Leaves: {leaves_total:.2f}")

    def _save(self):
        record = {
            "sprint_name": self.sprint_name.get(),
            "total_days": self.total_days.get(),
            "haircut": self.haircut.get(),
            "resources": [
                {
                    "name": v[0],
                    "role": v[1],
                    "tech": v[2],
                    "leave": v[3],
                } for v in [self.res.item(i, "values") for i in self.res.get_children()]
            ],
            "summary": self.sum_var.get(),
            "resource_summary": [self.out.item(i, "values") for i in self.out.get_children()],
        }
        firestore.save_sprint_capacity(record)
        messagebox.showinfo("Saved", "Sprint capacity saved")

class SprintRetrievePage(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.names = ttk.Combobox(self, values=firestore.get_sprint_names())
        self.names.grid(row=0, column=0, sticky="w", padx=8, pady=8)
        load = ttk.Button(self, text="Load", command=self._load)
        load.grid(row=0, column=1, sticky="w", padx=8)
        self.sprint = ttk.Treeview(self, columns=("Field","Value"), show="headings")
        for c in ("Field","Value"):
            self.sprint.heading(c, text=c)
            self.sprint.column(c, width=240, anchor="w")
        self.sprint.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=8, pady=8)
        cols = ("Name","Role","Tech","Avail Days","Avail Hours","Leave")
        self.res = ttk.Treeview(self, columns=cols, show="headings")
        for c in cols:
            self.res.heading(c, text=c)
            self.res.column(c, width=160, anchor="w")
        self.res.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=8, pady=8)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=1)

    def _load(self):
        name = self.names.get()
        rec = firestore.get_sprint_capacity(name)
        for i in self.sprint.get_children():
            self.sprint.delete(i)
        for k in ["sprint_name","total_days","haircut","summary"]:
            self.sprint.insert("", "end", values=(k, rec.get(k, "")))
        for i in self.res.get_children():
            self.res.delete(i)
        for r in rec.get("resource_summary", []):
            self.res.insert("", "end", values=tuple(r))

