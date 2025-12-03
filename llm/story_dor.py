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
    full = f"{txt}\n\nStory Summary:\n{summary}\n\nReturn ONLY the two lines in this exact format:\nScore: <integer 1-100>\nReason: <brief explanation>"
    try:
        text = generate_plain_text(full, cfg)
        sc, st, rs = _parse_text(text)
        return sc, st, rs
    except RuntimeError as e:
        msg = str(e)
        overloaded = False
        empty = msg.startswith("llm_empty_output")
        any_http = msg.startswith("llm_http_error:")
        if any_http:
            raw = msg.replace("llm_http_error:", "").strip()
            try:
                obj = json.loads(raw); err = obj.get("error") or obj
                c = err.get("code"); s = (err.get("status") or "").upper()
                overloaded = (c == 503) or (s == "UNAVAILABLE")
            except Exception:
                overloaded = False
        if any_http or msg.startswith("llm_network_error:") or empty:
            s = str(summary or "")
            score = 50
            if re.search(r"Acceptance Criteria\s*:\s*", s, re.I): score += 20
            wc = len(re.findall(r"\w+", s))
            if wc > 200: score += 5
            if wc < 50: score -= 10
            score = max(1, min(100, score))
            st = "Pass" if score >= 85 else "Fail"
            rs = "Heuristic DOR due to AI error"
            return score, st, rs
        raise
from .nlp import generate_plain_text
