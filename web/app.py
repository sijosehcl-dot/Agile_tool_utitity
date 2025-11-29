from flask import Flask, render_template, request, redirect, url_for, flash
import os, sys, logging
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from prompt import load_prompts
from config import load_config
from llm import feature_creation, feature_dor, story_creation, story_dor, request_features, request_stories
import jira
from flask import jsonify

app = Flask(__name__)
app.secret_key = "dev"

# Logging for LLM requests
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, 'llm.log')
logger = logging.getLogger('llm')
if not logger.handlers:
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(LOG_FILE)
    fmt = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    fh.setFormatter(fmt)
    logger.addHandler(fh)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/features/create", methods=["GET", "POST"])
def features_create():
    prompts = load_prompts()
    generated = []
    text = ""
    if request.method == "POST":
        text = request.form.get("requirement", "").strip()
        if len(text) > 500:
            flash("Enter details in no more than 500 characters")
        else:
            feats = feature_creation.split_features(text, prompts)
            generated = feats
    return render_template("features_create.html", text=text, features=generated)

@app.route("/api/features/generate", methods=["POST"])
def api_features_generate():
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("requirement") or "").strip()
    if len(text) == 0:
        return jsonify({"error": "Enter requirement"}), 400
    if len(text) > 500:
        return jsonify({"error": "Enter details in no more than 500 characters"}), 400
    prompts = load_prompts()
    prompt_text = (prompts.get("feature_prompt", "") or "").strip()
    if len(prompt_text) == 0:
        return jsonify({"error": "No prompt defined"}), 400
    logger.info("FeatureCreate: prompt=%r requirement=%r", prompt_text, text)
    cfg = load_config()
    try:
        feats = request_features(text, prompt_text, cfg)
    except ValueError as ve:
        if str(ve) == "llm_not_configured":
            return jsonify({"error": "LLM not configured"}), 400
        if str(ve) == "no_prompt":
            return jsonify({"error": "No prompt defined"}), 400
        return jsonify({"error": "Invalid request"}), 400
    except RuntimeError as re_err:
        msg = str(re_err)
        if msg.startswith("llm_http_error:"):
            return jsonify({"error": msg.replace("llm_http_error:", "LLM request failed: ")}), 502
        if msg.startswith("llm_network_error:"):
            return jsonify({"error": msg.replace("llm_network_error:", "LLM network error: ")}), 502
        if msg.startswith("llm_cert_missing:"):
            return jsonify({"error": msg.replace("llm_cert_missing:", "LLM TLS error: ")}), 502
        return jsonify({"error": "LLM request failed"}), 502
    rows = []
    for f in feats:
        rows.append({
            "title": f.get("Title", ""),
            "description": f.get("Summary", ""),
            "acceptance": "\n".join(f.get("Acceptance Criteria", [])) if isinstance(f.get("Acceptance Criteria"), list) else f.get("Acceptance Criteria", ""),
            "benefit": f.get("Benefit Hypothesis", ""),
            "size": f.get("T-Shirt Size", ""),
            "priority": f.get("Priority", ""),
            "businessValue": f.get("Business Value", 0),
            "dueDate": f.get("duedate", ""),
            "issue_type": "Feature",
        })
    return jsonify({"rows": rows})

@app.route("/features/upload")
def features_upload():
    return render_template("features_upload.html")

