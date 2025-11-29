import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import os
import csv
import re
from config import load_config, save_config
from prompt import load_prompts, save_prompts
from llm import feature_creation, feature_dor, story_creation, story_dor
import jira
import firestore
import confluence
from ui import feature_pages
from ui import story_pages
from ui import sprint_pages
from ui import qbr_pages
from ui import meetings_page
from ui import config_pages
from ui import logout_page

MENU = {
    "Feature creation": {
        "Create Feature": None,
        "Upload Excel": None,
        "From JIRA": None,
        "Check Feature DOR": None,
    },
    "Story Creation": {
        "Create Stories": None,
        "Check story DOR": None,
    },
    "Sprint Planning": {
        "Capacity Planning": None,
        "Velocity": None,
        "Allocate Stories": None,
        "Retrieve Plan": None,
    },
    "QBR Planning": {
        "QBR Capacity Plan": None,
        "Retrieve Plan": None,
    },
    "Meeting": {
        "Upload Transcripts": None,
    },
    "Configuration": {
        "JIRA Configuration": None,
        "LLM Configuration": None,
        "Confluence Configuration": None,
        "Prompts": {
            "Feature creation": None,
            "Story Creation": None,
            "Feature DOR": None,
            "Story DOR": None,
        },
    },
    "Logout": None,
}

class AgileTool(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Agile Tool")
        self.geometry("1000x700")
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)
        self.status_var = tk.StringVar(value="Ready")
        self.tree = ttk.Treeview(self, show="tree")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.content = ttk.Frame(self)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.status = ttk.Label(self, textvariable=self.status_var, anchor="w")
        self.status.grid(row=1, column=0, columnspan=2, sticky="ew")
        self._pages = {}
        self._populate_tree()
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

    def _populate_tree(self):
        for main, children in MENU.items():
            node = self.tree.insert("", "end", text=main, open=False)
            self._add_children(node, children)

    def _add_children(self, parent, children):
        if children is None:
            return
        if isinstance(children, dict):
            for name, nested in children.items():
                node = self.tree.insert(parent, "end", text=name, open=False)
                self._add_children(node, nested)

    def _on_select(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        item = sel[0]
        parent = self.tree.parent(item)
        if parent == "":
            self._expand_only(item)
            self.status_var.set(f"Opened: {self.tree.item(item, 'text')}")
        else:
            path = self._item_path(item)
            self.status_var.set(f"Selected: {' > '.join(path)}")
            self._open_page(path)

    def _expand_only(self, item):
        for top in self.tree.get_children(""):
            if top == item:
                self.tree.item(top, open=True)
            else:
                self.tree.item(top, open=False)

    def _item_path(self, item):
        names = []
        cur = item
        while cur:
            names.append(self.tree.item(cur, "text"))
            cur = self.tree.parent(cur)
        names.reverse()
        return names

    def _open_page(self, path):
        key = " / ".join(path)
        for child in self.content.winfo_children():
            child.grid_remove()
        if key not in self._pages:
            self._pages[key] = self._create_page(path)
        page = self._pages[key]
        page.grid(row=0, column=0, sticky="nsew")
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)

    def _create_page(self, path):
        if path == ["Feature creation", "Create Feature"]:
            return feature_pages.FeatureCreatePage(self.content)
        if path == ["Feature creation", "Upload Excel"]:
            return feature_pages.FeatureUploadPage(self.content)
        if path == ["Feature creation", "From JIRA"]:
            return feature_pages.FeatureFromJiraPage(self.content)
        if path == ["Feature creation", "Check Feature DOR"]:
            return feature_pages.FeatureDorPage(self.content)
        if path == ["Story Creation", "Create Stories"]:
            return story_pages.StoryCreatePage(self.content)
        if path == ["Story Creation", "Check story DOR"]:
            return story_pages.StoryDorPage(self.content)
        if path == ["Sprint Planning", "Capacity Planning"]:
            return sprint_pages.SprintCapacityPage(self.content)
        if path == ["Sprint Planning", "Retrieve Plan"]:
            return sprint_pages.SprintRetrievePage(self.content)
        if path == ["QBR Planning", "QBR Capacity Plan"]:
            return qbr_pages.QbrCapacityPage(self.content)
        if path == ["QBR Planning", "Retrieve Plan"]:
            return qbr_pages.QbrRetrievePage(self.content)
        if path == ["Meeting", "Upload Transcripts"]:
            return meetings_page.MeetingUploadPage(self.content)
        if path == ["Configuration", "JIRA Configuration"]:
            return config_pages.JiraConfigPage(self.content)
        if path == ["Configuration", "LLM Configuration"]:
            return config_pages.LlmConfigPage(self.content)
        if path == ["Configuration", "Confluence Configuration"]:
            return config_pages.ConfluenceConfigPage(self.content)
        if path == ["Configuration", "Prompts", "Feature creation"]:
            return config_pages.PromptsPage(self.content, "feature_prompt")
        if path == ["Configuration", "Prompts", "Story Creation"]:
            return config_pages.PromptsPage(self.content, "story_prompt")
        if path == ["Configuration", "Prompts", "Feature DOR"]:
            return config_pages.PromptsPage(self.content, "feature_dor_prompt")
        if path == ["Configuration", "Prompts", "Story DOR"]:
            return config_pages.PromptsPage(self.content, "story_dor_prompt")
        if path == ["Logout"]:
            return logout_page.LogoutPage(self.content, self)
        frame = ttk.Frame(self.content)
        ttk.Label(frame, text="Not implemented").pack(anchor="center")
        return frame

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
        feats = feature_creation.split_features(text, self.prompts)
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
            feats.extend(feature_creation.split_features(req, self.prompts))
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
            feats.extend(feature_creation.generate_features(s, self.prompts))
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

