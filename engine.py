"""
SkillGap AI - core logic (no Streamlit code in here).

Contains: data loading, fuzzy matching (roles + skills), skill-gap analysis,
the rule-based fallback plan, the Gemini call, and saved-profile storage.
"""
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import tempfile
from difflib import SequenceMatcher, get_close_matches
from pathlib import Path

import pandas as pd

from prompts import SYSTEM_PROMPT, build_user_prompt

BASE_DIR = Path(__file__).parent
DATA_FILE = Path(os.getenv("SKILLGAP_DATA", BASE_DIR / "jobs_clean.csv"))
STORE_FILE = BASE_DIR / "user_data.json"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

EXPERIENCE_ORDER = ["Intern/Fresher", "Entry", "Mid", "Senior"]


# ----------------------------------------------------------------------
# 1. DATA
# ----------------------------------------------------------------------
def load_jobs(path=DATA_FILE) -> pd.DataFrame:
    """Load the master table and add a clean list-of-skills column."""
    df = pd.read_csv(path)
    df["role"] = df["role"].astype(str).str.strip()
    df["skill_list"] = df["skills"].fillna("").apply(
        lambda s: sorted({x.strip().lower() for x in str(s).split(";") if x.strip()})
    )
    return df


def skill_vocabulary(df: pd.DataFrame) -> list:
    return sorted({s for lst in df["skill_list"] for s in lst})


# ----------------------------------------------------------------------
# 2. FUZZY MATCHING
# ----------------------------------------------------------------------
ROLE_ALIASES = {
    "ml engineer": "Machine Learning Engineer",
    "machine learning": "Machine Learning Engineer",
    "ml": "Machine Learning Engineer",
    "ai ml engineer": "Machine Learning Engineer",
    "data science": "Data Scientist",
    "sde": "Software Engineer",
    "swe": "Software Engineer",
    "software developer": "Software Engineer",
    "full stack": "Full Stack Developer",
    "fullstack developer": "Full Stack Developer",
    "front end developer": "Frontend Developer",
    "react developer": "Frontend Developer",
    "back end developer": "Backend Developer",
    "devops": "DevOps Engineer",
    "genai engineer": "Generative AI Engineer",
    "gen ai engineer": "Generative AI Engineer",
    "ai developer": "AI Engineer",
    "sdet": "Test Automation Engineer (SDET)",
    "tester": "QA Engineer",
    "power bi developer": "BI Developer",
    "bi analyst": "BI Developer",
    "ux designer": "UI/UX Designer",
    "ui designer": "UI/UX Designer",
}

SKILL_ALIASES = {
    "ml": "machine learning",
    "dl": "deep learning",
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "powerbi": "power bi",
    "power-bi": "power bi",
    "k8s": "kubernetes",
    "gen ai": "generative ai",
    "genai": "generative ai",
    "large language models": "llm",
    "natural language processing": "nlp",
    "scikit learn": "scikit-learn",
    "sklearn": "scikit-learn",
    "amazon web services": "aws",
    "google cloud": "gcp",
    "ms excel": "excel",
    "microsoft excel": "excel",
    "node": "node.js",
    "nodejs": "node.js",
    "reactjs": "react",
    "react.js": "react",
}


TOKEN_FIXES = {"engr": "engineer", "eng": "engineer", "dev": "developer", "devs": "developer",
               "sci": "scientist", "mgr": "manager", "admin": "administrator"}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+#.]+", " ", str(text).lower())).strip()


def _norm_role(text: str) -> str:
    return " ".join(TOKEN_FIXES.get(t, t) for t in _norm(text).split())


def _role_score(query: str, role: str) -> float:
    q, r = _norm_role(query), _norm_role(role)
    if q == r:
        return 1.0
    ratio = SequenceMatcher(None, q, r).ratio()
    tq, tr = set(q.split()), set(r.split())
    if not tq or not tr:
        return ratio
    inter = len(tq & tr)
    contain = inter / len(tq)
    jaccard = inter / len(tq | tr)
    return max(ratio, 0.6 * contain + 0.4 * jaccard)


def match_role(query: str, roles: list):
    """
    Fuzzy-match free text to a role in the dataset.
    Returns (role_or_None, score 0-1, method, top3 suggestions).
    """
    q = _norm_role(query)
    if not q:
        return None, 0.0, "empty", []
    for alias, target in ROLE_ALIASES.items():
        if q == alias and target in roles:
            return target, 1.0, "alias", [target]
    scored = sorted(((_role_score(query, r), r) for r in roles), reverse=True)
    suggestions = [r for _, r in scored[:3]]
    best_score, best = scored[0]
    if best_score >= 0.999:
        method = "exact"
    elif best_score >= 0.75:
        method = "close match"
    elif best_score >= 0.55:
        method = "best guess"
    else:
        return None, best_score, "no match", suggestions
    return best, best_score, method, suggestions


