import json
import re
import base64
import ssl as _ssl
import logging
import os
from urllib import request as _req
from urllib.error import HTTPError, URLError

def _load_config():
    try:
        from config import load_config
        return load_config()
    except Exception:
        return {}

def _load_mapping():
    import os
    path = os.path.join(os.path.dirname(__file__), "mapping.json")
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return {"issue_types": {}, "fields": {}}

_jira_logger = logging.getLogger("jira")
if not _jira_logger.handlers:
    try:
        os.makedirs(os.path.join(os.path.dirname(__file__), "..", "logs"), exist_ok=True)
        fh = logging.FileHandler(os.path.join(os.path.dirname(__file__), "..", "logs", "jira.log"))
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        fh.setFormatter(fmt)
        _jira_logger.addHandler(fh)
        _jira_logger.setLevel(logging.INFO)
    except Exception:
        pass

def _auth_header(user, token):
    raw = f"{user}:{token}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")

def _get_project_key(base_url, auth):
    url = base_url.rstrip("/") + "/rest/api/3/project/search"
    req = _req.Request(url, headers={"Authorization": auth, "Accept": "application/json"}, method="GET")
    try:
        resp = _urlopen(req, timeout=30)
        try:
            data = json.loads(resp.read().decode("utf-8"))
        finally:
            try:
                resp.close()
            except Exception:
                pass
        values = data.get("values", [])
        if values:
            return values[0].get("key", None)
    except Exception:
        pass
    return None

def _map_fields(issue, mapping):
    fields_map = mapping.get("fields", {})
    out = {}
    def _adf_text(t):
        return {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": t or ""}]}]}
    def _adf_bullets(items):
        arr = []
        for it in items:
            if not it:
                continue
            arr.append({"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": str(it)}]}]})
        if not arr:
            return _adf_text("")
        return {"type": "doc", "version": 1, "content": [{"type": "bulletList", "content": arr}]}
    tval = issue.get("title") or issue.get("Title")
    sval = issue.get("summary") or issue.get("Summary")
    raw_type = (issue.get("Issue_type") or issue.get("issue_type") or "").strip().lower()
    is_story = ("story" in raw_type) or (issue.get("Story Point") is not None)
    default_title = "Story" if is_story else "Feature"
    out[fields_map.get("summary", "summary")] = tval or sval or default_title
    desc = issue.get("description") or issue.get("Summary") or ""
    out[fields_map.get("description", "description")] = _adf_text(desc)
    prio_raw = issue.get("priority") or issue.get("Priority")
    if prio_raw is not None:
        prio_name = None
        if isinstance(prio_raw, dict):
            prio_name = prio_raw.get("name") or prio_raw.get("value") or prio_raw.get("id")
        elif isinstance(prio_raw, (list, tuple)):
            prio_name = prio_raw[0] if prio_raw else None
        else:
            prio_name = prio_raw
        if prio_name is not None:
            prio_name = str(prio_name).strip()
            if prio_name:
                out[fields_map.get("priority", "priority")] = {"name": prio_name}
    if issue.get("businessValue") is not None:
        out[fields_map.get("business_value", "customfield_10115")] = issue.get("businessValue")
    ac = issue.get("acceptance") or issue.get("Acceptance Criteria")
    if ac:
        items = ac if isinstance(ac, list) else [x.strip() for x in str(ac).splitlines() if x.strip()]
        out[fields_map.get("Acceptance Criteria", "customfield_10041")] = _adf_bullets(items)
    bh = issue.get("benefit") or issue.get("Benefit Hypothesis")
    if bh:
        out[fields_map.get("Benefit Hypothesis", "customfield_10043")] = bh
    # size handled separately to ensure valid option id
    # work_type handled in create_issue to resolve select option id
    due = issue.get("duedate") or issue.get("dueDate") or issue.get("due_date")
    if due:
        out[fields_map.get("duedate", "duedate")] = due
    # story points if present
    if issue.get("Story Point") is not None:
        out[fields_map.get("story_points", "customfield_10016")] = issue.get("Story Point")
    return out

def _get_select_options(base_url, auth, field_id):
    def _fetch(url):
        req = _req.Request(url, headers={"Authorization": auth, "Accept": "application/json"}, method="GET")
        resp = _urlopen(req, timeout=30)
        try:
            return json.loads(resp.read().decode("utf-8"))
        finally:
            try:
                resp.close()
            except Exception:
                pass
    try:
        # Try direct options endpoint
        base = base_url.rstrip("/")
        data = _fetch(base + f"/rest/api/3/field/{field_id}/option")
        for key in ("values", "options", "data", "results"):
            if isinstance(data.get(key), list):
                return data.get(key)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    try:
        # Fallback: retrieve contexts then options per context
        base = base_url.rstrip("/")
        ctx = _fetch(base + f"/rest/api/3/field/{field_id}/context")
        context_ids = []
        if isinstance(ctx, dict):
            for key in ("values", "contexts", "results"):
                items = ctx.get(key)
                if isinstance(items, list):
                    for it in items:
                        cid = it.get("id") or it.get("contextId")
                        if cid:
                            context_ids.append(cid)
        elif isinstance(ctx, list):
            for it in ctx:
                cid = it.get("id") or it.get("contextId")
                if cid:
                    context_ids.append(cid)
        options = []
        for cid in context_ids[:3]:
            try:
                opt = _fetch(base + f"/rest/api/3/field/{field_id}/context/{cid}/option")
                for key in ("values", "options", "results"):
                    if isinstance(opt.get(key), list):
                        options.extend(opt.get(key))
                if isinstance(opt, list):
                    options.extend(opt)
            except Exception:
                continue
        return options
    except Exception:
        return []
    return []

def _get_createmeta(base_url, auth, project_key, issue_type_name):
    url = (
        base_url.rstrip("/")
        + f"/rest/api/3/issue/createmeta?projectKeys={project_key}&issuetypeNames={_req.quote(issue_type_name)}&expand=projects.issuetypes.fields"
    )
    req = _req.Request(url, headers={"Authorization": auth, "Accept": "application/json"}, method="GET")
    resp = _urlopen(req, timeout=30)
    try:
        return json.loads(resp.read().decode("utf-8"))
    finally:
        try:
            resp.close()
        except Exception:
            pass

def _get_field_allowed_values(meta, field_id):
    try:
        projects = meta.get("projects", [])
        for p in projects:
            for it in p.get("issuetypes", []):
                fields = it.get("fields", {})
                f = None
                # fields by id or by key mapping
                if field_id in fields:
                    f = fields[field_id]
                else:
                    for k, v in fields.items():
                        if k.endswith(field_id):
                            f = v
                            break
                if f and isinstance(f.get("allowedValues"), list):
                    return f.get("allowedValues")
    except Exception:
        return []
    return []