@app.route("/api/features/upload", methods=["POST"])
def api_features_upload():
    from werkzeug.utils import secure_filename
    import io, csv, os
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "No file uploaded"}), 400
    name = secure_filename(f.filename or "")
    ext = os.path.splitext(name)[1].lower()
    rows = []
    cols = []
    try:
        if ext == ".csv":
            data = f.read().decode("utf-8", errors="ignore")
            reader = csv.reader(io.StringIO(data))
            headers = next(reader, [])
            if not headers:
                return jsonify({"error": "Empty file"}), 400
            cols = [str(h or "").strip() or f"Column{idx+1}" for idx, h in enumerate(headers)]
            for row in reader:
                if not row:
                    continue
                # Normalize row length to columns length
                if len(row) < len(cols):
                    row = row + ["" for _ in range(len(cols) - len(row))]
                elif len(row) > len(cols):
                    row = row[:len(cols)]
                rows.append(row)
        elif ext == ".xlsx":
            try:
                import openpyxl
            except Exception:
                return jsonify({"error": "Install openpyxl to read .xlsx"}), 400
            buf = io.BytesIO(f.read())
            wb = openpyxl.load_workbook(buf)
            ws = wb.active
            it = ws.iter_rows(values_only=True)
            headers = next(it, None)
            if not headers:
                return jsonify({"error": "Empty sheet"}), 400
            cols = [str(h or "").strip() or f"Column{idx+1}" for idx, h in enumerate(headers)]
            for r in it:
                if not r:
                    continue
                row = list(r)
                # Normalize row length to columns length
                if len(row) < len(cols):
                    row = row + ["" for _ in range(len(cols) - len(row))]
                elif len(row) > len(cols):
                    row = row[:len(cols)]
                rows.append(["" if v is None else str(v) for v in row])
        else:
            return jsonify({"error": "Unsupported file type"}), 400
    except Exception:
        return jsonify({"error": "Failed to parse file"}), 400
    return jsonify({"columns": cols, "rows": rows})

@app.route("/api/features/generate_batch", methods=["POST"])
def api_features_generate_batch():
    data = request.get_json(force=True, silent=True) or {}
    reqs = data.get("requirements") or []
    if not isinstance(reqs, list) or len(reqs) == 0:
        return jsonify({"error": "No requirements selected"}), 400
    prompts = load_prompts()
    prompt_text = (prompts.get("feature_prompt", "") or "").strip()
    if len(prompt_text) == 0:
        return jsonify({"error": "No prompt defined"}), 400
    logger.info("FeatureUploadBatch: prompt=%r count=%d", prompt_text, len(reqs))
    cfg = load_config()
    rows = []
    for text in reqs:
        t = (text or "").strip()
        if not t: continue
        try:
            feats = request_features(t, prompt_text, cfg)
        except Exception:
            return jsonify({"error": "LLM request failed"}), 502
        for f in feats:
            rows.append({
                "title": f.get("Title", ""),
                "description": f.get("Summary", ""),
                "acceptance": "\n".join(f.get("Acceptance Criteria", [])) if isinstance(f.get("Acceptance Criteria"), list) else f.get("Acceptance Criteria", ""),
                "benefit": f.get("Benefit Hypothesis", ""),
                "size": f.get("T-Shirt Size", ""),
                "priority": f.get("Priority", ""),
                "businessValue": f.get("Business Value", 0),
                "dueDate": f.get("duedate", ""),
                "issue_type": "Feature",
            })
    return jsonify({"rows": rows})

@app.route("/features/create_jira", methods=["POST"])
def features_create_jira():
    import json
    payload = request.form.get("payload")
    items = []
    try:
        if payload:
            items = json.loads(payload)
    except Exception:
        items = []
    created = []
    errors = []
    for f in items:
        try:
            resp = jira.create_issue(f)
            created.append(resp.get("key", ""))
        except Exception as e:
            errors.append(str(e))
    msg = ""
    if created:
        msg += f"{', '.join([k for k in created if k])} Created"
    if errors:
        if msg:
            msg += " | "
        msg += f"Errors: {', '.join(errors)}"
    flash(msg or "No items")
    return redirect(url_for("features_create"))

@app.route("/features/dor", methods=["GET", "POST"])
def features_dor_check():
    prompts = load_prompts()
    entries = []
    results = []
    if request.method == "POST":
        raw = request.form.get("summaries", "")
        entries = [x.strip() for x in raw.splitlines() if x.strip()]
        for s in entries:
            sc, st, rs = feature_dor.score(s, prompts.get("feature_dor_prompt", ""))
            results.append({"summary": s, "score": sc, "status": st, "reason": rs})
    return render_template("features_dor.html", entries=entries, results=results)