def normalize_skills(raw: str, vocab: list):
    """
    Turn 'pyton, ML, powerbi, communication' into clean skills.
    Returns list of dicts: {input, skill, status} where status is
    exact | alias | fuzzy | unknown.
    """
    vocab_set = set(vocab)
    out, seen = [], set()
    for token in re.split(r"[,;\n|/]+", raw or ""):
        original = token.strip()
        t = _norm(original)
        if not t:
            continue
        skill, status = t, "unknown"
        if t in vocab_set:
            status = "exact"
        elif t in SKILL_ALIASES and SKILL_ALIASES[t] in vocab_set:
            skill, status = SKILL_ALIASES[t], "alias"
        elif len(t) > 3:  # very short tokens are too risky to fuzzy match
            hit = get_close_matches(t, vocab, n=1, cutoff=0.82)
            if hit:
                skill, status = hit[0], "fuzzy"
        if skill in seen:
            continue
        seen.add(skill)
        out.append({"input": original, "skill": skill, "status": status})
    return out


# ----------------------------------------------------------------------
# 3. ANALYSIS
# ----------------------------------------------------------------------
def _demand(sub: pd.DataFrame) -> pd.Series:
    """Share of postings (0-1) that mention each skill."""
    n = len(sub)
    if n == 0:
        return pd.Series(dtype=float)
    counts = sub["skill_list"].explode().dropna().value_counts()
    return (counts / n).sort_values(ascending=False)


def analyze(df: pd.DataFrame, role: str, user_skills: list, exp_years: float):
    sub = df[df["role"] == role]
    n = len(sub)
    demand = _demand(sub)
    required = demand[demand >= 0.10].head(12)
    if len(required) < 8:
        required = demand.head(8)

    user_set = set(user_skills)
    matched = [s for s in required.index if s in user_set]
    missing = [s for s in required.index if s not in user_set]

    total_w = float(required.sum()) or 1.0
    coverage = float(required[matched].sum()) / total_w if len(required) else 0.0

    med_exp = sub["min_exp"].dropna().median() if sub["min_exp"].notna().any() else 0
    med_exp = 0 if pd.isna(med_exp) else float(med_exp)
    exp_factor = min(1.0, exp_years / med_exp) if med_exp > 0 else 1.0
    readiness = round(10 * (0.75 * coverage + 0.25 * exp_factor), 1)

    salaries = sub["salary_lpa"].dropna()
    return {
        "role": role,
        "postings": n,
        "required": {s: round(float(required[s]), 3) for s in required.index},
        "matched": matched,
        "missing": missing,
        "extra": sorted(user_set - set(required.index)),
        "match_pct": round(coverage * 100),
        "readiness": readiness,
        "median_min_exp": round(med_exp, 1),
        "median_salary_lpa": round(float(salaries.median()), 1) if len(salaries) >= 5 else None,
        "limited_data": n < 15,
    }


def demand_view(df: pd.DataFrame, role: str, scope: str, level: str):
    """Data for the demand charts. scope: 'role' or 'category'."""
    if scope == "category":
        cat = df.loc[df["role"] == role, "category"].iloc[0]
        sub = df[df["category"] == cat]
        label = cat
    else:
        sub = df[df["role"] == role]
        label = role
    if level != "All":
        lv = sub[sub["experience_level"] == level]
        if len(lv) >= 5:
            sub = lv
    top = _demand(sub).head(6)
    lv_counts = sub["experience_level"].value_counts().reindex(EXPERIENCE_ORDER).fillna(0).astype(int)
    return {"label": label, "postings": len(sub), "top": top, "levels": lv_counts}


# ----------------------------------------------------------------------
# 4. PLAN (rule-based fallback + Gemini)
# ----------------------------------------------------------------------
BASE_HOURS = {
    "python": 60, "sql": 30, "java": 70, "javascript": 60, "typescript": 30, "c++": 70,
    "r": 40, "go": 50, "rust": 80, "machine learning": 80, "deep learning": 80, "nlp": 60,
    "generative ai": 40, "llm": 40, "rag": 25, "computer vision": 60, "statistics": 50,
    "pandas": 20, "numpy": 15, "scikit-learn": 25, "tensorflow": 40, "pytorch": 40,
    "power bi": 30, "tableau": 30, "excel": 20, "data analysis": 40, "data modeling": 30,
    "data visualization": 20, "etl": 30, "spark": 50, "kafka": 35, "airflow": 25,
    "aws": 50, "azure": 50, "gcp": 50, "docker": 20, "kubernetes": 40, "terraform": 30,
    "git": 10, "linux": 30, "rest api": 20, "react": 50, "node.js": 40, "agile": 8,
    "software testing": 25, "project management": 30, "cloud computing": 30,
    "data structures": 60, "system design": 50, "microservices": 35,
}
SOFT_KEYWORDS = ("management", "communication", "agile", "scrum", "documentation", "stakeholder")