def _adf_text_doc(t):
    return {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": t or ""}]}]}

def _adf_bullets_doc(items):
    arr = []
    for it in items or []:
        if not it:
            continue
        arr.append({"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": str(it)}]}]})
    if not arr:
        return _adf_text_doc("")
    return {"type": "doc", "version": 1, "content": [{"type": "bulletList", "content": arr}]}

def _match_size_option(size, options, mapping):
    synonyms = mapping.get("size_synonyms", {})
    default = {
        "XS": ["XS", "Extra Small", "X-Small"],
        "S": ["S", "Small"],
        "M": ["M", "Medium"],
        "L": ["L", "Large"],
        "XL": ["XL", "Extra Large", "X-Large"],
    }
    alias = synonyms.get(size, default.get(size, [size]))
    alower = [a.lower() for a in alias]
    for opt in options or []:
        name = (opt.get("name") or opt.get("value") or "").lower()
        if name in alower:
            return opt
        # partial startswith for common labels
        for a in alower:
            if name.startswith(a) or a in name:
                return opt
    return None

def _normalize_size_value(val):
    s = str(val or "").upper()
    s = s.replace(".", " ").replace(",", " ")
    tokens = [t for t in s.split() if t]
    for t in tokens:
        if t in ("XS", "S", "M", "L", "XL"):
            return t
    # full-word mappings
    joined = " ".join(tokens)
    if joined in ("EXTRA SMALL", "X SMALL", "X-SMALL"):
        return "XS"
    if joined == "SMALL":
        return "S"
    if joined == "MEDIUM":
        return "M"
    if joined == "LARGE":
        return "L"
    if joined in ("EXTRA LARGE", "X LARGE", "X-LARGE"):
        return "XL"
    for t in tokens:
        if t.startswith("X") and "L" in t:
            return "XL"
    return s.strip()

def _match_option(value, options, synonyms):
    alias = synonyms.get(value, [value])
    alower = [str(a).lower() for a in alias]
    for opt in options or []:
        name = (opt.get("name") or opt.get("value") or "").lower()
        if name in alower:
            return opt
        for a in alower:
            if name.startswith(a) or a in name:
                return opt
    return None