@app.route("/api/features/dor_check", methods=["POST"])
def api_features_dor_check():
    data = request.get_json(force=True, silent=True) or {}
    items = data.get("items") or []
    if not isinstance(items, list) or len(items) == 0:
        return jsonify({"error": "No items selected"}), 400
    prompts = load_prompts()
    prompt_text = (prompts.get("feature_dor_prompt", "") or "").strip()
    # Re-fetch full JIRA details by keys to ensure all fields are present
    keys = [str((it or {}).get("key", "")).strip() for it in items]
    keys = [k for k in keys if k]
    jir_rows = []
    if keys:
        jql_keys = ",".join(keys)
        try:
            jir_rows = jira.search(f"key in ({jql_keys})") or []
        except Exception:
            jir_rows = []
    # Fall back to client items if search failed
    source_rows = jir_rows if jir_rows else items
    out = []
    for it in source_rows:
        key = (it.get("key") or "").strip()
        summary = (it.get("summary") or "").strip()
        parts = []
        def _add(label, value):
            v = value
            if isinstance(value, dict):
                v = value.get("name") or value.get("value")
            v = (v or "").strip() if isinstance(v, str) else v
            if v:
                parts.append(f"{label}: {v}")
        _add("Summary", summary)
        _add("Description", it.get("description"))
        _add("Acceptance Criteria", it.get("acceptance"))
        _add("Benefit Hypothesis", it.get("benefit"))
        _add("Business Value", it.get("businessValue"))
        _add("Priority", it.get("priority"))
        _add("Status", it.get("status"))
        _add("Size", it.get("size"))
        _add("Work Type", it.get("work_type"))
        _add("Assignee", it.get("assignee"))
        _add("Reporter", it.get("reporter"))
        _add("Due Date", it.get("dueDate"))
        text = "\n".join(parts) if parts else summary
        try:
            sc, st, rs = feature_dor.score(text, prompt_text)
        except ValueError as ve:
            if str(ve) == "llm_not_configured":
                return jsonify({"error": "LLM not configured"}), 400
            sc, st, rs = 0, "Fail", "DOR check failed"
        except RuntimeError as re_err:
            msg = str(re_err)
            if msg.startswith("llm_http_error:"):
                return jsonify({"error": msg.replace("llm_http_error:", "LLM request failed: ")}), 502
            if msg.startswith("llm_network_error:"):
                return jsonify({"error": msg.replace("llm_network_error:", "LLM network error: ")}), 502
            if msg.startswith("llm_cert_missing:"):
                return jsonify({"error": msg.replace("llm_cert_missing:", "LLM TLS error: ")}), 502
            sc, st, rs = 0, "Fail", "DOR check failed"
        out.append({"key": key, "summary": summary, "score": sc, "status": st, "reason": rs})
    return jsonify({"rows": out})

@app.route("/api/features/jira_update_dor_flag", methods=["POST"])
def api_features_jira_update_dor_flag():
    data = request.get_json(force=True, silent=True) or {}
    keys = data.get("keys") or []
    flag = (data.get("flag") or "Y").strip() or "Y"
    if not isinstance(keys, list) or len(keys) == 0:
        return jsonify({"error": "No issue keys to update"}), 400
    updated = []
    errors = []
    for k in keys:
        try:
            jira.update_dor_flag(str(k), flag)
            updated.append(str(k))
        except RuntimeError as re_err:
            errors.append(f"{k}:{str(re_err)}")
        except Exception as e:
            errors.append(f"{k}:{str(e)}")
    return jsonify({"updated": updated, "errors": errors})

@app.route("/features/jira")
def features_from_jira():
    return render_template("features_jira.html")

@app.route("/api/features/jira_search", methods=["POST"])
def api_features_jira_search():
    data = request.get_json(force=True, silent=True) or {}
    jql = (data.get("jql") or "").strip()
    if not jql:
        return jsonify({"error": "Enter JQL"}), 400
    try:
        rows = jira.search(jql)
    except RuntimeError as re_err:
        msg = str(re_err)
        if msg.startswith("jira_http_error:"):
            return jsonify({"error": msg.replace("jira_http_error:", "JIRA request failed: ")}), 502
        if msg.startswith("jira_network_error:"):
            return jsonify({"error": msg.replace("jira_network_error:", "JIRA network error: ")}), 502
        if msg.startswith("jira_cert_missing:"):
            return jsonify({"error": msg.replace("jira_cert_missing:", "JIRA TLS error: ")}), 502
        return jsonify({"error": "JIRA request failed"}), 502
    except Exception:
        return jsonify({"error": "JIRA request failed"}), 502
    return jsonify({"rows": rows})

@app.route("/stories/create", methods=["GET"])
def stories_create():
    return render_template("stories_jira.html")

