import tkinter as tk
from tkinter import ttk, messagebox
from prompt import load_prompts
from llm import story_creation, story_dor
import jira

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
            score, status, reason = story_dor.score(summary, load_prompts().get("story_dor_prompt", ""))
            vals[2] = score
            vals[3] = status
            vals[4] = reason
            self.gridv.item(iid, values=tuple(vals))
