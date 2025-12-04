from tkinter import ttk

class LogoutPage(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        btn = ttk.Button(self, text="Logout", command=self._logout)
        btn.pack(padx=12, pady=12)

    def _logout(self):
        self.app._pages.clear()
        self.app.destroy()