@app.route("/stories/jira", methods=["GET"])
def stories_from_jira():
    return render_template("stories_jira.html")

@app.route("/stories/create_jira", methods=["POST"])
def stories_create_jira():
    items = request.form.getlist("story_summary")
    created = []
    for s in items:
        stories = story_creation.generate_stories(s, load_prompts())
        for st in stories:
            created.append(jira.create_issue(st)["key"])
    flash(f"Created: {', '.join(created)}")
    return redirect(url_for("stories_create"))

@app.route("/api/stories/generate_batch", methods=["POST"])
def api_stories_generate_batch():
    data = request.get_json(force=True, silent=True) or {}
    feats = data.get("features") or data.get("summaries") or []
    if not isinstance(feats, list) or len(feats) == 0:
        return jsonify({"error": "No features selected"}), 400
    prompts = load_prompts()
    prompt_text = (prompts.get("story_prompt", "") or "").strip()
    if len(prompt_text) == 0:
        return jsonify({"error": "No prompt defined"}), 400
    cfg = load_config()
    rows = []
    for it in feats:
        text = it if isinstance(it, str) else ((it or {}).get("summary") or (it or {}).get("description") or "")
        feature_key = (it if isinstance(it, dict) else {}).get("key", "")
        t = (text or "").strip()
        if not t:
            continue
        try:
            stories = request_stories(t, prompt_text, cfg)
        except ValueError as ve:
            if str(ve) == "llm_not_configured":
                return jsonify({"error": "LLM not configured"}), 400
            if str(ve) == "no_prompt":
                return jsonify({"error": "No prompt defined"}), 400
            return jsonify({"error": "Invalid request"}), 400
        except RuntimeError as re_err:
            msg = str(re_err)
            if msg.startswith("llm_http_error:"):
                return jsonify({"error": msg.replace("llm_http_error:", "LLM request failed: ")}), 502
            if msg.startswith("llm_network_error:"):
                return jsonify({"error": msg.replace("llm_network_error:", "LLM network error: ")}), 502
            if msg.startswith("llm_cert_missing:"):
                return jsonify({"error": msg.replace("llm_cert_missing:", "LLM TLS error: ")}), 502
            return jsonify({"error": "LLM request failed"}), 502
        for st in stories:
            rows.append({
                "Feature Key": feature_key,
                "Title": st.get("Title", "Story"),
                "Description": st.get("Summary", st.get("Description", "")),
                "Acceptance Criteria": "\n".join(st.get("Acceptance Criteria", [])) if isinstance(st.get("Acceptance Criteria"), list) else st.get("Acceptance Criteria", ""),
                "Story Point": st.get("Story Point", 3),
                "Issue_type": st.get("Issue_type", "story"),
                "Subtasks": st.get("Tasks", []),
                "Summary": st.get("Summary", ""),
                "Priority": st.get("Priority", "Medium"),
                "Tasks": st.get("Tasks", []),
            })
    return jsonify({"rows": rows})

@app.route("/api/stories/create_batch", methods=["POST"])
def api_stories_create_batch():
    data = request.get_json(force=True, silent=True) or {}
    items = data.get("stories") or []
    if not isinstance(items, list) or len(items) == 0:
        return jsonify({"error": "No stories to create"}), 400
    created = []
    errors = []
    for st in items:
        try:
            res = jira.create_issue(st)
            k = res.get("key") or ""
            if k: created.append(k)
        except Exception as e:
            errors.append(str(e))
    return jsonify({"created": created, "errors": errors})


@app.route("/stories/dor", methods=["GET", "POST"])
def stories_dor_check():
    # Render page; interactive checks handled via API endpoints below
    return render_template("stories_dor.html")

@app.route("/api/stories/jira_search", methods=["POST"])
def api_stories_jira_search():
    data = request.get_json(force=True, silent=True) or {}
    jql = (data.get("jql") or "").strip()
    if not jql:
        return jsonify({"error": "Enter JQL"}), 400
    try:
        rows = jira.search(jql)
    except RuntimeError as re_err:
        msg = str(re_err)
        if msg.startswith("jira_http_error:"):
            return jsonify({"error": msg.replace("jira_http_error:", "JIRA request failed: ")}), 502
        if msg.startswith("jira_network_error:"):
            return jsonify({"error": msg.replace("jira_network_error:", "JIRA network error: ")}), 502
        if msg.startswith("jira_cert_missing:"):
            return jsonify({"error": msg.replace("jira_cert_missing:", "JIRA TLS error: ")}), 502
        return jsonify({"error": "JIRA request failed"}), 502
    except Exception:
        return jsonify({"error": "JIRA request failed"}), 502
    return jsonify({"rows": rows})