def create_issue(issue):
    cfg = _load_config()
    mapping = _load_mapping()
    jira_cfg = cfg.get("jira", {})
    itypes = mapping.get("issue_types", {})
    raw_type = issue.get("Issue_type") or issue.get("issue_type") or ""
    t = str(raw_type or "").strip().lower()
    if not t:
        if issue.get("Story Point") is not None:
            t = "story"
        else:
            t = "feature"
    if t in ("sub-task", "sub task", "subtask"):
        tnorm = "subtask"
    elif "story" in t:
        tnorm = "story"
    elif "feat" in t:
        tnorm = "feature"
    else:
        tnorm = t
    itype_in = tnorm
    itype_name = itypes.get(itype_in, itype_in.title())
    fields = _map_fields(issue, mapping)
    base_url = jira_cfg.get("url", "").strip()
    user = jira_cfg.get("user", "").strip()
    token = jira_cfg.get("token", "").strip()
    if not base_url or not user or not token:
        try:
            _jira_logger.info("CreateIssue MOCK type=%r fields=%r", itype_name, fields)
        except Exception:
            pass
        key = "JIRA-LOCAL"
        return {"key": key, "status": "mock"}
    auth = _auth_header(user, token)
    project_key = jira_cfg.get("project", "").strip() or _get_project_key(base_url, auth)
    if not project_key:
        raise RuntimeError("jira_project_missing")
    fields["project"] = {"key": project_key}
    fields["issuetype"] = {"name": itype_name}
    # resolve select options using CreateMeta preferred, then field options fallback
    # Priority: map provided value to allowed values (id/name), with synonyms
    try:
        pr_field_id = mapping.get("fields", {}).get("priority", "priority")
        pr_val_obj = fields.get(pr_field_id)
        pr_name_in = None
        if isinstance(pr_val_obj, dict):
            pr_name_in = pr_val_obj.get("name") or pr_val_obj.get("value") or pr_val_obj.get("id")
        elif pr_val_obj is not None:
            pr_name_in = pr_val_obj
        pr_name_in = str(pr_name_in or "").strip()
        if pr_name_in:
            meta = None
            try:
                meta = _get_createmeta(base_url, auth, project_key, itype_name)
            except Exception:
                meta = None
            options = _get_field_allowed_values(meta, pr_field_id) if meta else []
            # Common Jira priorities
            pr_syn = {
                "highest": ["highest", "critical", "urgent"],
                "high": ["high"],
                "medium": ["medium"],
                "low": ["low"],
                "lowest": ["lowest"]
            }
            def _match_priority(name, opts):
                n = str(name).strip().lower()
                for opt in opts or []:
                    nm = (opt.get("name") or opt.get("value") or "").strip().lower()
                    if nm == n:
                        return opt
                for key, syns in pr_syn.items():
                    if n == key or n in syns:
                        for opt in opts or []:
                            nm = (opt.get("name") or opt.get("value") or "").strip().lower()
                            if nm == key:
                                return opt
                return None
            match = _match_priority(pr_name_in, options)
            if match and match.get("id"):
                fields[pr_field_id] = {"id": match.get("id")}
            elif match and match.get("name"):
                fields[pr_field_id] = {"name": match.get("name")}
            else:
                # keep as name string to satisfy servers expecting string form
                fields[pr_field_id] = {"name": pr_name_in}
    except Exception:
        pass
    meta = None
    try:
        meta = _get_createmeta(base_url, auth, project_key, itype_name)
    except Exception:
        meta = None
    # resolve size select option id
    size_val = issue.get("size") or issue.get("T-Shirt Size")
    if size_val:
        field_id = mapping.get("fields", {}).get("Size", "customfield_10114")
        options = _get_field_allowed_values(meta, field_id) if meta else []
        if not options:
            options = _get_select_options(base_url, auth, field_id)
        norm = _normalize_size_value(size_val)
        match = _match_size_option(norm, options, mapping)
        if match and match.get("id"):
            fields[field_id] = {"id": match.get("id")}
        else:
            # try strict name equality fallback
            for opt in options or []:
                nm = opt.get("name") or opt.get("value")
                if nm and str(nm).strip().lower() == str(norm).strip().lower():
                    if opt.get("id"):
                        fields[field_id] = {"id": opt.get("id")}
                    break
    # resolve work_type select option id
    wt_val = issue.get("work_type") or issue.get("Issue_type") or issue.get("issue_type")
    if wt_val:
        wt_field_id = mapping.get("fields", {}).get("work_type", "customfield_10112")
        wt_options = _get_field_allowed_values(meta, wt_field_id) if meta else []
        if not wt_options:
            wt_options = _get_select_options(base_url, auth, wt_field_id)
        wt_syn = mapping.get("work_type_synonyms", {})
        wt_match = _match_option(str(wt_val).strip(), wt_options, wt_syn)
        if wt_match and wt_match.get("id"):
            fields[wt_field_id] = {"id": wt_match.get("id")}
        else:
            # strict equality fallback
            for opt in wt_options or []:
                nm = opt.get("name") or opt.get("value")
                if nm and str(nm).strip().lower() == str(wt_val).strip().lower():
                    if opt.get("id"):
                        fields[wt_field_id] = {"id": opt.get("id")}
                    break
    # Set Epic Link if creating a story and a feature key is provided
    try:
        raw_type = (issue.get("Issue_type") or issue.get("issue_type") or "").strip().lower()
        is_story = ("story" in raw_type) or (issue.get("Story Point") is not None)
        fkey = str((issue.get("Feature Key") or issue.get("feature_key") or "")).strip()
        if is_story and fkey:
            epic_field = mapping.get("fields", {}).get("epic_link", "customfield_10014")
            has_epic = False
            try:
                projects = meta.get("projects", []) if isinstance(meta, dict) else []
                for p in projects:
                    for it in p.get("issuetypes", []):
                        fields_meta = it.get("fields", {})
                        if epic_field in fields_meta:
                            has_epic = True
                            break
                        for k in fields_meta.keys():
                            if k.endswith(epic_field):
                                has_epic = True
                                break
                        if has_epic:
                            break
                    if has_epic:
                        break
            except Exception:
                has_epic = False
            if has_epic:
                fields[epic_field] = fkey
    except Exception:
        pass
    url = base_url.rstrip("/") + "/rest/api/3/issue"
    payload = json.dumps({"fields": fields}).encode("utf-8")
    try:
        _jira_logger.info("CreateIssue project=%r type=%r fields=%r", project_key, itype_name, fields)
    except Exception:
        pass
    req = _req.Request(url, data=payload, headers={
        "Authorization": auth,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }, method="POST")
    try:
        resp = _urlopen(req, timeout=30)
        try:
            data = json.loads(resp.read().decode("utf-8"))
        finally:
            try:
                resp.close()
            except Exception:
                pass
        new_key = data.get("key", "")
        fkey = str((issue.get("Feature Key") or issue.get("feature_key") or "")).strip()
        if new_key and fkey:
            try:
                link(new_key, fkey)
            except RuntimeError as le:
                raise
            except Exception as e:
                raise RuntimeError(f"jira_link_error:{e}")
        # create subtasks and add comment if tasks are provided and the issue is a story
        tasks = issue.get("Tasks") or issue.get("Subtasks") or []
        raw_type = (issue.get("Issue_type") or issue.get("issue_type") or "").strip().lower()
        is_story = ("story" in raw_type) or (issue.get("Story Point") is not None)
        if new_key and is_story and isinstance(tasks, list) and tasks:
            sub_keys = []
            try:
                sub_keys = create_subtasks(new_key, tasks)
            except Exception:
                sub_keys = []
            lines = []
            for i, t in enumerate(tasks):
                nm = (t.get("name") or t.get("title") or f"Task {i+1}")
                hrs = t.get("hours")
                sk = (sub_keys[i] if i < len(sub_keys) else "").strip()
                suffix = f" ({sk})" if sk else ""
                part = f"{nm}{suffix} — {hrs}h" if hrs is not None else f"{nm}{suffix}"
                lines.append(part)
            try:
                add_comment(new_key, lines)
            except Exception:
                pass
        return {"key": new_key, "status": "created"}
    except HTTPError as e:
        try:
            msg = e.read().decode("utf-8")
        except Exception:
            msg = str(e)
        try:
            epic_field = mapping.get("fields", {}).get("epic_link", "customfield_10014")
            if epic_field in msg:
                try:
                    if epic_field in fields:
                        del fields[epic_field]
                except Exception:
                    pass
                payload2 = json.dumps({"fields": fields}).encode("utf-8")
                req2 = _req.Request(url, data=payload2, headers={
                    "Authorization": auth,
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                }, method="POST")
                resp2 = _urlopen(req2, timeout=30)
                try:
                    data = json.loads(resp2.read().decode("utf-8"))
                finally:
                    try:
                        resp2.close()
                    except Exception:
                        pass
                new_key = data.get("key", "")
                fkey = str((issue.get("Feature Key") or issue.get("feature_key") or "")).strip()
                if new_key and fkey:
                    try:
                        link(new_key, fkey)
                    except RuntimeError as le:
                        raise
                    except Exception as e:
                        raise RuntimeError(f"jira_link_error:{e}")
                tasks = issue.get("Tasks") or issue.get("Subtasks") or []
                raw_type = (issue.get("Issue_type") or issue.get("issue_type") or "").strip().lower()
                is_story = ("story" in raw_type) or (issue.get("Story Point") is not None)
                if new_key and is_story and isinstance(tasks, list) and tasks:
                    sub_keys = []
                    try:
                        sub_keys = create_subtasks(new_key, tasks)
                    except Exception:
                        sub_keys = []
                    lines = []
                    for i, t in enumerate(tasks):
                        nm = (t.get("name") or t.get("title") or f"Task {i+1}")
                        hrs = t.get("hours")
                        sk = (sub_keys[i] if i < len(sub_keys) else "").strip()
                        suffix = f" ({sk})" if sk else ""
                        part = f"{nm}{suffix} — {hrs}h" if hrs is not None else f"{nm}{suffix}"
                        lines.append(part)
                    try:
                        add_comment(new_key, lines)
                    except Exception:
                        pass
                return {"key": new_key, "status": "created"}
        except Exception:
            pass
        raise RuntimeError(f"jira_http_error:{msg}")
    except URLError as e:
        try:
            if isinstance(e.reason, _ssl.SSLError):
                raise RuntimeError("jira_cert_missing:TLS certificate bundle not found. Install 'certifi' or system CA certificates.")
        except Exception:
            pass
        raise RuntimeError(f"jira_network_error:{e.reason}")
    except _ssl.SSLError:
        raise RuntimeError("jira_cert_missing:TLS certificate bundle not found. Install 'certifi' or system CA certificates.")
    
