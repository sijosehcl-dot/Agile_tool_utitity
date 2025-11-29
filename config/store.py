import os
import json

def _path(name):
    return os.path.join(os.path.dirname(__file__), name)

def load_config():
    path = _path("config.json")
    data = {
        "jira": {"url": "", "user": "", "token": "", "project": ""},
        "llm": {"api_key": "", "model": ""},
        "confluence": {"url": "", "space": "", "page": ""},
    }
    try:
        with open(path, "r") as f:
            data.update(json.load(f))
    except Exception:
        pass
    return data

def save_config(cfg):
    path = _path("config.json")
    with open(path, "w") as f:
        json.dump(cfg, f)

 