@app.route("/api/stories/dor_check", methods=["POST"])
def api_stories_dor_check():
    data = request.get_json(force=True, silent=True) or {}
    items = data.get("items") or []
    if not isinstance(items, list) or len(items) == 0:
        return jsonify({"error": "No items selected"}), 400
    prompts = load_prompts()
    prompt_text = (prompts.get("story_dor_prompt", "") or "").strip()
    keys = [str((it or {}).get("key", "")).strip() for it in items]
    keys = [k for k in keys if k]
    jir_rows = []
    if keys:
        jql_keys = ",".join(keys)
        try:
            jir_rows = jira.search(f"key in ({jql_keys})") or []
        except Exception:
            jir_rows = []
    source_rows = jir_rows if jir_rows else items
    out = []
    for it in source_rows:
        key = (it.get("key") or "").strip()
        summary = (it.get("summary") or "").strip()
        parts = []
        def _add(label, value):
            v = value
            if isinstance(value, dict):
                v = value.get("name") or value.get("value")
            v = (v or "").strip() if isinstance(v, str) else v
            if v:
                parts.append(f"{label}: {v}")
        _add("Summary", summary)
        _add("Description", it.get("description"))
        _add("Acceptance Criteria", it.get("acceptance"))
        _add("Story Points", it.get("story_points") or it.get("Story Point"))
        _add("Priority", it.get("priority"))
        _add("Status", it.get("status"))
        _add("Due Date", it.get("dueDate") or it.get("duedate"))
        text = "\n".join(parts) if parts else summary
        try:
            sc, st, rs = story_dor.score(text, prompt_text)
        except ValueError as ve:
            if str(ve) == "llm_not_configured":
                return jsonify({"error": "LLM not configured"}), 400
            sc, st, rs = 0, "Fail", "DOR check failed"
        except RuntimeError as re_err:
            msg = str(re_err)
            if msg.startswith("llm_http_error:"):
                return jsonify({"error": msg.replace("llm_http_error:", "LLM request failed: ")}), 502
            if msg.startswith("llm_network_error:"):
                return jsonify({"error": msg.replace("llm_network_error:", "LLM network error: ")}), 502
            if msg.startswith("llm_cert_missing:"):
                return jsonify({"error": msg.replace("llm_cert_missing:", "LLM TLS error: ")}), 502
            sc, st, rs = 0, "Fail", "DOR check failed"
        out.append({"key": key, "summary": summary, "score": sc, "status": st, "reason": rs})
    return jsonify({"rows": out})

@app.route("/api/stories/jira_update_dor_flag", methods=["POST"])
def api_stories_jira_update_dor_flag():
    data = request.get_json(force=True, silent=True) or {}
    pass_keys = data.get("pass_keys") or []
    fail_keys = data.get("fail_keys") or []
    # Backward compatibility: single list with one flag
    fallback_keys = data.get("keys") or []
    fallback_flag = (data.get("flag") or "").strip()
    if (not isinstance(pass_keys, list)) or (not isinstance(fail_keys, list)):
        return jsonify({"error": "Invalid payload"}), 400
    if len(pass_keys) == 0 and len(fail_keys) == 0:
        if isinstance(fallback_keys, list) and len(fallback_keys) > 0:
            if (fallback_flag or "").upper() in ("Y", "YES"):
                pass_keys = fallback_keys
            else:
                fail_keys = fallback_keys
        else:
            return jsonify({"error": "No issue keys to update"}), 400
    updated = []
    errors = []
    results = []
    for k in pass_keys:
        try:
            jira.update_dor_flag(str(k), "YES")
            try:
                jira.update_status(str(k), "READY")
                results.append({"key": str(k), "dor": "YES", "status": "READY", "success": True})
            except Exception as e:
                errors.append(f"{k}:{str(e)}")
                results.append({"key": str(k), "dor": "YES", "status": "READY", "success": False, "error": str(e)})
            updated.append(str(k))
        except RuntimeError as re_err:
            msg = str(re_err)
            errors.append(f"{k}:{msg}")
            results.append({"key": str(k), "dor": "YES", "status": "READY", "success": False, "error": msg})
        except Exception as e:
            msg = str(e)
            errors.append(f"{k}:{msg}")
            results.append({"key": str(k), "dor": "YES", "status": "READY", "success": False, "error": msg})
    for k in fail_keys:
        try:
            jira.update_dor_flag(str(k), "No")
            results.append({"key": str(k), "dor": "No", "status": "", "success": True})
            updated.append(str(k))
        except RuntimeError as re_err:
            msg = str(re_err)
            errors.append(f"{k}:{msg}")
            results.append({"key": str(k), "dor": "No", "status": "", "success": False, "error": msg})
        except Exception as e:
            msg = str(e)
            errors.append(f"{k}:{msg}")
            results.append({"key": str(k), "dor": "No", "status": "", "success": False, "error": msg})
    return jsonify({"updated": updated, "errors": errors, "results": results})