def add_issues_to_sprint(sprint_name, keys):
    cfg = _load_config()
    jira_cfg = cfg.get("jira", {})
    base_url = jira_cfg.get("url", "").strip()
    user = jira_cfg.get("user", "").strip()
    token = jira_cfg.get("token", "").strip()
    project_key = jira_cfg.get("project", "").strip() or None
    if not base_url or not user or not token:
        try:
            _jira_logger.info("AddIssuesToSprint MOCK sprint=%r keys=%r", sprint_name, keys)
        except Exception:
            pass
        return True
    auth = _auth_header(user, token)
    boards = _get_boards(base_url, auth, project_key)
    sid = None
    target = str(sprint_name or "").strip().lower()
    for b in boards or []:
        bid = b.get("id")
        sprints = _get_sprints_for_board(base_url, auth, bid)
        for sp in sprints or []:
            nm = str((sp.get("name") or "").strip().lower())
            if nm == target:
                sid = sp.get("id")
                break
        if sid:
            break
    if not sid:
        raise RuntimeError("jira_http_error:Sprint not found")
    url = base_url.rstrip("/") + f"/rest/agile/1.0/sprint/{_req.quote(str(sid))}/issue"
    payload = json.dumps({"issues": [str(k) for k in keys or []]}).encode("utf-8")
    req = _req.Request(url, data=payload, headers={
        "Authorization": auth,
        "Accept": "application/json",
        "Content-Type": "application/json"
    }, method="POST")
    try:
        resp = _urlopen(req, timeout=30)
        try:
            resp.read()
        finally:
            try:
                resp.close()
            except Exception:
                pass
        return True
    except HTTPError as e:
        try:
            msg = e.read().decode("utf-8")
        except Exception:
            msg = str(e)
        raise RuntimeError(f"jira_http_error:{msg}")
    except URLError as e:
        try:
            if isinstance(e.reason, _ssl.SSLError):
                raise RuntimeError("jira_cert_missing:TLS certificate bundle not found. Install 'certifi' or system CA certificates.")
        except Exception:
            pass
        raise RuntimeError(f"jira_network_error:{e.reason}")
    except _ssl.SSLError:
        raise RuntimeError("jira_cert_missing:TLS certificate bundle not found. Install 'certifi' or system CA certificates.")

def _ssl_context():
    try:
        import certifi
        return _ssl.create_default_context(cafile=certifi.where())
    except Exception:
        try:
            return _ssl.create_default_context()
        except Exception:
            return None

def _urlopen(req, timeout=30):
    ctx = _ssl_context()
    if ctx is not None:
        return _req.urlopen(req, timeout=timeout, context=ctx)
    return _req.urlopen(req, timeout=timeout)

def search(jql):
    cfg = _load_config()
    jira_cfg = cfg.get("jira", {})
    base_url = jira_cfg.get("url", "").strip()
    user = jira_cfg.get("user", "").strip()
    token = jira_cfg.get("token", "").strip()
    if not jql:
        return []
    try:
        jql = _sanitize_jql(jql)
    except Exception:
        pass
    # Mock if not configured
    if not base_url or not user or not token:
        try:
            _jira_logger.info("Search MOCK jql=%r", jql)
        except Exception:
            pass
        return []
    auth = _auth_header(user, token)
    # New endpoint as per Atlassian migration: /rest/api/3/search/jql
    url = base_url.rstrip("/") + "/rest/api/3/search/jql?jql=" + _req.quote(jql)
    url += "&maxResults=100&fields=summary,description,issuetype,status,priority,assignee,reporter,created,updated,duedate,customfield_10016,customfield_10112,customfield_10114,customfield_10041,customfield_10043,customfield_10115,customfield_10113"
    try:
        _jira_logger.info("Search JQL=%r", jql)
    except Exception:
        pass
    def _adf_to_text(doc):
        try:
            if isinstance(doc, str):
                return doc
            if not isinstance(doc, dict):
                return ""
            def _walk(node):
                t = node.get("type")
                if t == "text":
                    return node.get("text", "")
                out = []
                for child in node.get("content", []) or []:
                    out.append(_walk(child))
                if t in ("paragraph", "listItem"):
                    return (" ".join(out)).strip()
                return " ".join(out)
            return _walk(doc).strip()
        except Exception:
            return ""
    def _parse_rows(data):
        issues = data.get("issues", [])
        rows = []
        for it in issues:
            f = it.get("fields", {})
            def _name(x):
                if isinstance(x, dict):
                    return x.get("name") or x.get("value") or x.get("displayName") or x.get("key")
                return x
            desc = f.get("description", "")
            ac = f.get("customfield_10041")
            ac_text = ""
            try:
                if isinstance(ac, list):
                    ac_text = "; ".join([str(a) for a in ac if a])
                else:
                    ac_text = _adf_to_text(ac)
            except Exception:
                ac_text = ""
            rows.append({
                "key": it.get("key", ""),
                "summary": f.get("summary", ""),
                "description": _adf_to_text(desc),
                "acceptance": ac_text,
                "story_points": f.get("customfield_10016", 0),
                "benefit": f.get("customfield_10043", ""),
                "businessValue": f.get("customfield_10115", 0),
                "dor": _name(f.get("customfield_10113")),
                "issue_type": _name(f.get("issuetype")),
                "status": _name(f.get("status")),
                "priority": _name(f.get("priority")),
                "assignee": _name(f.get("assignee")),
                "reporter": _name(f.get("reporter")),
                "created": f.get("created", ""),
                "updated": f.get("updated", ""),
                "dueDate": f.get("duedate", ""),
                "work_type": _name(f.get("customfield_10112")),
                "size": _normalize_size_value(_name(f.get("customfield_10114"))),
            })
        return rows
    # Try GET first
    try:
        req = _req.Request(url, headers={"Authorization": auth, "Accept": "application/json"}, method="GET")
        resp = _urlopen(req, timeout=30)
        try:
            data = json.loads(resp.read().decode("utf-8"))
        finally:
            try:
                resp.close()
            except Exception:
                pass
        return _parse_rows(data)
    except HTTPError as e:
        # Fallback to POST if GET is removed or blocked
        try:
            msg = e.read().decode("utf-8")
        except Exception:
            msg = str(e)
        # Attempt POST to /search/jql
        try:
            body = json.dumps({
                "jql": jql,
                "maxResults": 100,
                "fields": [
                        "summary","description","issuetype","status","priority","assignee","reporter","created","updated","duedate","customfield_10112","customfield_10114","customfield_10041","customfield_10043","customfield_10115","customfield_10113"
                ]
            }).encode("utf-8")
            post_url = base_url.rstrip("/") + "/rest/api/3/search/jql"
            req2 = _req.Request(post_url, data=body, headers={
                "Authorization": auth,
                "Accept": "application/json",
                "Content-Type": "application/json"
            }, method="POST")
            resp2 = _urlopen(req2, timeout=30)
            try:
                data2 = json.loads(resp2.read().decode("utf-8"))
            finally:
                try:
                    resp2.close()
                except Exception:
                    pass
            return _parse_rows(data2)
        except Exception:
            raise RuntimeError(f"jira_http_error:{msg}")
    except URLError as e:
        try:
            if isinstance(e.reason, _ssl.SSLError):
                raise RuntimeError("jira_cert_missing:TLS certificate bundle not found. Install 'certifi' or system CA certificates.")
        except Exception:
            pass
        raise RuntimeError(f"jira_network_error:{e.reason}")
    except _ssl.SSLError:
        raise RuntimeError("jira_cert_missing:TLS certificate bundle not found. Install 'certifi' or system CA certificates.")