def baseline_hours(skill: str) -> int:
    if skill in BASE_HOURS:
        return BASE_HOURS[skill]
    if any(k in skill for k in SOFT_KEYWORDS):
        return 12
    return 30


def priority_of(demand: float) -> str:
    return "High" if demand >= 0.40 else "Medium" if demand >= 0.20 else "Low"


def gap_table(analysis: dict, hours_per_week: float) -> list:
    rows = []
    for s in analysis["missing"]:
        d = analysis["required"][s]
        h = baseline_hours(s)
        rows.append({
            "skill": s, "demand_pct": round(d * 100), "priority": priority_of(d),
            "baseline_hours": h, "baseline_weeks": math.ceil(h / max(hours_per_week, 1)),
        })
    rows.sort(key=lambda r: -r["demand_pct"])
    return rows


def rule_based_plan(profile: dict, analysis: dict) -> dict:
    hpw = max(float(profile["hours_per_week"]), 1)
    role = analysis["role"]
    gaps = []
    for g in gap_table(analysis, hpw):
        s = g["skill"]
        gaps.append({
            "skill": s, "priority": g["priority"], "demand_pct": g["demand_pct"],
            "estimated_hours": g["baseline_hours"], "estimated_weeks": g["baseline_weeks"],
            "why_it_matters": f"{s.title()} appears in {g['demand_pct']}% of {role} postings analysed.",
            "how_to_learn": [
                f"Learn the core concepts and terminology of {s}.",
                f"Follow one structured beginner course or the official documentation for {s}.",
                f"Build a small hands-on project that uses {s}.",
                f"Revise with 10-15 interview-style questions on {s}.",
            ],
            "practice_project": f"Build a mini {role} project that uses {s} and publish it on GitHub.",
            "success_check": f"You can use {s} in a project without looking up the basics.",
            "search_keywords": [f"{s} for beginners", f"{s} project {role.lower()}"],
        })

    # 3 skill milestones + 1 capstone
    groups = [[] for _ in range(min(3, max(len(gaps), 1)))]
    for i, g in enumerate(gaps):
        groups[i * len(groups) // max(len(gaps), 1)].append(g)
    milestones = []
    for i, grp in enumerate([g for g in groups if g], start=1):
        hrs = sum(g["estimated_hours"] for g in grp)
        names = [g["skill"] for g in grp]
        tasks = []
        for g in grp:
            tasks += [f"Learn the fundamentals of {g['skill']}", f"Build a mini project using {g['skill']}"]
        milestones.append({
            "title": f"Learn {', '.join(n.title() for n in names)}",
            "focus_skills": names, "weeks": math.ceil(hrs / hpw), "tasks": tasks[:6],
            "deliverable": f"A small working project that uses {', '.join(names)}.",
        })
    total_skill_hours = sum(g["estimated_hours"] for g in gaps)
    cap_hours = max(10, round(total_skill_hours * 0.15))
    milestones.append({
        "title": "Portfolio project & interview prep", "focus_skills": [g["skill"] for g in gaps][:5],
        "weeks": math.ceil(cap_hours / hpw),
        "tasks": [f"Plan a {role} capstone project", "Build and document the project on GitHub",
                  "Write 3 resume bullets from the project", "Practice 10 interview questions"],
        "deliverable": f"A published {role} portfolio project.",
    })
    total_hours = total_skill_hours + cap_hours
    return {
        "source": "rule-based",
        "summary": (f"You match {analysis['match_pct']}% of the key skills for {role}. "
                    f"Closing {len(gaps)} gap(s) needs roughly {total_hours} hours."),
        "total_hours": total_hours,
        "total_weeks": math.ceil(total_hours / hpw),
        "gaps": gaps,
        "milestones": milestones,
        "quick_wins": [f"Spend your first session on {gaps[0]['skill']}." if gaps else "Start your capstone project."],
    }


def gemini_api_key(secrets_value=None):
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or secrets_value


def _clean_plan(raw: dict, fallback: dict, hpw: float) -> dict:
    """Keep what the model returned if it is well-formed, otherwise fall back per-field."""
    plan = {"source": "gemini"}
    plan["summary"] = str(raw.get("summary") or fallback["summary"])
    gaps = []
    for g in raw.get("gaps") or []:
        if not isinstance(g, dict) or not g.get("skill"):
            continue
        hrs = int(float(g.get("estimated_hours") or 0)) or baseline_hours(str(g["skill"]).lower())
        steps = g.get("how_to_learn")
        gaps.append({
            "skill": str(g["skill"]).lower(),
            "priority": g.get("priority") if g.get("priority") in ("High", "Medium", "Low") else "Medium",
            "demand_pct": int(float(g.get("demand_pct") or 0)),
            "estimated_hours": hrs,
            "estimated_weeks": math.ceil(hrs / max(hpw, 1)),
            "why_it_matters": str(g.get("why_it_matters") or ""),
            "how_to_learn": [str(x) for x in steps] if isinstance(steps, list) else [],
            "practice_project": str(g.get("practice_project") or ""),
            "success_check": str(g.get("success_check") or ""),
            "search_keywords": [str(x) for x in (g.get("search_keywords") or [])][:3],
        })
    plan["gaps"] = gaps or fallback["gaps"]
    ms = []
    for m in (raw.get("milestones") or [])[:4]:
        if isinstance(m, dict) and m.get("title") and isinstance(m.get("tasks"), list) and m["tasks"]:
            ms.append({
                "title": str(m["title"]),
                "focus_skills": [str(x) for x in (m.get("focus_skills") or [])],
                "weeks": int(float(m.get("weeks") or 1)) or 1,
                "tasks": [str(t) for t in m["tasks"]][:6],
                "deliverable": str(m.get("deliverable") or ""),
            })
    plan["milestones"] = ms or fallback["milestones"]
    plan["total_weeks"] = sum(m["weeks"] for m in plan["milestones"])
    skill_hours = sum(g["estimated_hours"] for g in plan["gaps"])
    plan["total_hours"] = int(float(raw.get("total_hours") or 0)) or skill_hours
    qw = raw.get("quick_wins")
    plan["quick_wins"] = [str(x) for x in qw][:3] if isinstance(qw, list) and qw else fallback["quick_wins"]
    return plan


def generate_ai_plan(profile: dict, analysis: dict, api_key: str) -> dict:
    """Call Gemini with the prompt from prompts.py. Raises on failure (UI shows the message)."""
    from google import genai
    from google.genai import types

    hpw = max(float(profile["hours_per_week"]), 1)
    fallback = rule_based_plan(profile, analysis)
    prompt = build_user_prompt(profile, analysis, gap_table(analysis, hpw))
    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            temperature=0.4,
        ),
    )
    text = (resp.text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text).strip()
    return _clean_plan(json.loads(text), fallback, hpw)


