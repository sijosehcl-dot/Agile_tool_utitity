import os
import json

def _dir():
    return os.path.join(os.path.dirname(__file__), "data")

def _ensure():
    d = _dir()
    if not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)

def _path(name):
    _ensure()
    return os.path.join(_dir(), name)

def _load(name):
    p = _path(name)
    try:
        with open(p, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def _save(name, data):
    p = _path(name)
    with open(p, "w") as f:
        json.dump(data, f)

def save_sprint_capacity(record):
    data = _load("sprint_capacity.json")
    data[record["sprint_name"]] = record
    _save("sprint_capacity.json", data)

def get_sprint_names():
    data = _load("sprint_capacity.json")
    return sorted(list(data.keys()))

def get_sprint_capacity(name):
    data = _load("sprint_capacity.json")
    return data.get(name, {})

def save_qbr_capacity(record):
    data = _load("qbr_capacity.json")
    data[record["qbr_name"]] = record
    _save("qbr_capacity.json", data)

def get_qbr_names():
    data = _load("qbr_capacity.json")
    return sorted(list(data.keys()))

def get_qbr_capacity(name):
    data = _load("qbr_capacity.json")
    return data.get(name, {})

def save_sprint_allocation(sprint_name, keys):
    data = _load("sprint_allocations.json")
    existing = data.get(sprint_name, {}).get("story_keys", [])
    merged = sorted(set([str(k) for k in existing] + [str(k) for k in (keys or []) if k]))
    data[sprint_name] = {"story_keys": merged}
    _save("sprint_allocations.json", data)
