import re
import json
import ssl as _ssl
from urllib import request as _req
from urllib.error import HTTPError, URLError

def _parse_text(text):
    s = str(text or "")
    m = re.search(r"Score\s*:\s*(\d{1,3})", s, re.I)
    n = 0
    if m:
        try:
            n = int(m.group(1))
        except Exception:
            n = 0
    r = ""
    mr = re.search(r"Reason\s*:\s*(.+)", s, re.I | re.S)
    if mr:
        r = mr.group(1).strip()
    n = max(1, min(100, n)) if n else max(1, min(100, len(re.findall(r"\w+", s)) // 3))
    st = "Pass" if n >= 85 else "Fail"
    return n, st, r or "DOR evaluated"

def score(summary, prompt):
    txt = (prompt or "").strip()
    if not txt:
        sc = min(100, max(1, len(re.findall(r"\w+", summary)) // 3))
        st = "Pass" if sc >= 85 else "Fail"
        return sc, st, "Content length and structure assessed"
    try:
        from config import load_config
        cfg = load_config()
    except Exception:
        cfg = {}
    llm = cfg.get("llm", {})
    api_key = (llm.get("api_key") or "").strip()
    model = (llm.get("model") or "").strip()
    if not api_key or not model:
        raise ValueError("llm_not_configured")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": f"{txt}\n\nStory Summary:\n{summary}\n\nReturn ONLY the two lines in this exact format:\nScore: <integer 1-100>\nReason: <brief explanation>"
                    }
                ]
            }
        ],
        "generationConfig": {"responseMimeType": "text/plain"}
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
    except _ssl.SSLError:
        raise RuntimeError("llm_cert_missing:TLS certificate bundle not found. Install 'certifi' or system CA certificates.")
    candidates = obj.get("candidates", [])
    text = ""
    if candidates:
        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if parts:
            text = parts[0].get("text", "")
    sc, st, rs = _parse_text(text)
    return sc, st, rs