# ----------------------------------------------------------------------
# 5. SAVED PROFILES  (username + password login, one profile per user)
#    - Online: Supabase table "profiles" (set SUPABASE_URL and SUPABASE_KEY)
#    - Local testing: falls back to user_data.json next to the app
# ----------------------------------------------------------------------
_CFG = {"url": None, "key": None}


def configure_storage(url=None, key=None):
    u = (url or os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    k = (key or os.getenv("SUPABASE_KEY") or "").strip()
    _CFG["url"], _CFG["key"] = (u or None), (k or None)


def storage_mode() -> str:
    return "supabase" if _CFG["url"] and _CFG["key"] else "local"


def user_key(username: str) -> str:
    return re.sub(r"[^a-z0-9_.-]", "", str(username).strip().lower())


def hash_pin(pin: str) -> str:
    salt = secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt.encode(), 100_000).hex()
    return f"{salt}${digest}"


def check_pin(pin: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$")
    except ValueError:
        return False
    test = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt.encode(), 100_000).hex()
    return hmac.compare_digest(test, digest)


def _sb_headers(extra=None):
    h = {"apikey": _CFG["key"], "Authorization": f"Bearer {_CFG['key']}",
         "Content-Type": "application/json"}
    h.update(extra or {})
    return h


def _local_read() -> dict:
    try:
        with open(STORE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("users", {})
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {"users": {}}


def _local_write(data: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=str(BASE_DIR), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, STORE_FILE)


def load_user(key: str):
    """Return the saved profile dict for a username, or None."""
    if storage_mode() == "supabase":
        import requests
        r = requests.get(f"{_CFG['url']}/rest/v1/profiles", headers=_sb_headers(),
                         params={"username": f"eq.{key}", "select": "data"}, timeout=10)
        r.raise_for_status()
        rows = r.json()
        return rows[0]["data"] if rows else None
    return _local_read()["users"].get(key)


def save_user(key: str, profile: dict) -> None:
    if storage_mode() == "supabase":
        import requests
        r = requests.post(f"{_CFG['url']}/rest/v1/profiles",
                          headers=_sb_headers({"Prefer": "resolution=merge-duplicates"}),
                          json={"username": key, "data": profile}, timeout=10)
        r.raise_for_status()
        return
    data = _local_read()
    data["users"][key] = profile
    _local_write(data)


def profile_signature(p: dict) -> str:
    raw = json.dumps([p.get("matched_role"), sorted(p.get("skills", [])),
                      p.get("hours_per_week"), p.get("exp_years")])
    return hashlib.md5(raw.encode()).hexdigest()[:12]
