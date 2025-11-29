import tkinter as tk
from tkinter import ttk
from . import feature_pages, story_pages, sprint_pages, qbr_pages, meetings_page, config_pages, logout_page

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

def main():
    app = AgileTool()
    app.mainloop()
