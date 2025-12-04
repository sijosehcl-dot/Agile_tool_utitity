import json
import re
import ssl as _ssl
from urllib import request as _req
from urllib.error import HTTPError, URLError

def _normalize(items):
    res = []
    for f in items or []:
        res.append({
            "Title": f.get("Title", f.get("title", "Feature")),
            "Summary": f.get("Summary", f.get("description", "")),
            "Acceptance Criteria": f.get("Acceptance Criteria", f.get("acceptance", f.get("acceptance_criteria", []))),
            "Benefit Hypothesis": f.get("Benefit Hypothesis", f.get("benefit", f.get("benefit_hypothesis", ""))),
            "T-Shirt Size": f.get("T-Shirt Size", f.get("size", "M")),
            "Priority": f.get("Priority", f.get("priority", "Medium")),
            "Business Value": f.get("Business Value", f.get("businessValue", f.get("business_value", 5))),
            "Issue_type": f.get("Issue_type", f.get("issue_type", f.get("work_type", "Feature"))),
            "duedate": f.get("duedate", f.get("due_date", "")),
        })
    return res

def _strip_code_fences(text):
    s = text.strip()
    s = re.sub(r"^```(?:json)?", "", s)
    s = re.sub(r"```$", "", s)
    return s.strip()

def request_features(requirement_text, prompt_text, config=None):
    if not (prompt_text or "").strip():
        raise ValueError("no_prompt")
    cfg = config or {}
    llm = cfg.get("llm", {})
    api_key = llm.get("api_key", "").strip()
    model = llm.get("model", "").strip()
    if not api_key or not model:
        raise ValueError("llm_not_configured")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": f"{prompt_text}\n\nRequirement:\n{requirement_text}\n\nReturn ONLY a JSON array of Feature objects using the schema from the prompt. Do not include any prose or markdown; respond with pure JSON."
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    data = json.dumps(payload).encode("utf-8")
    req = _req.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        ctx = None
        try:
            import certifi
            ctx = _ssl.create_default_context(cafile=certifi.where())
        except Exception:
            ctx = None
        if ctx is not None:
            resp = _req.urlopen(req, timeout=60, context=ctx)
        else:
            resp = _req.urlopen(req, timeout=60)
        try:
            raw = resp.read().decode("utf-8")
            obj = json.loads(raw)
        finally:
            try:
                resp.close()
            except Exception:
                pass
    except HTTPError as e:
        try:
            msg = e.read().decode("utf-8")
        except Exception:
            msg = str(e)
        raise RuntimeError(f"llm_http_error:{msg}")
    except URLError as e:
        try:
            if isinstance(e.reason, _ssl.SSLError):
                raise RuntimeError("llm_cert_missing:TLS certificate bundle not found. Install 'certifi' or system CA certificates.")
        except Exception:
            pass
        raise RuntimeError(f"llm_network_error:{e.reason}")
    except _ssl.SSLError as e:
        raise RuntimeError("llm_cert_missing:TLS certificate bundle not found. Install 'certifi' or system CA certificates.")
    candidates = obj.get("candidates", [])
    text = ""
    if candidates:
        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if parts:
            text = parts[0].get("text", "")
    if not text:
        raise RuntimeError("llm_empty_output")
    cleaned = _strip_code_fences(text)
    try:
        arr = json.loads(cleaned)
    except Exception:
        raise RuntimeError("llm_invalid_json")
    if isinstance(arr, dict) and "features" in arr:
        arr = arr.get("features", [])
    if not isinstance(arr, list):
        raise RuntimeError("llm_json_not_array")
    # ensure due date exists on each item
    import datetime as _dt
    def _infer_due(requirement):
        m = re.search(r"(20\d{2})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])", requirement)
        if m:
            return m.group(0)
        return (_dt.date.today() + _dt.timedelta(days=14)).isoformat()
    for it in arr:
        if not it.get("due_date") and not it.get("duedate"):
            it["due_date"] = _infer_due(requirement_text)
    return _normalize(arr)