@app.route("/sprint/capacity")
def sprint_capacity():
    return render_template("sprint_capacity.html")

@app.route("/sprint/velocity")
def sprint_velocity():
    return render_template("placeholder.html", title="Sprint Velocity")

 

@app.route("/sprint/retrieve")
def sprint_retrieve():
    return render_template("sprint_retrieve.html")

@app.route("/sprint/allocate")
def sprint_allocate():
    return render_template("sprint_allocate.html")

@app.route("/qbr/capacity")
def qbr_capacity():
    return render_template("qbr_capacity.html")

@app.route("/qbr/retrieve")
def qbr_retrieve():
    return render_template("qbr_retrieve.html")

@app.route("/api/qbr/names")
def api_qbr_names():
    import firestore
    try:
        names = firestore.get_qbr_names()
    except Exception:
        names = []
    return jsonify({"names": names})

@app.route("/api/qbr/capacity/get", methods=["POST"])
def api_qbr_capacity_get():
    import firestore
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Enter QBR Name"}), 400
    try:
        rec = firestore.get_qbr_capacity(name) or {}
        return jsonify({
            "summary": rec.get("summary", []),
            "resource_summary": rec.get("resource_summary", []),
        })
    except Exception as e:
        return jsonify({"error": f"Load failed: {e}"}), 500

@app.route("/api/qbr/capacity/save", methods=["POST"])
def api_qbr_capacity_save():
    import firestore
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("qbr_name") or "").strip()
    if not name:
        return jsonify({"error": "Enter QBR Name"}), 400
    try:
        firestore.save_qbr_capacity(data)
    except Exception as e:
        return jsonify({"error": f"Save failed: {e}"}), 500
    return jsonify({"ok": True})

@app.route("/api/sprint/names")
def api_sprint_names():
    import firestore
    try:
        names = firestore.get_sprint_names()
    except Exception as e:
        return jsonify({"error": f"Load failed: {e}"}), 500
    return jsonify({"names": names})

@app.route("/api/sprint/capacity/get", methods=["POST"])
def api_sprint_capacity_get():
    import firestore
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Enter sprint name"}), 400
    try:
        rec = firestore.get_sprint_capacity(name)
    except Exception as e:
        return jsonify({"error": f"Load failed: {e}"}), 500
    if not rec:
        return jsonify({"error": "Sprint not found"}), 404
    summary = rec.get("summary") or []
    resources = rec.get("resource_summary") or []
    return jsonify({"summary": summary, "resources": resources})

@app.route("/api/sprint/capacity/save", methods=["POST"])
def api_sprint_capacity_save():
    import firestore
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("sprint_name") or "").strip()
    if not name:
        return jsonify({"error": "Enter Sprint Name"}), 400
    try:
        firestore.save_sprint_capacity(data)
    except Exception as e:
        return jsonify({"error": f"Save failed: {e}"}), 500
    return jsonify({"ok": True})

