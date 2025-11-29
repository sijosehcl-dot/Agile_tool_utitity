import tkinter as tk
from tkinter import ttk, messagebox
from ui.widgets import EditableTree
import firestore

class QbrCapacityPage(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        ttk.Label(self, text="QBR Name").grid(row=0, column=0, sticky="w", padx=8)
        self.qbr_name = ttk.Entry(self)
        self.qbr_name.grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Label(self, text="Haircut %").grid(row=1, column=0, sticky="w", padx=8)
        self.haircut = ttk.Entry(self)
        self.haircut.grid(row=1, column=1, sticky="ew", padx=8)
        ttk.Label(self, text="Sprints").grid(row=2, column=0, sticky="w", padx=8)
        self.sprints_n = ttk.Entry(self)
        self.sprints_n.grid(row=2, column=1, sticky="ew", padx=8)
        s_add = ttk.Button(self, text="Create Sprint Grid", command=self._create_sprint_grid)
        s_add.grid(row=2, column=2, sticky="w", padx=8)
        ttk.Label(self, text="Resources").grid(row=3, column=0, sticky="w", padx=8)
        self.resources_n = ttk.Entry(self)
        self.resources_n.grid(row=3, column=1, sticky="ew", padx=8)
        r_add = ttk.Button(self, text="Create Resource Grid", command=self._create_res_grid)
        r_add.grid(row=3, column=2, sticky="w", padx=8)
        calc = ttk.Button(self, text="Calculate QBR Capacity", command=self._calc)
        calc.grid(row=3, column=3, sticky="w", padx=8)
        save = ttk.Button(self, text="Save", command=self._save)
        save.grid(row=3, column=4, sticky="w", padx=8)
        self.sprint = EditableTree(self, columns=("Sprint Name","Start","End","Total Days"), show="headings")
        for c in ("Sprint Name","Start","End","Total Days"):
            self.sprint.heading(c, text=c)
            self.sprint.column(c, width=160, anchor="w")
        self.sprint.grid(row=4, column=0, columnspan=5, sticky="nsew", padx=8, pady=8)
        self.res = None
        self.sum_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.sum_var).grid(row=6, column=0, columnspan=5, sticky="w", padx=8)
        self.rowconfigure(4, weight=1)
        self.rowconfigure(5, weight=1)
        self.columnconfigure(1, weight=1)

    def _create_sprint_grid(self):
        try:
            n = int(self.sprints_n.get())
        except Exception:
            n = 0
        for i in self.sprint.get_children():
            self.sprint.delete(i)
        for i in range(n):
            self.sprint.insert("", "end", values=(f"S{i+1}", "", "", "0"))

    def _create_res_grid(self):
        try:
            n = int(self.resources_n.get())
        except Exception:
            n = 0
        try:
            scount = len(self.sprint.get_children())
        except Exception:
            scount = 0
        cols = ["Name","Role","Tech"] + [f"Leave S{j+1}" for j in range(scount)]
        if self.res:
            self.res.destroy()
        self.res = EditableTree(self, columns=tuple(cols), show="headings")
        for c in cols:
            self.res.heading(c, text=c)
            self.res.column(c, width=120 if c.startswith("Leave") else 160, anchor="w")
        self.res.grid(row=5, column=0, columnspan=5, sticky="nsew", padx=8, pady=8)
        for i in range(n):
            self.res.insert("", "end", values=tuple(["", "DEV", ""] + ["0" for _ in range(scount)]))

    def _calc(self):
        try:
            hc = float(self.haircut.get())
        except Exception:
            hc = 0.0
        srows = [self.sprint.item(i, "values") for i in self.sprint.get_children()]
        totals = []
        total_days_sum = 0.0
        total_hours_sum = 0.0
        total_leaves_sum = 0.0
        for idx, sr in enumerate(srows):
            try:
                days = float(sr[3])
            except Exception:
                days = 0.0
            total_days_sum += days
            hcd = (hc / 100.0) * days
            leaves = 0.0
            if self.res:
                for iid in self.res.get_children():
                    vals = self.res.item(iid, "values")
                    try:
                        leaves += float(vals[3 + idx])
                    except Exception:
                        pass
            total_leaves_sum += leaves
            avail = max(0.0, days - (hcd + leaves))
            hours = avail * 8.0
            total_hours_sum += hours
            totals.append((sr[0], f"{avail:.2f}", f"{hours:.2f}", f"{leaves:.2f}"))
        qbr_cap_days = sum(float(t[1]) for t in totals)
        qbr_cap_hours = sum(float(t[2]) for t in totals)
        self.sum_var.set(f"QBR Capacity Days: {qbr_cap_days:.2f} | Hours: {qbr_cap_hours:.2f} | Leaves: {total_leaves_sum:.2f}")

    def _save(self):
        rec = {
            "qbr_name": self.qbr_name.get(),
            "haircut": self.haircut.get(),
            "sprints": [self.sprint.item(i, "values") for i in self.sprint.get_children()],
            "resources": [self.res.item(i, "values") for i in (self.res.get_children() if self.res else [])],
            "summary": self.sum_var.get(),
        }
        firestore.save_qbr_capacity(rec)
        messagebox.showinfo("Saved", "QBR capacity saved")

class QbrRetrievePage(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.names = ttk.Combobox(self, values=firestore.get_qbr_names())
        self.names.grid(row=0, column=0, sticky="w", padx=8, pady=8)
        load = ttk.Button(self, text="Load", command=self._load)
        load.grid(row=0, column=1, sticky="w", padx=8)
        self.sprint = ttk.Treeview(self, columns=("Sprint Name","Start","End","Total Days"), show="headings")
        for c in ("Sprint Name","Start","End","Total Days"):
            self.sprint.heading(c, text=c)
            self.sprint.column(c, width=160, anchor="w")
        self.sprint.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=8, pady=8)
        self.res = ttk.Treeview(self, columns=("Name","Role","Tech"), show="headings")
        for c in ("Name","Role","Tech"):
            self.res.heading(c, text=c)
            self.res.column(c, width=160, anchor="w")
        self.res.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=8, pady=8)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=1)

    def _load(self):
        name = self.names.get()
        rec = firestore.get_qbr_capacity(name)
        for i in self.sprint.get_children():
            self.sprint.delete(i)
        for r in rec.get("sprints", []):
            self.sprint.insert("", "end", values=tuple(r))
        for i in self.res.get_children():
            self.res.delete(i)
        for r in rec.get("resources", []):
            self.res.insert("", "end", values=tuple(r[:3]))

