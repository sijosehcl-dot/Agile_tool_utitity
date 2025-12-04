import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import csv
import re
from prompt import load_prompts
from llm import feature_creation, feature_dor, request_features
import jira

class FeatureCreatePage(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.prompts = load_prompts()
        self.input = tk.Text(self, wrap="word", height=10)
        self.input.grid(row=0, column=0, columnspan=3, sticky="nsew", padx=8, pady=8)
        self.word_var = tk.StringVar(value="0 words")
        ttk.Label(self, textvariable=self.word_var).grid(row=1, column=0, sticky="w", padx=8)
        gen = ttk.Button(self, text="Generate Feature", command=self.generate)
        gen.grid(row=1, column=1, sticky="e", padx=8)
        create = ttk.Button(self, text="Create JIRA", command=self.create_jira)
        create.grid(row=1, column=2, sticky="e", padx=8)
        cols = ("Title","Summary","T-Shirt Size","Business Value","Priority","Issue_type")
        self.gridv = ttk.Treeview(self, columns=cols, show="headings")
        for c in cols:
            self.gridv.heading(c, text=c)
            self.gridv.column(c, width=160, anchor="w")
        self.gridv.grid(row=2, column=0, columnspan=3, sticky="nsew", padx=8, pady=8)
        self.rowconfigure(2, weight=1)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0)
        self.columnconfigure(2, weight=0)
        self.input.bind("<KeyRelease>", self._update_words)
        self.generated = []

    def _update_words(self, event=None):
        text = self.input.get("1.0", "end").strip()
        words = re.findall(r"\w+", text)
        self.word_var.set(f"{len(words)} words")

    def generate(self):
        text = self.input.get("1.0", "end").strip()
        words = re.findall(r"\w+", text)
        if len(words) > 300:
            messagebox.showerror("Limit", "Requirement must be no more than 300 words")
            return
        feats = request_features(text, self.prompts.get("feature_creation_request", self.prompts.get("feature_prompt", "")))
        self.generated = feats
        for i in self.gridv.get_children():
            self.gridv.delete(i)
        for f in feats:
            self.gridv.insert("", "end", values=(f["Title"], f["Summary"], f["T-Shirt Size"], f["Business Value"], f["Priority"], f["Issue_type"]))

    def create_jira(self):
        if not self.generated:
            messagebox.showinfo("Info", "Generate features first")
            return
        created = [jira.create_issue(f) for f in self.generated]
        keys = ", ".join(x["key"] for x in created)
        messagebox.showinfo("JIRA", f"Created: {keys}")

class FeatureUploadPage(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.prompts = load_prompts()
        up = ttk.Button(self, text="Upload CSV/Excel", command=self.upload)
        up.grid(row=0, column=0, sticky="w", padx=8, pady=8)
        gen = ttk.Button(self, text="Generate Features", command=self.generate)
        gen.grid(row=0, column=1, sticky="w", padx=8)
        create = ttk.Button(self, text="Create JIRA", command=self.create_jira)
        create.grid(row=0, column=2, sticky="w", padx=8)
        self.src = ttk.Treeview(self, columns=("Requirement",), show="headings", selectmode="extended")
        self.src.heading("Requirement", text="Requirement")
        self.src.column("Requirement", width=600, anchor="w")
        self.src.grid(row=1, column=0, columnspan=3, sticky="nsew", padx=8, pady=8)
        cols = ("Selected","Title","Summary","T-Shirt Size","Business Value","Priority","Issue_type")
        self.out = ttk.Treeview(self, columns=cols, show="headings")
        for c in cols:
            self.out.heading(c, text=c)
            w = 100 if c == "Selected" else 160
            self.out.column(c, width=w, anchor="w")
        self.out.grid(row=2, column=0, columnspan=3, sticky="nsew", padx=8, pady=8)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=1)
        self.columnconfigure(0, weight=1)
        self.data = []
        self.generated = []

    def upload(self):
        path = filedialog.askopenfilename(filetypes=[("CSV or Excel","*.csv *.xlsx")])
        if not path:
            return
        rows = []
        ext = os.path.splitext(path)[1].lower()
        if ext == ".csv":
            with open(path, newline="", encoding="utf-8") as f:
                for row in csv.reader(f):
                    if len(row) == 0:
                        continue
                    rows.append(row[0])
        elif ext == ".xlsx":
            try:
                import openpyxl
                wb = openpyxl.load_workbook(path)
                ws = wb.active
                for r in ws.iter_rows(values_only=True):
                    if r and r[0]:
                        rows.append(str(r[0]))
            except Exception:
                messagebox.showerror("Excel", "Install openpyxl to read .xlsx files")
                return
        self.data = rows
        for i in self.src.get_children():
            self.src.delete(i)
        for r in rows:
            self.src.insert("", "end", values=(r,))

    def generate(self):
        sel = self.src.selection()
        if not sel:
            messagebox.showinfo("Info", "Select requirements in grid")
            return
        feats = []
        for iid in sel:
            req = self.src.item(iid, "values")[0]
            feats.extend(request_features(req, self.prompts.get("feature_creation_request", self.prompts.get("feature_prompt", ""))))
        self.generated = feats
        for i in self.out.get_children():
            self.out.delete(i)
        for f in feats:
            self.out.insert("", "end", values=("Yes", f["Title"], f["Summary"], f["T-Shirt Size"], f["Business Value"], f["Priority"], f["Issue_type"]))

    def create_jira(self):
        if not self.generated:
            messagebox.showinfo("Info", "Generate features first")
            return
        created = [jira.create_issue(f) for f in self.generated]
        keys = ", ".join(x["key"] for x in created)
        messagebox.showinfo("JIRA", f"Created: {keys}")