def link(story_key, feature_key):
    cfg = _load_config()
    jira_cfg = cfg.get("jira", {})
    base_url = jira_cfg.get("url", "").strip()
    user = jira_cfg.get("user", "").strip()
    token = jira_cfg.get("token", "").strip()
    if not story_key or not feature_key:
        raise RuntimeError("jira_issue_missing")
    if not base_url or not user or not token:
        try:
            _jira_logger.info("Link MOCK story=%r feature=%r", story_key, feature_key)
        except Exception:
            pass
        return True
    auth = _auth_header(user, token)
    url = base_url.rstrip("/") + "/rest/api/3/issueLink"
    payload = json.dumps({
        "type": {"name": "Relates", "inward": "relates to", "outward": "relates to"},
        "inwardIssue": {"key": str(feature_key)},
        "outwardIssue": {"key": str(story_key)}
    }).encode("utf-8")
    req = _req.Request(url, data=payload, headers={
        "Authorization": auth,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }, method="POST")
    try:
        resp = _urlopen(req, timeout=30)
        try:
            resp.read()
        finally:
            try:
                resp.close()
            except Exception:
                pass
        return True
    except HTTPError as e:
        try:
            msg = e.read().decode("utf-8")
        except Exception:
            msg = str(e)
        raise RuntimeError(f"jira_http_error:{msg}")
    except URLError as e:
        try:
            if isinstance(e.reason, _ssl.SSLError):
                raise RuntimeError("jira_cert_missing:TLS certificate bundle not found. Install 'certifi' or system CA certificates.")
        except Exception:
            pass
        raise RuntimeError(f"jira_network_error:{e.reason}")
    except _ssl.SSLError:
        raise RuntimeError("jira_cert_missing:TLS certificate bundle not found. Install 'certifi' or system CA certificates.")

def add_comment(issue_key, lines):
    cfg = _load_config()
    jira_cfg = cfg.get("jira", {})
    base_url = jira_cfg.get("url", "").strip()
    user = jira_cfg.get("user", "").strip()
    token = jira_cfg.get("token", "").strip()
    if not issue_key:
        raise RuntimeError("jira_issue_missing")
    if not base_url or not user or not token:
        try:
            _jira_logger.info("Comment MOCK key=%r lines=%r", issue_key, lines)
        except Exception:
            pass
        return True
    auth = _auth_header(user, token)
    url = base_url.rstrip("/") + f"/rest/api/3/issue/{_req.quote(issue_key)}/comment"
    body = _adf_bullets_doc(lines)
    payload = json.dumps({"body": body}).encode("utf-8")
    req = _req.Request(url, data=payload, headers={
        "Authorization": auth,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }, method="POST")
    try:
        resp = _urlopen(req, timeout=30)
        try:
            resp.read()
        finally:
            try:
                resp.close()
            except Exception:
                pass
        return True
    except HTTPError as e:
        try:
            msg = e.read().decode("utf-8")
        except Exception:
            msg = str(e)
        raise RuntimeError(f"jira_http_error:{msg}")
    except URLError as e:
        try:
            if isinstance(e.reason, _ssl.SSLError):
                raise RuntimeError("jira_cert_missing:TLS certificate bundle not found. Install 'certifi' or system CA certificates.")
        except Exception:
            pass
        raise RuntimeError(f"jira_network_error:{e.reason}")
    except _ssl.SSLError:
        raise RuntimeError("jira_cert_missing:TLS certificate bundle not found. Install 'certifi' or system CA certificates.")

def create_subtasks(parent_key, tasks):
    cfg = _load_config()
    mapping = _load_mapping()
    jira_cfg = cfg.get("jira", {})
    base_url = jira_cfg.get("url", "").strip()
    user = jira_cfg.get("user", "").strip()
    token = jira_cfg.get("token", "").strip()
    if not parent_key:
        raise RuntimeError("jira_issue_missing")
    if not base_url or not user or not token:
        try:
            _jira_logger.info("Subtasks MOCK parent=%r tasks=%r", parent_key, tasks)
        except Exception:
            pass
        return []
    auth = _auth_header(user, token)
    project_key = jira_cfg.get("project", "").strip() or _get_project_key(base_url, auth)
    if not project_key:
        raise RuntimeError("jira_project_missing")
    itype_name = mapping.get("issue_types", {}).get("subtask", "Sub-task")
    created = []
    for i, t in enumerate(tasks or []):
        name = (t.get("name") or t.get("title") or f"Task {i+1}")
        hours = t.get("hours")
        fields = {
            "project": {"key": project_key},
            "issuetype": {"name": itype_name},
            "parent": {"key": parent_key},
            "summary": str(name)[:255],
            "description": _adf_text_doc(f"Estimated: {hours}h" if hours is not None else "")
        }
        url = base_url.rstrip("/") + "/rest/api/3/issue"
        payload = json.dumps({"fields": fields}).encode("utf-8")
        req = _req.Request(url, data=payload, headers={
            "Authorization": auth,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }, method="POST")
        try:
            resp = _urlopen(req, timeout=30)
            try:
                data = json.loads(resp.read().decode("utf-8"))
            finally:
                try:
                    resp.close()
                except Exception:
                    pass
            created.append(data.get("key", ""))
        except Exception:
            created.append("")
            continue
    return created

