import os
import json

def _path(name):
    return os.path.join(os.path.dirname(__file__), name)

def load_prompts():
    p = {
        "feature_prompt": "Create feature JSON with Title, Summary, Acceptance Criteria, Benefit Hypothesis, TShirtSize, BusinessValue, Priority, Issue_type=Feature",
        "feature_creation_request": "Given a requirement, produce one or more Feature objects with Title, Description, Acceptance Criteria, Benefit Hypothesis, T-Shirt Size (XL/L/M/S/XS), Priority (Critical/High/Medium/Low), Business Value (1-10). If the requirement is very large, split into multiple independent features.",
        "story_prompt": "Create story JSON with Title, Summary, Acceptance Criteria, StoryPoint, Priority, Issue_type=story",
        "feature_dor_prompt": "Assess feature readiness against DOR and score 1-100",
        "story_dor_prompt": "Assess story readiness against DOR and score 1-100",
    }
    path = _path("prompts.json")
    try:
        with open(path, "r") as f:
            data = json.load(f)
            p.update(data)
    except Exception:
        pass
    return p

def save_prompts(prompts):
    path = _path("prompts.json")
    with open(path, "w") as f:
        json.dump(prompts, f)
