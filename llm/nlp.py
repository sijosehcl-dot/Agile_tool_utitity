import json
import re
import ssl as _ssl
import time
import random
import threading
import socket
from urllib import request as _req
from urllib.error import HTTPError, URLError

def _strip_code_fences(text):
    s = text.strip()
    s = re.sub(r"^```(?:json)?", "", s)
    s = re.sub(r"```$", "", s)
    return s.strip()

def nlp_to_jql(request_text, project_key, config=None):
    cfg = config or {}
    llm = cfg.get("llm", {})
    api_key = llm.get("api_key", "").strip()
    primary_model = llm.get("model", "").strip()
    alternates = llm.get("alternates") or []
    try:
        timeout_secs = int(llm.get("timeout_secs", 60))
    except Exception:
        timeout_secs = 60
    try:
        max_retries = int(llm.get("max_retries", 5))
    except Exception:
        max_retries = 5
    try:
        max_concurrent = int(llm.get("max_concurrent", 4))
    except Exception:
        max_concurrent = 4
    try:
        cooldown_secs = int(llm.get("cooldown_secs", 60))
    except Exception:
        cooldown_secs = 60
    if not api_key or not primary_model:
        raise ValueError("llm_not_configured")
    models = [m.strip() for m in ([primary_model] + list(alternates)) if str(m or "").strip()]
    avail = set()
    gen_ok = set()
    try:
        urlm = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        reqm = _req.Request(urlm, headers={"Accept": "application/json"}, method="GET")
        ctxm = None
        try:
            import certifi
            ctxm = _ssl.create_default_context(cafile=certifi.where())
        except Exception:
            ctxm = None
        if ctxm is not None:
            respm = _req.urlopen(reqm, timeout=30, context=ctxm)
        else:
            respm = _req.urlopen(reqm, timeout=30)
        try:
            rawm = respm.read().decode("utf-8")
            objm = json.loads(rawm)
        finally:
            try:
                respm.close()
            except Exception:
                pass
        arr = objm.get("models") or objm.get("data") or []
        for it in arr or []:
            nm = (it.get("name") or "").strip()
            if nm.startswith("models/"):
                nm = nm.split("/",1)[1]
            if nm:
                avail.add(nm)
                methods = it.get("supportedGenerationMethods") or []
                if "generateContent" in methods:
                    gen_ok.add(nm)
    except Exception:
        pass
    # initialize concurrency limiter
    global _SEM
    if _SEM is None:
        _SEM = threading.Semaphore(max_concurrent)
    def _base_name(x):
        x = str(x or "").strip()
        if x.startswith("models/"):
            x = x.split("/",1)[1]
        if x.endswith("-latest"):
            x = x[:-7]
        return x
    filtered = []
    seen = set()
    for m in models:
        mm = str(m or "").strip()
        if not gen_ok:
            if mm not in seen:
                filtered.append(mm); seen.add(mm)
            continue
        base = _base_name(mm)
        choice = None
        if mm in gen_ok:
            choice = mm
        elif base in gen_ok:
            choice = base
        elif f"{base}-latest" in gen_ok:
            choice = f"{base}-latest"
        if choice and choice not in seen:
            filtered.append(choice); seen.add(choice)
    if filtered:
        models = filtered
    ctx_proj = str(project_key or "").strip()
    base_instr = (f"Use project = {ctx_proj} and return ONLY a valid JQL string." if ctx_proj else "Return ONLY a valid JQL string.")
    instr = base_instr + " Use double quotes around field names like Size, DOR, Sprint, Acceptance Criteria, Benefit Hypothesis. For Size values, use codes XS/S/M/L/XL (e.g., Small→S, Extra Large→XL)."
    ck = (str(request_text or "").strip(), ctx_proj)
    now = int(time.time())
    cv = _CACHE.get(ck)
    if cv and isinstance(cv, dict):
        t = int(cv.get("t", 0))
        if now - t < 300:
            s = str(cv.get("v", ""))
            if s:
                return s
    obj = None
    last_err = ""
    last_kind = ""
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": f"Convert the request to JQL for Jira Cloud. {instr}\n\nRequest:\n{request_text}"}
                    ]
                }
            ],
            "generationConfig": {"responseMimeType": "text/plain"}
        }
        data = json.dumps(payload).encode("utf-8")
        req = _req.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        obj = None
        # skip models in cooldown
        try:
            cd_until = _COOLDOWN.get(model, 0)
            if cd_until and time.time() < cd_until:
                continue
        except Exception:
            pass
        for i in range(max_retries):
            try:
                ctx = None
                try:
                    import certifi
                    ctx = _ssl.create_default_context(cafile=certifi.where())
                except Exception:
                    ctx = None
                _SEM.acquire()
                try:
                    eff_timeout = max(5, min(120, int(timeout_secs * (1 + 0.5 * i))))
                    if ctx is not None:
                        resp = _req.urlopen(req, timeout=eff_timeout, context=ctx)
                    else:
                        resp = _req.urlopen(req, timeout=eff_timeout)
                finally:
                    try:
                        _SEM.release()
                    except Exception:
                        pass
                try:
                    raw = resp.read().decode("utf-8")
                    obj = json.loads(raw)
                finally:
                    try:
                        resp.close()
                    except Exception:
                        pass
                break
            except HTTPError as e:
                try:
                    msg = e.read().decode("utf-8")
                except Exception:
                    msg = str(e)
                last_err = msg
                last_kind = "http"
                code = getattr(e, "code", None)
                try:
                    ra = None
                    h = getattr(e, "headers", None)
                    if h:
                        ra = h.get("Retry-After")
                    if ra and i < (max_retries - 1):
                        try:
                            dly = int(ra)
                            time.sleep(max(0, dly))
                            continue
                        except Exception:
                            pass
                except Exception:
                    pass
                if code in (429, 500, 503) and i < (max_retries - 1):
                    delay = min(8, (2 ** i)) + random.uniform(0, 0.5)
                    time.sleep(delay)
                    continue
                if code in (404,):
                    obj = None
                    try:
                        _COOLDOWN[model] = int(time.time()) + cooldown_secs
                    except Exception:
                        pass
                    break
                if code in (429, 500, 503):
                    obj = None
                    try:
                        cd = None
                        h = getattr(e, "headers", None)
                        if h:
                            ra = h.get("Retry-After")
                            if ra:
                                cd = int(ra)
                        if not cd:
                            cd = cooldown_secs
                        _COOLDOWN[model] = int(time.time()) + int(cd)
                    except Exception:
                        pass
                    break
                raise RuntimeError(f"llm_http_error:{msg}")
            except URLError as e:
                try:
                    if isinstance(e.reason, _ssl.SSLError):
                        raise RuntimeError("llm_cert_missing:TLS certificate bundle not found. Install 'certifi' or system CA certificates.")
                except Exception:
                    pass
                last_err = str(e.reason)
                last_kind = "network"
                if i < (max_retries - 1):
                    delay = min(8, (2 ** i)) + random.uniform(0, 0.5)
                    time.sleep(delay)
                    continue
                try:
                    _COOLDOWN[model] = int(time.time()) + cooldown_secs
                except Exception:
                    pass
                break
            except _ssl.SSLError:
                raise RuntimeError("llm_cert_missing:TLS certificate bundle not found. Install 'certifi' or system CA certificates.")
            except TimeoutError:
                last_err = "timeout"
                last_kind = "network"
                if i < (max_retries - 1):
                    delay = min(8, (2 ** i)) + random.uniform(0, 0.5)
                    time.sleep(delay)
                    continue
                try:
                    _COOLDOWN[model] = int(time.time()) + cooldown_secs
                except Exception:
                    pass
                break
            except socket.timeout:
                last_err = "timeout"
                last_kind = "network"
                if i < (max_retries - 1):
                    delay = min(8, (2 ** i)) + random.uniform(0, 0.5)
                    time.sleep(delay)
                    continue
                try:
                    _COOLDOWN[model] = int(time.time()) + cooldown_secs
                except Exception:
                    pass
                break
        if obj is not None:
            break
    if obj is None:
        if last_kind == "network":
            raise RuntimeError("llm_network_error:" + (last_err or "timeout"))
        raise RuntimeError("llm_http_error:" + (last_err or "empty response"))
    candidates = obj.get("candidates", [])
    text = ""
    if candidates:
        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if parts:
            text = parts[0].get("text", "")
    s = (text or "").strip()
    s = _strip_code_fences(s)
    s = re.sub(r"^JQL\s*:\s*", "", s, flags=re.I)
    s = re.sub(r"^(fetch|search|find|query)\b[:]*\s*", "", s, flags=re.I)
    s = s.strip()
    if not s:
        raise RuntimeError("llm_empty_output")
    _CACHE[ck] = {"t": now, "v": s}
    return s