def update_dor_flag(issue_key, flag="Y"):
    cfg = _load_config()
    mapping = _load_mapping()
    jira_cfg = cfg.get("jira", {})
    base_url = jira_cfg.get("url", "").strip()
    user = jira_cfg.get("user", "").strip()
    token = jira_cfg.get("token", "").strip()
    field_id = mapping.get("fields", {}).get("DOR", "customfield_10113")
    if not issue_key:
        raise RuntimeError("jira_issue_missing")
    if not base_url or not user or not token:
        try:
            _jira_logger.info("Update DOR MOCK key=%r field=%r flag=%r", issue_key, field_id, flag)
        except Exception:
            pass
        return True
    auth = _auth_header(user, token)
    url = base_url.rstrip("/") + f"/rest/api/3/issue/{_req.quote(issue_key)}"
    # Resolve select option id using CreateMeta and field options, with synonyms
    val = {"value": flag}
    try:
        project_key = jira_cfg.get("project", "").strip() or _get_project_key(base_url, auth)
        synonyms = {"Y": ["Y", "Yes", "Ready", "True"], "N": ["N", "No", "Not Ready", "False"]}
        meta = None
        try:
            if project_key:
                itypes = _load_mapping().get("issue_types", {})
                itype_name = itypes.get("feature", "Feature")
                meta = _get_createmeta(base_url, auth, project_key, itype_name)
        except Exception:
            meta = None
        options = []
        try:
            opts_meta = _get_field_allowed_values(meta, field_id) if meta else []
            if isinstance(opts_meta, list):
                options.extend(opts_meta)
        except Exception:
            pass
        try:
            opts_field = _get_select_options(base_url, auth, field_id)
            if isinstance(opts_field, list):
                options.extend(opts_field)
        except Exception:
            pass
        # Deduplicate options by id or name
        dedup = {}
        for opt in options or []:
            key = opt.get("id") or (opt.get("name") or opt.get("value"))
            if key and key not in dedup:
                dedup[key] = opt
        options = list(dedup.values())
        # Match against synonyms
        wanted = synonyms.get(str(flag).strip(), [str(flag).strip()])
        flset = [str(w).strip().lower() for w in wanted]
        match = None
        for opt in options or []:
            name = (opt.get("name") or opt.get("value") or "").strip().lower()
            if name in flset:
                match = opt
                break
            for w in flset:
                if name.startswith(w) or w in name:
                    match = opt
                    break
            if match:
                break
        if match and match.get("id"):
            val = {"id": match.get("id")}
        elif match:
            nm = match.get("name") or match.get("value")
            if nm:
                val = {"name": nm}
    except Exception:
        pass
    attempts = [val, {"name": str(flag)}, {"value": str(flag)}, str(flag), {"name": "Yes"}, {"value": "Yes"}, "Yes"]
    last_err = None
    for attempt in attempts:
        payload = json.dumps({"fields": {field_id: attempt}}).encode("utf-8")
        req = _req.Request(url, data=payload, headers={
            "Authorization": auth,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }, method="PUT")
        try:
            resp = _urlopen(req, timeout=30)
            try:
                resp.read()
            finally:
                try:
                    resp.close()
                except Exception:
                    pass
            return True
        except HTTPError as e:
            try:
                last_err = e.read().decode("utf-8")
            except Exception:
                last_err = str(e)
            continue
        except Exception as e:
            last_err = str(e)
            continue
    raise RuntimeError(f"jira_http_error:{last_err}")

def update_status(issue_key, status_name="READY"):
    cfg = _load_config()
    jira_cfg = cfg.get("jira", {})
    base_url = jira_cfg.get("url", "").strip()
    user = jira_cfg.get("user", "").strip()
    token = jira_cfg.get("token", "").strip()
    if not issue_key:
        raise RuntimeError("jira_issue_missing")
    if not base_url or not user or not token:
        try:
            _jira_logger.info("Update Status MOCK key=%r status=%r", issue_key, status_name)
        except Exception:
            pass
        return True
    auth = _auth_header(user, token)
    base = base_url.rstrip("/")
    url = base + f"/rest/api/3/issue/{_req.quote(issue_key)}/transitions"
    req = _req.Request(url, headers={"Authorization": auth, "Accept": "application/json"}, method="GET")
    try:
        resp = _urlopen(req, timeout=30)
        try:
            obj = json.loads(resp.read().decode("utf-8"))
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
        raise RuntimeError(f"jira_http_error:{msg}")
    except URLError as e:
        try:
            if isinstance(e.reason, _ssl.SSLError):
                raise RuntimeError("jira_cert_missing:TLS certificate bundle not found. Install 'certifi' or system CA certificates.")
        except Exception:
            pass
        raise RuntimeError(f"jira_network_error:{e.reason}")
    except _ssl.SSLError:
        raise RuntimeError("jira_cert_missing:TLS certificate bundle not found. Install 'certifi' or system CA certificates.")
    trans = obj.get("transitions", [])
    wanted = str(status_name or "").strip().lower()
    tid = None
    for t in trans or []:
        nm = str((t.get("name") or "").strip().lower())
        to_nm = str(((t.get("to") or {}).get("name") or "").strip().lower())
        cat_nm = str((((t.get("to") or {}).get("statusCategory") or {}).get("name") or "").strip().lower())
        if nm == wanted or to_nm == wanted or cat_nm == wanted:
            tid = t.get("id")
            break
    if not tid and wanted in ("ready",):
        for t in trans or []:
            nm = str((t.get("name") or "").strip().lower())
            to_nm = str(((t.get("to") or {}).get("name") or "").strip().lower())
            cat_nm = str((((t.get("to") or {}).get("statusCategory") or {}).get("name") or "").strip().lower())
            if "ready" in nm or "ready" in to_nm or "ready" in cat_nm:
                tid = t.get("id")
                break
    if not tid:
        raise RuntimeError("jira_http_error:No matching transition for status")
    body = json.dumps({"transition": {"id": tid}}).encode("utf-8")
    preq = _req.Request(url, data=body, headers={"Authorization": auth, "Accept": "application/json", "Content-Type": "application/json"}, method="POST")
    try:
        presp = _urlopen(preq, timeout=30)
        try:
            presp.read()
        finally:
            try:
                presp.close()
            except Exception:
                pass
        return True
    except HTTPError as e:
        try:
            msg = e.read().decode("utf-8")
        except Exception:
            msg = str(e)
        raise RuntimeError(f"jira_http_error:{msg}")
    except URLError as e:
        try:
            if isinstance(e.reason, _ssl.SSLError):
                raise RuntimeError("jira_cert_missing:TLS certificate bundle not found. Install 'certifi' or system CA certificates.")
        except Exception:
            pass
        raise RuntimeError(f"jira_network_error:{e.reason}")
    except _ssl.SSLError:
        raise RuntimeError("jira_cert_missing:TLS certificate bundle not found. Install 'certifi' or system CA certificates.")