@app.route("/api/jira/open_sprints", methods=["GET"])
def api_jira_open_sprints():
    import jira
    # JQL requested: project = SCRUM AND sprint in openSprints()
    # For reliability, use Agile API to list active sprints for the configured project
    try:
        names = jira.get_open_sprint_names() or []
        return jsonify({"names": names, "rows": [{"name": n} for n in names]})
    except Exception as e:
        return jsonify({"error": f"Fetch failed: {e}"}), 500

@app.route("/api/sprint/allocate_stories", methods=["POST"])
def api_sprint_allocate_stories():
    import firestore
    import jira
    data = request.get_json(force=True, silent=True) or {}
    sprint_name = (data.get("sprint_name") or "").strip()
    keys = data.get("keys") or []
    if not sprint_name:
        return jsonify({"error": "Enter sprint name"}), 400
    if not isinstance(keys, list) or len(keys) == 0:
        return jsonify({"error": "No stories to allocate"}), 400
    updated = []
    errors = []
    # Try bulk add via Agile API first
    try:
        jira.add_issues_to_sprint(sprint_name, keys)
        updated = [str(k) for k in keys]
    except Exception as bulk_err:
        errors.append(str(bulk_err))
        # Fallback to per-issue field update
        updated = []
        for k in keys:
            try:
                jira.update_sprint(str(k), sprint_name)
                updated.append(str(k))
            except RuntimeError as re_err:
                errors.append(f"{k}:{str(re_err)}")
            except Exception as e:
                errors.append(f"{k}:{str(e)}")
    # Persist allocation locally for reference
    try:
        firestore.save_sprint_allocation(sprint_name, updated)
    except Exception:
        pass
    if errors and not updated:
        return jsonify({"error": "; ".join(errors)}), 502
    return jsonify({"ok": True, "updated": updated, "errors": errors})

@app.route("/meeting/upload", methods=["GET", "POST"])
def meeting_upload():
    return render_template("meeting_upload.html")