_CACHE = {}
_SEM = None
_COOLDOWN = {}
_PT_CACHE = {}

def generate_plain_text(prompt_text, config=None):
    # Early return from cache to avoid unnecessary LLM calls
    ck = str(prompt_text or "").strip()
    now = int(time.time())
    cv = _PT_CACHE.get(ck)
    if cv and isinstance(cv, dict):
        t = int(cv.get("t", 0))
        if now - t < 300:
            s = str(cv.get("v", ""))
            if s:
                return s
    cfg = config or {}
    llm = cfg.get("llm", {})
    api_key = llm.get("api_key", "").strip()
    primary_model = llm.get("model", "").strip()
    alternates = llm.get("alternates") or []
    try:
        timeout_secs = int(llm.get("timeout_secs", 60))
    except Exception:
        timeout_secs = 60
    try:
        max_retries = int(llm.get("max_retries", 5))
    except Exception:
        max_retries = 5
    try:
        max_concurrent = int(llm.get("max_concurrent", 4))
    except Exception:
        max_concurrent = 4
    try:
        cooldown_secs = int(llm.get("cooldown_secs", 60))
    except Exception:
        cooldown_secs = 60
    if not api_key or not primary_model:
        raise ValueError("llm_not_configured")
    models = [m.strip() for m in ([primary_model] + list(alternates)) if str(m or "").strip()]
    avail = set()
    gen_ok = set()
    try:
        urlm = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        reqm = _req.Request(urlm, headers={"Accept": "application/json"}, method="GET")
        ctxm = None
        try:
            import certifi
            ctxm = _ssl.create_default_context(cafile=certifi.where())
        except Exception:
            ctxm = None
        if ctxm is not None:
            respm = _req.urlopen(reqm, timeout=30, context=ctxm)
        else:
            respm = _req.urlopen(reqm, timeout=30)
        try:
            rawm = respm.read().decode("utf-8")
            objm = json.loads(rawm)
        finally:
            try:
                respm.close()
            except Exception:
                pass
        arr = objm.get("models") or objm.get("data") or []
        for it in arr or []:
            nm = (it.get("name") or "").strip()
            if nm.startswith("models/"):
                nm = nm.split("/",1)[1]
            if nm:
                avail.add(nm)
                methods = it.get("supportedGenerationMethods") or []
                if "generateContent" in methods:
                    gen_ok.add(nm)
    except Exception:
        pass
    global _SEM
    if _SEM is None:
        _SEM = threading.Semaphore(max_concurrent)
    def _base_name(x):
        x = str(x or "").strip()
        if x.startswith("models/"):
            x = x.split("/",1)[1]
        if x.endswith("-latest"):
            x = x[:-7]
        return x
    filtered = []
    seen = set()
    for m in models:
        mm = str(m or "").strip()
        if not gen_ok:
            if mm not in seen:
                filtered.append(mm); seen.add(mm)
            continue
        base = _base_name(mm)
        choice = None
        if mm in gen_ok:
            choice = mm
        elif base in gen_ok:
            choice = base
        elif f"{base}-latest" in gen_ok:
            choice = f"{base}-latest"
        if choice and choice not in seen:
            filtered.append(choice); seen.add(choice)
    if filtered:
        models = filtered
    # Cache handled above; proceed to LLM request
    obj = None
    last_err = ""
    last_kind = ""
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": str(prompt_text or "")}]} 
            ],
            "generationConfig": {"responseMimeType": "text/plain"}
        }
        data = json.dumps(payload).encode("utf-8")
        req = _req.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        obj = None
        try:
            cd_until = _COOLDOWN.get(model, 0)
            if cd_until and time.time() < cd_until:
                continue
        except Exception:
            pass
        for i in range(max_retries):
            try:
                ctx = None
                try:
                    import certifi
                    ctx = _ssl.create_default_context(cafile=certifi.where())
                except Exception:
                    ctx = None
                _SEM.acquire()
                try:
                    eff_timeout = max(5, min(120, int(timeout_secs * (1 + 0.5 * i))))
                    if ctx is not None:
                        resp = _req.urlopen(req, timeout=eff_timeout, context=ctx)
                    else:
                        resp = _req.urlopen(req, timeout=eff_timeout)
                finally:
                    try:
                        _SEM.release()
                    except Exception:
                        pass
                try:
                    raw = resp.read().decode("utf-8")
                    obj = json.loads(raw)
                finally:
                    try:
                        resp.close()
                    except Exception:
                        pass
                break
            except HTTPError as e:
                try:
                    msg = e.read().decode("utf-8")
                except Exception:
                    msg = str(e)
                last_err = msg
                last_kind = "http"
                code = getattr(e, "code", None)
                try:
                    ra = None
                    h = getattr(e, "headers", None)
                    if h:
                        ra = h.get("Retry-After")
                    if ra and i < (max_retries - 1):
                        try:
                            dly = int(ra)
                            time.sleep(max(0, dly))
                            continue
                        except Exception:
                            pass
                except Exception:
                    pass
                if code in (429, 500, 503) and i < (max_retries - 1):
                    delay = min(8, (2 ** i)) + random.uniform(0, 0.5)
                    time.sleep(delay)
                    continue
                if code in (404,):
                    obj = None
                    try:
                        _COOLDOWN[model] = int(time.time()) + cooldown_secs
                    except Exception:
                        pass
                    break
                if code in (429, 500, 503):
                    obj = None
                    try:
                        cd = None
                        h = getattr(e, "headers", None)
                        if h:
                            ra = h.get("Retry-After")
                            if ra:
                                cd = int(ra)
                        if not cd:
                            cd = cooldown_secs
                        _COOLDOWN[model] = int(time.time()) + int(cd)
                    except Exception:
                        pass
                    break
                raise RuntimeError(f"llm_http_error:{msg}")
            except URLError as e:
                try:
                    if isinstance(e.reason, _ssl.SSLError):
                        raise RuntimeError("llm_cert_missing:TLS certificate bundle not found. Install 'certifi' or system CA certificates.")
                except Exception:
                    pass
                last_err = str(e.reason)
                last_kind = "network"
                if i < (max_retries - 1):
                    delay = min(8, (2 ** i)) + random.uniform(0, 0.5)
                    time.sleep(delay)
                    continue
                try:
                    _COOLDOWN[model] = int(time.time()) + cooldown_secs
                except Exception:
                    pass
                break
            except _ssl.SSLError:
                raise RuntimeError("llm_cert_missing:TLS certificate bundle not found. Install 'certifi' or system CA certificates.")
            except TimeoutError:
                last_err = "timeout"
                last_kind = "network"
                if i < (max_retries - 1):
                    delay = min(8, (2 ** i)) + random.uniform(0, 0.5)
                    time.sleep(delay)
                    continue
                try:
                    _COOLDOWN[model] = int(time.time()) + cooldown_secs
                except Exception:
                    pass
                break
            except socket.timeout:
                last_err = "timeout"
                last_kind = "network"
                if i < (max_retries - 1):
                    delay = min(8, (2 ** i)) + random.uniform(0, 0.5)
                    time.sleep(delay)
                    continue
                try:
                    _COOLDOWN[model] = int(time.time()) + cooldown_secs
                except Exception:
                    pass
                break
        if obj is not None:
            break
    if obj is None:
        if last_kind == "network":
            raise RuntimeError("llm_network_error:" + (last_err or "timeout"))
        raise RuntimeError("llm_http_error:" + (last_err or "empty response"))
    candidates = obj.get("candidates", [])
    out = ""
    if candidates:
        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if parts:
            out = parts[0].get("text", "")
    s = str(out or "").strip()
    if not s:
        raise RuntimeError("llm_empty_output")
    _PT_CACHE[ck] = {"t": int(time.time()), "v": s}
    return s
