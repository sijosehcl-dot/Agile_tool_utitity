import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import confluence

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

