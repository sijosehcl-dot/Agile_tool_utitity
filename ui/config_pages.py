import tkinter as tk
from tkinter import ttk, messagebox
from config import load_config, save_config
from prompt import load_prompts, save_prompts

class JiraConfigPage(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.cfg = load_config()
        self.url = ttk.Entry(self)
        self.user = ttk.Entry(self)
        self.token = ttk.Entry(self, show="*")
        self.project = ttk.Entry(self)
        ttk.Label(self, text="URL").grid(row=0, column=0, sticky="w", padx=8)
        self.url.grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Label(self, text="User").grid(row=1, column=0, sticky="w", padx=8)
        self.user.grid(row=1, column=1, sticky="ew", padx=8)
        ttk.Label(self, text="Token").grid(row=2, column=0, sticky="w", padx=8)
        self.token.grid(row=2, column=1, sticky="ew", padx=8)
        ttk.Label(self, text="Project Key").grid(row=3, column=0, sticky="w", padx=8)
        self.project.grid(row=3, column=1, sticky="ew", padx=8)
        save = ttk.Button(self, text="Save", command=self._save)
        save.grid(row=4, column=1, sticky="e", padx=8)
        self._load()

    def _load(self):
        j = self.cfg.get("jira", {})
        self.url.insert(0, j.get("url", ""))
        self.user.insert(0, j.get("user", ""))
        self.token.insert(0, j.get("token", ""))
        self.project.insert(0, j.get("project", ""))

    def _save(self):
        cur = self.cfg.get("jira", {})
        cur.update({"url": self.url.get(), "user": self.user.get(), "token": self.token.get(), "project": self.project.get()})
        self.cfg["jira"] = cur
        try:
            save_config(self.cfg)
            messagebox.showinfo("Saved", "JIRA config saved")
        except Exception:
            messagebox.showerror("Error", "Failed to save JIRA configuration")

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
        cur = self.cfg.get("llm", {})
        cur.update({"api_key": self.api.get(), "model": self.model.get()})
        self.cfg["llm"] = cur
        try:
            save_config(self.cfg)
            messagebox.showinfo("Saved", "LLM config saved")
        except Exception:
            messagebox.showerror("Error", "Failed to save LLM configuration")

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
        cur = self.cfg.get("confluence", {})
        cur.update({"url": self.url.get(), "space": self.space.get(), "page": self.page.get()})
        self.cfg["confluence"] = cur
        try:
            save_config(self.cfg)
            messagebox.showinfo("Saved", "Confluence config saved")
        except Exception:
            messagebox.showerror("Error", "Failed to save Confluence configuration")

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
