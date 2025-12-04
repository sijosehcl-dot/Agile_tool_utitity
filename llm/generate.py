import re

def _size(n):
    if n > 280:
        return "XL"
    if n > 200:
        return "L"
    if n > 120:
        return "M"
    if n > 50:
        return "S"
    return "XS"

def _prio(text):
    if re.search(r"critical|urgent|immediate", text, re.I):
        return "Critical"
    if re.search(r"high|important", text, re.I):
        return "High"
    return "Medium"

def generate_features(text, prompts):
    words = re.findall(r"\w+", text)
    n = len(words)
    title = text.strip()[:80] or "Feature"
    ac = []
    for s in re.split(r"[\n;•\-]+", text):
        s = s.strip()
        if len(s) > 0:
            ac.append(f"Given {s[:40]} When executed Then measurable")
    ac = ac[:5]
    value = 8 if re.search(r"revenue|value|impact", text, re.I) else 5
    return [{
        "Title": title,
        "Summary": text[:500],
        "Acceptance Criteria": ac,
        "Benefit Hypothesis": "Improves outcomes",
        "T-Shirt Size": _size(n),
        "Business Value": value,
        "Priority": _prio(text),
        "Issue_type": "Feature",
    }]

def split_features(text, prompts):
    words = re.findall(r"\w+|\S", text)
    chunks = []
    cur = []
    count = 0
    for w in words:
        cur.append(w)
        count += 1 if re.match(r"\w+", w) else 0
        if count >= 250:
            chunks.append(" ".join(cur))
            cur = []
            count = 0
    if cur:
        chunks.append(" ".join(cur))
    if len(chunks) == 0:
        chunks = [text]
    res = []
    for c in chunks:
        res.extend(generate_features(c, prompts))
    return res

def generate_stories(text, prompts):
    words = re.findall(r"\w+", text)
    n = len(words)
    sp = max(1, min(13, n // 30))
    title = text.strip()[:80] or "Story"
    tasks = []
    base = ["Design", "Implement", "Test", "Review"]
    for name in base:
        hours = max(1, len(text) // 200)
        tasks.append({"name": name, "hours": hours + int(0.1 * hours)})
    return [{
        "Title": title,
        "Summary": text[:400],
        "Acceptance Criteria": ["Meets INVEST", "Deliverable is verifiable"],
        "Story Point": sp,
        "Priority": _prio(text),
        "Issue_type": "story",
        "Tasks": tasks,
    }]

def dor_score(summary, prompt):
    score = min(100, max(1, len(re.findall(r"\w+", summary)) // 3))
    status = "Pass" if score >= 85 else "Fail"
    reason = "Content length and structure assessed"
    return score, status, reason