def get_issue_details_with_links(issue_key):
    cfg = _load_config()
    jira_cfg = cfg.get("jira", {})
    base_url = jira_cfg.get("url", "").strip()
    user = jira_cfg.get("user", "").strip()
    token = jira_cfg.get("token", "").strip()
    if not issue_key:
        raise RuntimeError("jira_issue_missing")
    if not base_url or not user or not token:
        try:
            _jira_logger.info("IssueDetails MOCK key=%r", issue_key)
        except Exception:
            pass
        return {"issue": {"key": issue_key, "fields": {}}, "links": []}
    auth = _auth_header(user, token)
    base = base_url.rstrip("/")
    url = base + "/rest/api/3/issue/" + _req.quote(issue_key) + "?expand=names,renderedFields"
    req = _req.Request(url, headers={"Authorization": auth, "Accept": "application/json"}, method="GET")
    data = None
    try:
        resp = _urlopen(req, timeout=30)
        try:
            data = json.loads(resp.read().decode("utf-8"))
        finally:
            try:
                resp.close()
            except Exception:
                pass
    except HTTPError:
        pass
    if data is None:
        try:
            alt = base + "/rest/api/3/issue/" + _req.quote(issue_key)
            areq = _req.Request(alt, headers={"Authorization": auth, "Accept": "application/json"}, method="GET")
            aresp = _urlopen(areq, timeout=30)
            try:
                data = json.loads(aresp.read().decode("utf-8"))
            finally:
                try:
                    aresp.close()
                except Exception:
                    pass
        except Exception:
            data = None
    # Fallback to JQL search if direct issue fetch failed
    if data is None:
        try:
            body = json.dumps({
                "jql": f"key = {issue_key}",
                "maxResults": 1,
                "fields": [
                    "issuelinks","summary","description","issuetype","status","priority","assignee","reporter","created","updated","duedate"
                ]
            }).encode("utf-8")
            sreq = _req.Request(base + "/rest/api/3/search/jql", data=body, headers={
                "Authorization": auth,
                "Accept": "application/json",
                "Content-Type": "application/json"
            }, method="POST")
            sresp = _urlopen(sreq, timeout=30)
            try:
                sobj = json.loads(sresp.read().decode("utf-8"))
            finally:
                try:
                    sresp.close()
                except Exception:
                    pass
            issues = sobj.get("issues", [])
            if issues:
                data = issues[0]
        except Exception:
            data = None
    if data is None:
        raise RuntimeError("jira_http_error:Issue fetch failed")
    if "fields" in data:
        issue = {
            "key": data.get("key", issue_key),
            "fields": data.get("fields", {}),
            "names": data.get("names", {}),
        }
    else:
        # When using search fallback, shape differs
        issue = {
            "key": data.get("key", issue_key),
            "fields": data.get("fields", {}),
            "names": {}
        }
    links = []
    for lk in issue.get("fields", {}).get("issuelinks", []) or []:
        rel = (lk.get("type") or {}).get("name")
        direction = "outward" if lk.get("outwardIssue") else ("inward" if lk.get("inwardIssue") else "")
        other = lk.get("outwardIssue") or lk.get("inwardIssue") or {}
        k = other.get("key")
        linked = None
        if k:
            try:
                lurl = base + "/rest/api/3/issue/" + _req.quote(k)
                lreq = _req.Request(lurl, headers={"Authorization": auth, "Accept": "application/json"}, method="GET")
                lr = _urlopen(lreq, timeout=30)
                try:
                    obj = json.loads(lr.read().decode("utf-8"))
                finally:
                    try:
                        lr.close()
                    except Exception:
                        pass
                linked = {"key": obj.get("key", k), "fields": obj.get("fields", {})}
            except Exception:
                # Try search fallback
                try:
                    body = json.dumps({"jql": f"key = {k}", "maxResults": 1, "fields": ["summary","status","priority","assignee","reporter","created","updated","duedate"]}).encode("utf-8")
                    sreq2 = _req.Request(base + "/rest/api/3/search/jql", data=body, headers={"Authorization": auth, "Accept": "application/json", "Content-Type": "application/json"}, method="POST")
                    sresp2 = _urlopen(sreq2, timeout=30)
                    try:
                        sobj2 = json.loads(sresp2.read().decode("utf-8"))
                    finally:
                        try:
                            sresp2.close()
                        except Exception:
                            pass
                    items = sobj2.get("issues", [])
                    if items:
                        it2 = items[0]
                        linked = {"key": it2.get("key", k), "fields": it2.get("fields", {})}
                    else:
                        linked = {"key": k, "fields": {}}
                except Exception:
                    linked = {"key": k, "fields": {}}
        links.append({"relation": rel, "direction": direction, "key": k, "issue": linked})
    return {"issue": issue, "links": links}

def get_issue_raw(issue_key):
    cfg = _load_config()
    jira_cfg = cfg.get("jira", {})
    base_url = jira_cfg.get("url", "").strip()
    user = jira_cfg.get("user", "").strip()
    token = jira_cfg.get("token", "").strip()
    if not issue_key:
        raise RuntimeError("jira_issue_missing")
    if not base_url or not user or not token:
        try:
            _jira_logger.info("IssueRaw MOCK key=%r", issue_key)
        except Exception:
            pass
        return {"key": issue_key, "fields": {}}
    auth = _auth_header(user, token)
    base = base_url.rstrip("/")
    url = base + "/rest/api/3/issue/" + _req.quote(issue_key) + "?expand=names,renderedFields,changelog,transitions"
    req = _req.Request(url, headers={"Authorization": auth, "Accept": "application/json"}, method="GET")
    data = None
    try:
        resp = _urlopen(req, timeout=30)
        try:
            data = json.loads(resp.read().decode("utf-8"))
        finally:
            try:
                resp.close()
            except Exception:
                pass
    except HTTPError:
        pass
    if data is None:
        try:
            alt = base + "/rest/api/3/issue/" + _req.quote(issue_key)
            areq = _req.Request(alt, headers={"Authorization": auth, "Accept": "application/json"}, method="GET")
            aresp = _urlopen(areq, timeout=30)
            try:
                data = json.loads(aresp.read().decode("utf-8"))
            finally:
                try:
                    aresp.close()
                except Exception:
                    pass
        except Exception:
            data = None
    if data is None:
        try:
            body = json.dumps({
                "jql": f"key = {issue_key}",
                "maxResults": 1,
                "fields": ["*all"]
            }).encode("utf-8")
            sreq = _req.Request(base + "/rest/api/3/search/jql", data=body, headers={"Authorization": auth, "Accept": "application/json", "Content-Type": "application/json"}, method="POST")
            sresp = _urlopen(sreq, timeout=30)
            try:
                sobj = json.loads(sresp.read().decode("utf-8"))
            finally:
                try:
                    sresp.close()
                except Exception:
                    pass
            issues = sobj.get("issues", [])
            if issues:
                data = issues[0]
        except Exception:
            data = None
    if data is None:
        raise RuntimeError("jira_http_error:Issue fetch failed")
    return data

def _get_boards(base_url, auth, project_key):
    url = base_url.rstrip("/") + "/rest/agile/1.0/board?maxResults=50"
    if project_key:
        url += "&projectKeyOrId=" + _req.quote(project_key)
    req = _req.Request(url, headers={"Authorization": auth, "Accept": "application/json"}, method="GET")
    try:
        resp = _urlopen(req, timeout=30)
        try:
            obj = json.loads(resp.read().decode("utf-8"))
        finally:
            try:
                resp.close()
            except Exception:
                pass
        return obj.get("values", [])
    except Exception:
        return []