class StoryCreatePage(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.prompts = load_prompts()
        ttk.Label(self, text="JQL").grid(row=0, column=0, sticky="w", padx=8)
        self.jql = ttk.Entry(self)
        self.jql.grid(row=0, column=1, sticky="ew", padx=8)
        fetch = ttk.Button(self, text="Fetch Features", command=self.fetch)
        fetch.grid(row=0, column=2, sticky="w")
        gen = ttk.Button(self, text="Generate Stories", command=self.generate)
        gen.grid(row=0, column=3, sticky="w", padx=8)
        create = ttk.Button(self, text="Create JIRA", command=self.create_jira)
        create.grid(row=0, column=4, sticky="w")
        self.src = ttk.Treeview(self, columns=("Key","Summary"), show="headings", selectmode="extended")
        for c in ("Key","Summary"):
            self.src.heading(c, text=c)
            self.src.column(c, width=180, anchor="w")
        self.src.grid(row=1, column=0, columnspan=5, sticky="nsew", padx=8, pady=8)
        cols = ("Title","Summary","Story Point","Priority","Issue_type","Tasks")
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
        stories = []
        for iid in sel:
            s = self.src.item(iid, "values")[1]
            stories.extend(story_creation.generate_stories(s, load_prompts()))
        self.generated = stories
        for i in self.out.get_children():
            self.out.delete(i)
        for st in stories:
            self.out.insert("", "end", values=(st["Title"], st["Summary"], st["Story Point"], st["Priority"], st["Issue_type"], "; ".join([f"{t['name']}:{t['hours']}h" for t in st["Tasks"]])))

    def create_jira(self):
        if not self.generated:
            return
        created = [jira.create_issue(s) for s in self.generated]
        keys = ", ".join(x["key"] for x in created)
        messagebox.showinfo("JIRA", f"Created: {keys}")

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

class StoryDorPage(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        ttk.Label(self, text="JQL").grid(row=0, column=0, sticky="w", padx=8)
        self.jql = ttk.Entry(self)
        self.jql.grid(row=0, column=1, sticky="ew", padx=8)
        fetch = ttk.Button(self, text="Fetch", command=self.fetch)
        fetch.grid(row=0, column=2, sticky="w")
        check = ttk.Button(self, text="Check DOR", command=self.check_dor)
        check.grid(row=0, column=3, sticky="w", padx=8)
        cols = ("Key","Summary","Score","Status","Reason")
        self.gridv = ttk.Treeview(self, columns=cols, show="headings")
        for c in cols:
            self.gridv.heading(c, text=c)
            w = 100 if c in ("Score","Status") else 200
            self.gridv.column(c, width=w, anchor="w")
        self.gridv.grid(row=1, column=0, columnspan=4, sticky="nsew", padx=8, pady=8)
        self.rowconfigure(1, weight=1)
        self.columnconfigure(1, weight=1)

    def fetch(self):
        rows = jira.search(self.jql.get())
        for i in self.gridv.get_children():
            self.gridv.delete(i)
        for r in rows:
            self.gridv.insert("", "end", values=(r.get("key",""), r.get("summary",""), "", "", ""))

    def check_dor(self):
        for iid in self.gridv.get_children():
            vals = list(self.gridv.item(iid, "values"))
            summary = vals[1]
            score = min(100, max(1, len(re.findall(r"\w+", summary)) // 3))
            status = "Pass" if score >= 85 else "Fail"
            reason = "Content length and structure assessed"
            vals[2] = score
            vals[3] = status
            vals[4] = reason
            self.gridv.item(iid, values=tuple(vals))

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

class MeetingUploadPage(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        ttk.Label(self, text="Action").grid(row=0, column=0, sticky="w", padx=8)
        self.action = ttk.Combobox(self, values=["RET","MOM","ST"])
        self.action.grid(row=0, column=1, sticky="w", padx=8)
        up = ttk.Button(self, text="Upload Transcript", command=self._upload)
        up.grid(row=0, column=2, sticky="w", padx=8)
        pub = ttk.Button(self, text="Publish to Confluence", command=self._publish)
        pub.grid(row=0, column=3, sticky="w", padx=8)
        self.text = tk.Text(self, wrap="word")
        self.text.grid(row=1, column=0, columnspan=4, sticky="nsew", padx=8, pady=8)
        self.rowconfigure(1, weight=1)

    def _upload(self):
        path = filedialog.askopenfilename()
        if not path:
            return
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            self.text.delete("1.0", "end")
            self.text.insert("1.0", f.read())

    def _publish(self):
        act = self.action.get() or "RET"
        resp = confluence.publish_transcript(act, self.text.get("1.0", "end"))
        messagebox.showinfo("Confluence", json.dumps(resp))

class JiraConfigPage(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.cfg = load_config()
        self.url = ttk.Entry(self)
        self.user = ttk.Entry(self)
        self.token = ttk.Entry(self, show="*")
        ttk.Label(self, text="URL").grid(row=0, column=0, sticky="w", padx=8)
        self.url.grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Label(self, text="User").grid(row=1, column=0, sticky="w", padx=8)
        self.user.grid(row=1, column=1, sticky="ew", padx=8)
        ttk.Label(self, text="Token").grid(row=2, column=0, sticky="w", padx=8)
        self.token.grid(row=2, column=1, sticky="ew", padx=8)
        save = ttk.Button(self, text="Save", command=self._save)
        save.grid(row=3, column=1, sticky="e", padx=8)
        self._load()

    def _load(self):
        j = self.cfg.get("jira", {})
        self.url.insert(0, j.get("url", ""))
        self.user.insert(0, j.get("user", ""))
        self.token.insert(0, j.get("token", ""))

    def _save(self):
        self.cfg["jira"] = {"url": self.url.get(), "user": self.user.get(), "token": self.token.get()}
        save_config(self.cfg)
        messagebox.showinfo("Saved", "JIRA config saved")

class LlmConfigPage(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.cfg = load_config()
        self.api = ttk.Entry(self)
        self.model = ttk.Entry(self)
        ttk.Label(self, text="API Key").grid(row=0, column=0, sticky="w", padx=8)
        self.api.grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Label(self, text="Model").grid(row=1, column=0, sticky="w", padx=8)
        self.model.grid(row=1, column=1, sticky="ew", padx=8)
        save = ttk.Button(self, text="Save", command=self._save)
        save.grid(row=2, column=1, sticky="e", padx=8)
        j = self.cfg.get("llm", {})
        self.api.insert(0, j.get("api_key", ""))
        self.model.insert(0, j.get("model", ""))

    def _save(self):
        self.cfg["llm"] = {"api_key": self.api.get(), "model": self.model.get()}
        save_config(self.cfg)
        messagebox.showinfo("Saved", "LLM config saved")

class ConfluenceConfigPage(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.cfg = load_config()
        self.url = ttk.Entry(self)
        self.space = ttk.Entry(self)
        self.page = ttk.Entry(self)
        ttk.Label(self, text="URL").grid(row=0, column=0, sticky="w", padx=8)
        self.url.grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Label(self, text="Space").grid(row=1, column=0, sticky="w", padx=8)
        self.space.grid(row=1, column=1, sticky="ew", padx=8)
        ttk.Label(self, text="Page").grid(row=2, column=0, sticky="w", padx=8)
        self.page.grid(row=2, column=1, sticky="ew", padx=8)
        save = ttk.Button(self, text="Save", command=self._save)
        save.grid(row=3, column=1, sticky="e", padx=8)
        j = self.cfg.get("confluence", {})
        self.url.insert(0, j.get("url", ""))
        self.space.insert(0, j.get("space", ""))
        self.page.insert(0, j.get("page", ""))

    def _save(self):
        self.cfg["confluence"] = {"url": self.url.get(), "space": self.space.get(), "page": self.page.get()}
        save_config(self.cfg)
        messagebox.showinfo("Saved", "Confluence config saved")

class PromptsPage(ttk.Frame):
    def __init__(self, master, key):
        super().__init__(master)
        self.key = key
        self.prompts = load_prompts()
        self.text = tk.Text(self, wrap="word", height=10)
        self.text.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=8, pady=8)
        self.text.insert("1.0", self.prompts.get(key, ""))
        save = ttk.Button(self, text="Save", command=self._save)
        save.grid(row=1, column=1, sticky="e", padx=8)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

    def _save(self):
        self.prompts[self.key] = self.text.get("1.0", "end")
        save_prompts(self.prompts)
        messagebox.showinfo("Saved", "Prompt saved")

class LogoutPage(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        btn = ttk.Button(self, text="Logout", command=self._logout)
        btn.pack(padx=12, pady=12)

    def _logout(self):
        self.app._pages.clear()
        self.app.destroy()

def main():
    app = AgileTool()
    app.mainloop()

if __name__ == "__main__":
    main()