def _normalize_stories(items):
    res = []
    for st in items or []:
        tasks = (
            st.get("Tasks")
            or st.get("tasks")
            or st.get("Subtasks")
            or st.get("subtasks")
            or st.get("sub_tasks")
            or st.get("SubTasks")
            or []
        )
        if isinstance(tasks, dict):
            conv = []
            for k, v in tasks.items():
                hrs = v
                try:
                    hrs = int(hrs)
                except Exception:
                    hrs = 4
                conv.append({"name": str(k), "hours": max(1, min(16, hrs))})
            tasks = conv
        elif isinstance(tasks, str):
            parts = [p.strip() for p in re.split(r"[\n,;•\-]+", tasks) if p.strip()]
            tasks = [{"name": p, "hours": 4} for p in parts][:8]
        elif isinstance(tasks, list):
            norm = []
            for t in tasks:
                if isinstance(t, str):
                    norm.append({"name": t.strip(), "hours": 4})
                elif isinstance(t, dict):
                    name = (
                        t.get("name")
                        or t.get("title")
                        or t.get("task")
                        or t.get("summary")
                        or "Task"
                    )
                    hrs = t.get("hours") or t.get("estimate") or t.get("time") or 4
                    try:
                        hrs = int(hrs)
                    except Exception:
                        hrs = 4
                    norm.append({"name": str(name), "hours": max(1, min(16, hrs))})
            tasks = norm
        ac_val = (
            st.get("Acceptance Criteria")
            or st.get("acceptance")
            or st.get("acceptance_criteria")
            or st.get("AcceptanceCriteria")
            or st.get("criteria")
            or st.get("Criteria")
            or st.get("AC")
            or st.get("ac")
        )
        if ac_val is None:
            for k, v in (st.items() if isinstance(st, dict) else []):
                kl = str(k).lower()
                if "acceptance" in kl or "criteria" in kl:
                    ac_val = v
                    break
        ac_list = []
        if isinstance(ac_val, str):
            ac_list = [p.strip() for p in re.split(r"[\n,;•\-]+", ac_val) if p.strip()]
        elif isinstance(ac_val, list):
            for it in ac_val:
                if isinstance(it, str):
                    t = it.strip()
                    if t:
                        ac_list.append(t)
                elif isinstance(it, dict):
                    t = it.get("text") or it.get("value") or it.get("name") or it.get("summary") or ""
                    t = str(t).strip()
                    if t:
                        ac_list.append(t)
        elif isinstance(ac_val, dict):
            for k, v in ac_val.items():
                t = v if v is not None else k
                t = str(t).strip()
                if t:
                    ac_list.append(t)
        if not ac_list:
            summary = st.get("Summary") or st.get("description") or ""
            s = str(summary).strip()
            if s:
                parts = [p.strip() for p in re.split(r"[\n.]+", s) if p.strip()]
                if parts:
                    ac_list = [f"Given {parts[0][:40]} When implemented Then verified"]
        res.append({
            "Title": st.get("Title", st.get("title", "Story")),
            "Summary": st.get("Summary", st.get("description", "")),
            "Acceptance Criteria": ac_list,
            "Story Point": st.get("Story Point", st.get("story_points", st.get("points", 3))),
            "Priority": st.get("Priority", st.get("priority", "Medium")),
            "Issue_type": st.get("Issue_type", st.get("issue_type", "story")),
            "Tasks": tasks if isinstance(tasks, list) else [],
        })
    return res

def request_stories(feature_text, prompt_text, config=None):
    if not (prompt_text or "").strip():
        raise ValueError("no_prompt")
    cfg = config or {}
    llm = cfg.get("llm", {})
    api_key = llm.get("api_key", "").strip()
    model = llm.get("model", "").strip()
    if not api_key or not model:
        raise ValueError("llm_not_configured")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    schema = (
        "You MUST return Story objects with these fields: "
        "Title (string), Summary (string), Acceptance Criteria (array of strings), "
        "Story Point (integer), Priority (Critical/High/Medium/Low), Issue_type=story, "
        "Tasks (array of objects). Each Task must be an actionable developer instruction with fields: "
        "name (short imperative like 'Implement login endpoint') and hours (integer 1-16). "
        "Include 4-8 tasks that together accomplish the story."
    )
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": f"{prompt_text}\n\n{schema}\n\nFeature:\n{feature_text}\n\nReturn ONLY a JSON array of Story objects using the schema above. Do not include any prose or markdown; respond with pure JSON."
                    }
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    data = json.dumps(payload).encode("utf-8")
    req = _req.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        ctx = None
        try:
            import certifi
            ctx = _ssl.create_default_context(cafile=certifi.where())
        except Exception:
            ctx = None
        if ctx is not None:
            resp = _req.urlopen(req, timeout=60, context=ctx)
        else:
            resp = _req.urlopen(req, timeout=60)
        try:
            raw = resp.read().decode("utf-8")
            obj = json.loads(raw)
        finally:
            try:
                resp.close()
            except Exception:
                pass
    except HTTPError as e:
        try:
            msg = e.read().decode("utf-8")
        except Exception:
            msg = str(e)
        raise RuntimeError(f"llm_http_error:{msg}")
    except URLError as e:
        try:
            if isinstance(e.reason, _ssl.SSLError):
                raise RuntimeError("llm_cert_missing:TLS certificate bundle not found. Install 'certifi' or system CA certificates.")
        except Exception:
            pass
        raise RuntimeError(f"llm_network_error:{e.reason}")
    except _ssl.SSLError as e:
        raise RuntimeError("llm_cert_missing:TLS certificate bundle not found. Install 'certifi' or system CA certificates.")
    candidates = obj.get("candidates", [])
    text = ""
    if candidates:
        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if parts:
            text = parts[0].get("text", "")
    if not text:
        raise RuntimeError("llm_empty_output")
    cleaned = _strip_code_fences(text)
    try:
        arr = json.loads(cleaned)
    except Exception:
        raise RuntimeError("llm_invalid_json")
    if isinstance(arr, dict) and "stories" in arr:
        arr = arr.get("stories", [])
    if not isinstance(arr, list):
        raise RuntimeError("llm_json_not_array")
    return _normalize_stories(arr)