@app.route("/api/meeting/process_transcript", methods=["POST"])
def api_meeting_process_transcript():
    import time
    import ssl as _ssl
    from urllib import request as _req
    from urllib.error import HTTPError, URLError
    def _ssl_context():
        try:
            import certifi
            return _ssl.create_default_context(cafile=certifi.where())
        except Exception:
            try:
                return _ssl.create_default_context()
            except Exception:
                return None
    def _urlopen(req, timeout=60):
        ctx = _ssl_context()
        if ctx is not None:
            return _req.urlopen(req, timeout=timeout, context=ctx)
        return _req.urlopen(req, timeout=timeout)
    action = request.form.get("action") or request.form.get("Action") or "RET"
    file_obj = request.files.get("file") or request.files.get("File")
    filename = None
    content = None
    if file_obj:
        filename = file_obj.filename or "transcript.txt"
        content = file_obj.read()
    else:
        # fallback to text field if no file was uploaded
        text = request.form.get("text") or request.form.get("Transcript") or ""
        filename = "transcript.txt"
        content = (text or "").encode("utf-8")
    if not content:
        return jsonify({"error": "No transcript provided"}), 400
    boundary = "----TraeBoundary%08x" % (int(time.time()) & 0xFFFFFFFF)
    CRLF = "\r\n"
    body_parts = []
    # Action field (both cases for compatibility)
    for name in ("Action", "action"):
        body_parts.append(f"--{boundary}{CRLF}".encode("utf-8"))
        body_parts.append(f"Content-Disposition: form-data; name=\"{name}\"{CRLF}{CRLF}".encode("utf-8"))
        body_parts.append(str(action).encode("utf-8"))
        body_parts.append(CRLF.encode("utf-8"))
    # File field (both cases for compatibility)
    for name in ("File", "file"):
        body_parts.append(f"--{boundary}{CRLF}".encode("utf-8"))
        body_parts.append(f"Content-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"{CRLF}".encode("utf-8"))
        body_parts.append(f"Content-Type: text/plain{CRLF}{CRLF}".encode("utf-8"))
        body_parts.append(content)
        body_parts.append(CRLF.encode("utf-8"))
    # Closing boundary
    body_parts.append(f"--{boundary}--{CRLF}".encode("utf-8"))
    body = b"".join(body_parts)
    url = "https://us-central1-learngenaiapp.cloudfunctions.net/process_transcript"
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json"}
    req = _req.Request(url, data=body, headers=headers, method="POST")
    try:
        resp = _urlopen(req, timeout=60)
        try:
            raw = resp.read().decode("utf-8", errors="replace")
        finally:
            try:
                resp.close()
            except Exception:
                pass
        # Try JSON first, else return raw text
        try:
            import json as _json
            return jsonify(_json.loads(raw))
        except Exception:
            return jsonify({"result": raw})
    except HTTPError as e:
        try:
            msg = e.read().decode("utf-8")
        except Exception:
            msg = str(e)
        # Fallback: attempt JSON body
        try:
            import json as _json
            payload = {
                "Action": str(action),
                "action": str(action),
                "File": content.decode("utf-8", errors="replace"),
                "file": content.decode("utf-8", errors="replace")
            }
            req2 = _req.Request(url, data=_json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json", "Accept": "application/json"}, method="POST")
            resp2 = _urlopen(req2, timeout=60)
            try:
                raw2 = resp2.read().decode("utf-8", errors="replace")
            finally:
                try:
                    resp2.close()
                except Exception:
                    pass
            try:
                return jsonify(_json.loads(raw2))
            except Exception:
                return jsonify({"result": raw2})
        except Exception:
            return jsonify({"error": msg}), 502
    except URLError as e:
        try:
            if isinstance(e.reason, _ssl.SSLError):
                return jsonify({"error": "TLS certificate error"}), 502
        except Exception:
            pass
        return jsonify({"error": str(e.reason)}), 502

@app.route("/config/jira", methods=["GET", "POST"])
def config_jira():
    from config import load_config, save_config
    cfg = load_config()
    if request.method == "POST":
        cfg["jira"] = {
            "url": request.form.get("url", ""),
            "user": request.form.get("user", ""),
            "token": request.form.get("token", ""),
            "project": request.form.get("project", ""),
        }
        save_config(cfg)
        flash("JIRA config saved")
    return render_template("config_form.html", title="JIRA Configuration", fields=[
        ("URL", "url", cfg.get("jira", {}).get("url", "")),
        ("User", "user", cfg.get("jira", {}).get("user", "")),
        ("Token", "token", cfg.get("jira", {}).get("token", "")),
        ("Project Key", "project", cfg.get("jira", {}).get("project", "")),
    ], secret_names=["token"]) 

@app.route("/config/llm", methods=["GET", "POST"])
def config_llm():
    from config import load_config, save_config
    cfg = load_config()
    if request.method == "POST":
        cfg["llm"] = {
            "api_key": request.form.get("api_key", ""),
            "model": request.form.get("model", ""),
        }
        save_config(cfg)
        flash("LLM config saved")
    return render_template("config_form.html", title="LLM Configuration", fields=[
        ("API Key", "api_key", cfg.get("llm", {}).get("api_key", "")),
        ("Model", "model", cfg.get("llm", {}).get("model", "")),
    ], secret_names=["api_key"]) 

@app.route("/config/confluence", methods=["GET", "POST"])
def config_confluence():
    from config import load_config, save_config
    cfg = load_config()
    if request.method == "POST":
        cfg["confluence"] = {
            "url": request.form.get("url", ""),
            "space": request.form.get("space", ""),
            "page": request.form.get("page", ""),
        }
        save_config(cfg)
        flash("Confluence config saved")
    return render_template("config_form.html", title="Confluence Configuration", fields=[
        ("URL", "url", cfg.get("confluence", {}).get("url", "")),
        ("Space", "space", cfg.get("confluence", {}).get("space", "")),
        ("Page", "page", cfg.get("confluence", {}).get("page", "")),
    ]) 

@app.route("/prompts/<key>", methods=["GET", "POST"])
def edit_prompt(key):
    from prompt import load_prompts, save_prompts
    allowed = {"feature_prompt":"Feature creation", "story_prompt":"Story Creation", "feature_dor_prompt":"Feature DOR", "story_dor_prompt":"Story DOR"}
    if key not in allowed:
        return "Not found", 404
    prompts = load_prompts()
    if request.method == "POST":
        prompts[key] = request.form.get("text", "")
        save_prompts(prompts)
        flash("Prompt saved")
    value = prompts.get(key, "")
    return render_template("prompts.html", title=f"Prompt: {allowed[key]}", key=key, value=value)

@app.route("/logout")
def logout():
    flash("Logged out")
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
