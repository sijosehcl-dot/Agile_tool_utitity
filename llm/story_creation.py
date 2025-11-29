import re

def _prio(text):
    if re.search(r"critical|urgent|immediate", text, re.I):
        return "Critical"
    if re.search(r"high|important", text, re.I):
        return "High"
    return "Medium"

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