class FeatureFromJiraPage(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.prompts = load_prompts()
        ttk.Label(self, text="JQL").grid(row=0, column=0, sticky="w", padx=8)
        self.jql = ttk.Entry(self)
        self.jql.grid(row=0, column=1, sticky="ew", padx=8)
        fetch = ttk.Button(self, text="Fetch", command=self.fetch)
        fetch.grid(row=0, column=2, sticky="w")
        gen = ttk.Button(self, text="Generate Feature", command=self.generate)
        gen.grid(row=0, column=3, sticky="w", padx=8)
        create = ttk.Button(self, text="Create JIRA", command=self.create_jira)
        create.grid(row=0, column=4, sticky="w")
        self.src = ttk.Treeview(self, columns=("Key","Summary"), show="headings", selectmode="extended")
        for c in ("Key","Summary"):
            self.src.heading(c, text=c)
            self.src.column(c, width=180, anchor="w")
        self.src.grid(row=1, column=0, columnspan=5, sticky="nsew", padx=8, pady=8)
        cols = ("Title","Summary","T-Shirt Size","Business Value","Priority","Issue_type")
        self.out = ttk.Treeview(self, columns=cols, show="headings")
        for c in cols:
            self.out.heading(c, text=c)
            self.out.column(c, width=160, anchor="w")
        self.out.grid(row=2, column=0, columnspan=5, sticky="nsew", padx=8, pady=8)
        self.rowconfigure(1, weight=1)
        self.rowconfigure(2, weight=1)
        self.columnconfigure(1, weight=1)
        self.generated = []

    def fetch(self):
        rows = jira.search(self.jql.get())
        for i in self.src.get_children():
            self.src.delete(i)
        for r in rows:
            self.src.insert("", "end", values=(r.get("key",""), r.get("summary","")))

    def generate(self):
        sel = self.src.selection()
        feats = []
        for iid in sel:
            s = self.src.item(iid, "values")[1]
            feats.extend(request_features(s, self.prompts.get("feature_creation_request", self.prompts.get("feature_prompt", ""))))
        self.generated = feats
        for i in self.out.get_children():
            self.out.delete(i)
        for f in feats:
            self.out.insert("", "end", values=(f["Title"], f["Summary"], f["T-Shirt Size"], f["Business Value"], f["Priority"], f["Issue_type"]))

    def create_jira(self):
        if not self.generated:
            return
        created = [jira.create_issue(f) for f in self.generated]
        keys = ", ".join(x["key"] for x in created)
        messagebox.showinfo("JIRA", f"Created: {keys}")

class FeatureDorPage(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.prompts = load_prompts()
        ttk.Label(self, text="JQL").grid(row=0, column=0, sticky="w", padx=8)
        self.jql = ttk.Entry(self)
        self.jql.grid(row=0, column=1, sticky="ew", padx=8)
        fetch = ttk.Button(self, text="Fetch", command=self.fetch)
        fetch.grid(row=0, column=2, sticky="w")
        check = ttk.Button(self, text="Check DOR", command=self.check_dor)
        check.grid(row=0, column=3, sticky="w", padx=8)
        cols = ("Key","Summary","Score","Status","Reason")
        self.gridv = ttk.Treeview(self, columns=cols, show="headings", selectmode="extended")
        for c in cols:
            self.gridv.heading(c, text=c)
            w = 100 if c in ("Score","Status") else 200
            self.gridv.column(c, width=w, anchor="w")
        self.gridv.grid(row=1, column=0, columnspan=4, sticky="nsew", padx=8, pady=8)
        self.rowconfigure(1, weight=1)
        self.columnconfigure(1, weight=1)
        self.items = []

    def fetch(self):
        rows = jira.search(self.jql.get())
        self.items = rows
        for i in self.gridv.get_children():
            self.gridv.delete(i)
        for r in rows:
            self.gridv.insert("", "end", values=(r.get("key",""), r.get("summary",""), "", "", ""))

    def check_dor(self):
        for iid in self.gridv.get_children():
            vals = list(self.gridv.item(iid, "values"))
            summary = vals[1]
            score, status, reason = feature_dor.score(summary, self.prompts.get("feature_dor_prompt", ""))
            vals[2] = score
            vals[3] = status
            vals[4] = reason
            self.gridv.item(iid, values=tuple(vals))