def _get_sprints_for_board(base_url, auth, board_id):
    url = base_url.rstrip("/") + f"/rest/agile/1.0/board/{_req.quote(str(board_id))}/sprint?maxResults=50&state=active,future,closed"
    req = _req.Request(url, headers={"Authorization": auth, "Accept": "application/json"}, method="GET")
    try:
        resp = _urlopen(req, timeout=30)
        try:
            obj = json.loads(resp.read().decode("utf-8"))
        finally:
            try:
                resp.close()
            except Exception:
                pass
        return obj.get("values", [])
    except Exception:
        return []

def update_sprint(issue_key, sprint_name):
    cfg = _load_config()
    mapping = _load_mapping()
    jira_cfg = cfg.get("jira", {})
    base_url = jira_cfg.get("url", "").strip()
    user = jira_cfg.get("user", "").strip()
    token = jira_cfg.get("token", "").strip()
    project_key = jira_cfg.get("project", "").strip() or None
    field_id = mapping.get("fields", {}).get("Sprint", "customfield_10020")
    if not issue_key:
        raise RuntimeError("jira_issue_missing")
    if not base_url or not user or not token:
        try:
            _jira_logger.info("Update Sprint MOCK key=%r field=%r sprint=%r", issue_key, field_id, sprint_name)
        except Exception:
            pass
        return True
    auth = _auth_header(user, token)
    # find sprint id by name across boards
    sid = None
    try:
        boards = _get_boards(base_url, auth, project_key)
        target = str(sprint_name or "").strip().lower()
        for b in boards or []:
            bid = b.get("id")
            sprints = _get_sprints_for_board(base_url, auth, bid)
            for sp in sprints or []:
                nm = str((sp.get("name") or "").strip().lower())
                if nm == target:
                    sid = sp.get("id")
                    break
            if sid:
                break
    except Exception:
        sid = None
    if not sid:
        raise RuntimeError("jira_http_error:Sprint not found")
    url = base_url.rstrip("/") + f"/rest/api/3/issue/{_req.quote(issue_key)}"
    payload = json.dumps({"fields": {field_id: sid}}).encode("utf-8")
    req = _req.Request(url, data=payload, headers={
        "Authorization": auth,
        "Accept": "application/json",
        "Content-Type": "application/json"
    }, method="PUT")
    try:
        resp = _urlopen(req, timeout=30)
        try:
            resp.read()
        finally:
            try:
                resp.close()
            except Exception:
                pass
        return True
    except HTTPError as e:
        try:
            msg = e.read().decode("utf-8")
        except Exception:
            msg = str(e)
        raise RuntimeError(f"jira_http_error:{msg}")
    except URLError as e:
        try:
            if isinstance(e.reason, _ssl.SSLError):
                raise RuntimeError("jira_cert_missing:TLS certificate bundle not found. Install 'certifi' or system CA certificates.")
        except Exception:
            pass
        raise RuntimeError(f"jira_network_error:{e.reason}")
    except _ssl.SSLError:
        raise RuntimeError("jira_cert_missing:TLS certificate bundle not found. Install 'certifi' or system CA certificates.")

def get_open_sprint_names():
    cfg = _load_config()
    jira_cfg = cfg.get("jira", {})
    base_url = jira_cfg.get("url", "").strip()
    user = jira_cfg.get("user", "").strip()
    token = jira_cfg.get("token", "").strip()
    project_key = jira_cfg.get("project", "").strip() or None
    if not base_url or not user or not token:
        try:
            _jira_logger.info("OpenSprints MOCK project=%r", project_key)
        except Exception:
            pass
        return []
    auth = _auth_header(user, token)
    names = []
    seen = set()
    try:
        boards = _get_boards(base_url, auth, project_key)
        for b in boards or []:
            bid = b.get("id")
            sprints = _get_sprints_for_board(base_url, auth, bid)
            for sp in sprints or []:
                st = str((sp.get("state") or "").strip().lower())
                nm = str((sp.get("name") or "").strip())
                if st in ("active", "future") and nm and nm not in seen:
                    seen.add(nm)
                    names.append(nm)
    except Exception:
        pass
    return names
def _sanitize_jql(jql):
    try:
        mapping = _load_mapping()
        names = list((mapping.get("fields") or {}).keys())
    except Exception:
        names = []
    s = str(jql or "")
    try:
        s = re.sub(r"(?i)^\s*(fetch|search|find|query)\b[:]*\s*", "", s)
    except Exception:
        pass
    try:
        fm = mapping.get("fields", {})
        pairs = [
            ("Acceptance Criteria", fm.get("Acceptance Criteria")),
            ("Benefit Hypothesis", fm.get("Benefit Hypothesis")),
            ("Business Value", fm.get("business_value")),
        ]
        for name, fid in pairs:
            if not fid or not str(fid).startswith("customfield_"):
                continue
            cf = "cf[" + str(fid).split("_")[-1] + "]"
            s = re.sub(r'(?i)(?<!\w)"?' + re.escape(name) + r'"?(?!\w)', cf, s)
    except Exception:
        pass
    for name in names:
        n = str(name or "")
        if not n:
            continue
        if n.startswith("customfield_"):
            continue
        pattern = r'(?<!")\b' + re.escape(n) + r'\b(?!")'
        s = re.sub(pattern, '"' + n + '"', s)
    # Map Size values like Small/Medium/Large to S/M/L/XS/XL
    try:
        syn = (mapping.get("size_synonyms") or {})
        # Build reverse map
        rev = {}
        for code, arr in syn.items():
            for a in arr or []:
                rev[str(a).strip().lower()] = str(code).strip()
        rev.update({
            "small": "S", "medium": "M", "large": "L",
            "extra small": "XS", "x-small": "XS",
            "extra large": "XL", "x-large": "XL"
        })
        def _map_token(tok):
            t = str(tok or "").strip().strip('"').lower()
            code = rev.get(t)
            return ('"' + code + '"') if code else tok
        # Handle = value
        s = re.sub(r'("Size"|customfield_10114)\s*=\s*("[^"]+"|[^\s)]+)',
                   lambda m: f"{m.group(1)} = {_map_token(m.group(2))}", s, flags=re.I)
        # Handle in (...) list
        def _map_list(m):
            field = m.group(1)
            body = m.group(2)
            parts = [p.strip() for p in body.split(',')]
            mapped = [_map_token(p) for p in parts]
            return f"{field} in ({', '.join(mapped)})"
        s = re.sub(r'("Size"|customfield_10114)\s+in\s*\(([^)]*)\)', _map_list, s, flags=re.I)
    except Exception:
        pass
    return s
