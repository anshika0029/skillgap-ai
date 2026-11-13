"""
SkillGap AI - Smart Career Navigator (Streamlit UI)

Run:  streamlit run app.py
Logic lives in engine.py, prompts live in prompts.py.
"""
import base64
import html as _html
import re
from datetime import datetime
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

import engine as E

st.set_page_config(page_title="Skill Gap", page_icon="🎯", layout="wide")

TEAL = "#4FD1C5"
TEAL_DARK = "#2FB5A8"
TEXT = "#F0F6FC"
DIM = "#A9B4C6"
CARD = "#2A364A"
GRID = "#3A465C"
AVATAR_FILE = Path(__file__).parent / "avatar.jpg"

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
html, body, .stApp { font-family: 'Inter', sans-serif; }
.stApp { background: radial-gradient(1200px 600px at 50% -10%, #22314a 0%, #141c2b 60%, #0e1420 100%); }
header[data-testid="stHeader"] { background: transparent; }
#MainMenu, footer { visibility: hidden; }
.block-container { padding-top: 1.2rem; max-width: 1400px; }

/* cards */
[data-testid="stVerticalBlockBorderWrapper"] {
  background: rgba(42,54,74,.85); border: 1px solid #38455c; border-radius: 18px;
}
.card-title { font-size: 17px; font-weight: 700; letter-spacing: .4px; color: #F0F6FC; margin: 2px 0 12px 0; }
.sub-title { font-size: 11px; font-weight: 700; letter-spacing: .5px; color: #C9D3E3; margin: 6px 0 2px 0; }

/* top bar */
.topbar { display:flex; align-items:center; justify-content:space-between; padding: 10px 6px 14px 6px; }
.brand { display:flex; align-items:center; gap:12px; font-size: 28px; font-weight: 700; color: #fff; }
.brand .accent { color:#4FD1C5; }
.user { display:flex; align-items:center; gap:12px; font-weight:500; color:#fff; }
.user img, .user .initials { width:48px; height:48px; border-radius:50%; object-fit:cover; border:2px solid #4FD1C5; }
.user .initials { display:flex; align-items:center; justify-content:center; background:#22314a; color:#4FD1C5; font-weight:700; }

/* text bits */
.kv { font-size: 16px; margin: 7px 0; color:#F0F6FC; }
.kv span { color: #A9B4C6; margin-right: 6px; }
.chip { display:inline-block; background:#3A465C; color:#F0F6FC; padding:4px 14px; border-radius:999px; font-size:14px; margin: 3px 6px 3px 0; }
.chip.dim { background:#2f3a4e; color:#A9B4C6; }
.score-box { background:#3A465C; border-radius:12px; padding:12px 18px; display:inline-block; margin-top:10px; }
.score-box .lbl { font-size:12px; font-weight:700; letter-spacing:.5px; color:#C9D3E3; }
.score-box .val { font-size:26px; font-weight:700; text-align:center; }
.note { font-size:12px; color:#A9B4C6; }
.badge { display:inline-block; padding:2px 10px; border-radius:999px; font-size:12px; font-weight:600; }
.badge.high { background:rgba(255,99,132,.18); color:#FF8FA3; }
.badge.medium { background:rgba(255,193,7,.16); color:#FFD166; }
.badge.low { background:rgba(79,209,197,.16); color:#4FD1C5; }

/* timeline */
.tl { display:flex; position:relative; margin: 4px 0 8px 0; }
.tl::before { content:""; position:absolute; top: 38px; left: 8%; right: 8%; height: 3px; background:#2b8f88; }
.tl-item { flex:1; text-align:center; position:relative; font-size:14px; color:#A9B4C6; }
.tl-item .dot { width:22px; height:22px; border-radius:50%; margin: 10px auto 0 auto; background:#2b8f88; border:3px solid #2b8f88; }
.tl-item.done .dot { background:#4FD1C5; border-color:#4FD1C5; }
.tl-item.active { color:#4FD1C5; font-weight:600; }
.tl-item.active .dot { background:#0f2f36; border-color:#4FD1C5; box-shadow:0 0 12px #4FD1C5; }
.ms-title { font-size:15px; font-weight:600; margin-top:6px; }
.ms-next { font-size:13px; color:#A9B4C6; margin-top:6px; }

/* insights */
.ins-title { font-size:16px; font-weight:700; }
.ins-sub { font-size:14px; color:#C9D3E3; }

/* buttons */
.stButton > button { border-radius: 999px; font-weight: 600; padding: .45rem 1.3rem; border: 1px solid #4FD1C5; }
.stButton > button p { color: inherit; }
.stButton > button[kind="primary"], .stButton > button[data-testid="stBaseButton-primary"] {
  background: linear-gradient(135deg, #5fe0d0, #2fb5a8); color: #0c1a24; border: none;
}
.stButton > button[kind="secondary"], .stButton > button[data-testid="stBaseButton-secondary"] {
  background: rgba(79,209,197,.12); color: #4FD1C5;
}
.stButton > button:hover { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(79,209,197,.3); }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def H(markup: str):
    """Render HTML (collapses indentation so Markdown doesn't turn it into a code block)."""
    st.markdown(re.sub(r"\n\s*", "", markup.strip()), unsafe_allow_html=True)


def esc(x) -> str:
    return _html.escape(str(x))


def chips(skills, dim=False) -> str:
    cls = "chip dim" if dim else "chip"
    return "".join(f'<span class="{cls}">{esc(s)}</span>' for s in skills) or '<span class="note">none yet</span>'


@st.cache_data(show_spinner=False)
def get_data():
    df = E.load_jobs()
    return df, sorted(df["role"].unique().tolist()), E.skill_vocabulary(df)


@st.cache_data(show_spinner=False)
def avatar_b64():
    try:
        return base64.b64encode(AVATAR_FILE.read_bytes()).decode()
    except FileNotFoundError:
        return None


def go_to(page: str, focus_gap: str = None):
    st.session_state.page = page
    st.session_state.focus_gap = focus_gap


def persist(profile: dict):
    E.save_user(st.session_state.user, profile)
    st.session_state.profile = profile


def short_name(name: str) -> str:
    parts = name.split()
    return f"{parts[0]} {parts[-1][0].upper()}." if len(parts) > 1 else name


def plotly_base(fig, height):
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=height,
        margin=dict(t=10, b=10, l=10, r=10), font=dict(color=TEXT, family="Inter"),
    )
    return fig


# ----------------------------------------------------------------------
# state, login and saving
# ----------------------------------------------------------------------
def init_state():
    E.configure_storage(_secret("SUPABASE_URL"), _secret("SUPABASE_KEY"))
    if "initialised" not in st.session_state:
        st.session_state.update(initialised=True, user=None, profile=None, page="Dashboard",
                                focus_gap=None, welcome=False)


def login(username: str, password: str):
    """Returns an error string or None."""
    key = E.user_key(username)
    try:
        p = E.load_user(key) if key else None
    except Exception as ex:
        return f"Could not reach the profile storage ({type(ex).__name__}). Please try again."
    if not p or not E.check_pin(password, p.get("pin_hash", "")):
        return "Wrong username or password."
    st.session_state.update(user=key, profile=p, page="Dashboard", welcome=True)
    return None


def logout():
    st.session_state.update(user=None, profile=None, page="Dashboard", focus_gap=None)


def save_profile(form: dict, existing: dict, roles: list, vocab: list):
    """Validate, fuzzy-match, save. Returns an error string or None."""
    role, score, method, suggestions = E.match_role(form["target_input"], roles)
    if role is None:
        return "I couldn't map that to a role in the dataset. Did you mean: " + ", ".join(suggestions) + "?"
    notes = E.normalize_skills(form["skills_raw"], vocab)
    if not notes:
        return "Please enter at least one skill."

    if existing is None:  # new account
        key = E.user_key(form["username"])
        if len(key) < 3:
            return "Username must have at least 3 letters or numbers (a-z, 0-9, . _ -)."
        if len(form["password"]) < 4:
            return "Password must be at least 4 characters."
        try:
            if E.load_user(key) is not None:
                return "That username is already taken. Please choose another one."
        except Exception as ex:
            return f"Could not reach the profile storage ({type(ex).__name__}). Please try again."
        pin_hash = E.hash_pin(form["password"])
    else:
        key, pin_hash = st.session_state.user, existing["pin_hash"]

    if form["target_input"].strip().lower() == role.lower():
        role_note = ""
    elif method == "best guess":
        role_note = f"Best guess: '{form['target_input']}' mapped to {role} ({round(score * 100)}% match). Edit your profile if this is wrong."
    else:
        role_note = f"'{form['target_input']}' mapped to {role} ({round(score * 100)}% match)."

    now = datetime.now().strftime("%d %b %Y, %H:%M")
    profile = {
        "pin_hash": pin_hash, "name": form["name"].strip(), "current_role": form["current_role"].strip(),
        "target_input": form["target_input"].strip(), "matched_role": role, "role_note": role_note,
        "skills_raw": form["skills_raw"], "skill_notes": notes, "skills": [n["skill"] for n in notes],
        "exp_years": form["exp_years"], "hours_per_week": form["hours_per_week"],
        "created": (existing or {}).get("created", now), "updated": now,
    }
    sig = E.profile_signature(profile)
    profile["sig"] = sig
    df, _, _ = get_data()
    if existing and existing.get("sig") == sig and existing.get("plan"):
        profile["plan"] = existing["plan"]
    else:  # profile changed -> instant rule-based plan; AI plan can be generated from the plan page
        analysis = E.analyze(df, role, profile["skills"], profile["exp_years"])
        profile["plan"] = E.rule_based_plan(profile, analysis)
    st.session_state.user = key
    try:
        persist(profile)
    except Exception as ex:
        return f"Could not save your profile ({type(ex).__name__}). Please try again."
    st.session_state.page = "Dashboard"
    return None


def profile_form(existing: dict, roles: list, vocab: list, form_key: str):
    ex = existing or {}
    with st.form(form_key):
        username = password = ""
        if existing is None:
            u1, u2 = st.columns(2)
            username = u1.text_input("Username", placeholder="e.g. ananya.s")
            password = u2.text_input("Password (min 4 characters)", type="password")
        name = st.text_input("Full name", value=ex.get("name", ""), placeholder="e.g. Ananya Sharma")
        c1, c2 = st.columns(2)
        current_role = c1.text_input("Current role", value=ex.get("current_role", ""),
                                     placeholder="e.g. Software Engineer (Junior)")
        target = c2.text_input("Target role", value=ex.get("target_input", ""),
                               placeholder="e.g. data scientist, ml engr, fullstack dev")
        skills_raw = st.text_area("Your current skills (comma-separated)", value=ex.get("skills_raw", ""),
                                  placeholder="python, sql, java", height=90)
        c3, c4 = st.columns(2)
        exp = c3.number_input("Years of experience", 0.0, 30.0, float(ex.get("exp_years", 0.0)), 0.5)
        hpw = c4.slider("Hours you can study per week", 2, 40, int(ex.get("hours_per_week", 8)))
        submitted = st.form_submit_button("Save & analyze" if existing else "Create profile", type="primary")
    if submitted:
        if not name.strip():
            st.error("Please enter your name.")
        elif not target.strip():
            st.error("Please enter a target role.")
        else:
            form = {"username": username, "password": password, "name": name, "current_role": current_role,
                    "target_input": target, "skills_raw": skills_raw, "exp_years": exp, "hours_per_week": hpw}
            err = save_profile(form, existing, roles, vocab)
            if err:
                st.error(err)
            else:
                st.rerun()


# ----------------------------------------------------------------------
# pages
# ----------------------------------------------------------------------
def page_onboarding(roles, vocab):
    H('<div style="text-align:center;margin-top:30px"><div class="brand" style="justify-content:center">'
      '<span class="accent">Skill Gap</span></div>'
      '<p style="color:#A9B4C6;margin-top:10px">Find your skill gaps, see what the market wants, and get a personal learning plan.</p></div>')
    _, mid, _ = st.columns([1, 2, 1])
    with mid, st.container(border=True):
        tab_login, tab_new = st.tabs(["Log in", "Create profile"])
        with tab_login:
            with st.form("login_form"):
                u = st.text_input("Username")
                p = st.text_input("Password", type="password")
                go = st.form_submit_button("Log in", type="primary")
            if go:
                err = login(u, p)
                if err:
                    st.error(err)
                else:
                    st.rerun()
        with tab_new:
            profile_form(None, roles, vocab, "onboarding_form")
            if E.storage_mode() == "local":
                H('<div class="note">Profiles are stored in a local file on this computer.</div>')


def render_header(profile):
    b64 = avatar_b64()
    if b64:
        pic = f'<img src="data:image/jpeg;base64,{b64}"/>'
    else:
        pic = f'<div class="initials">{esc(profile["name"][:1].upper())}</div>'
    H(f'<div class="topbar"><div class="brand"><span class="accent">Skill Gap</span></div>'
      f'<div class="user">{pic}<span>{esc(short_name(profile["name"]))}</span></div></div>')
    pages = ["Dashboard", "Learning Plan", "My Profile"]
    cols = st.columns([1, 1.2, 1, 6])
    for col, p in zip(cols, pages):
        col.button(p, key=f"nav_{p}", type="primary" if st.session_state.page == p else "secondary",
                   on_click=go_to, args=(p,))


def page_dashboard(profile, analysis, df):
    plan = profile["plan"]
    top_l, top_r = st.columns(2, gap="medium")

    # ---- Profile summary -------------------------------------------------
    with top_l, st.container(border=True, height=390):
        H('<div class="card-title">MY PROFILE SUMMARY</div>')
        c1, c2 = st.columns([1.25, 1])
        with c1:
            H(f'<div class="kv"><span>User Name:</span>{esc(profile["name"])}</div>'
              f'<div class="kv"><span>Current Role:</span>{esc(profile["current_role"] or "-")}</div>'
              f'<div class="kv"><span>Target Role:</span>{esc(analysis["role"])}</div>'
              f'<div class="kv"><span>Skills:</span>{chips(profile["skills"][:8])}</div>'
              f'<div class="score-box"><div class="lbl">READINESS SCORE:</div>'
              f'<div class="val">{analysis["readiness"]} / 10</div></div>')
            if profile.get("role_note"):
                H(f'<div class="note" style="margin-top:8px">{esc(profile["role_note"])}</div>')
        with c2:
            fig = go.Figure(go.Pie(
                values=[analysis["match_pct"], 100 - analysis["match_pct"]], hole=0.78, sort=False,
                direction="clockwise", textinfo="none", hoverinfo="skip",
                marker=dict(colors=[TEAL, GRID], line=dict(width=0))))
            fig.add_annotation(text=f"<b style='font-size:34px'>{analysis['match_pct']}%</b>",
                               showarrow=False, font=dict(color=TEXT))
            fig.update_layout(showlegend=False)
            H('<div class="sub-title" style="text-align:center">OVERALL SKILL MATCH</div>')
            st.plotly_chart(plotly_base(fig, 190), config={"displayModeBar": False})
            H(f'<div class="note" style="text-align:center">{esc(analysis["role"])} requirements<br>'
              f'based on {analysis["postings"]} job postings</div>')
            st.button("Update My Skills", key="upd_skills", on_click=go_to, args=("My Profile",))

    # ---- Learning path ---------------------------------------------------
    with top_r, st.container(border=True, height=390):
        H('<div class="card-title">RECOMMENDED LEARNING PATH</div>')
        ms = plan["milestones"]
        items = "".join(f'<div class="tl-item{" active" if i == 0 else ""}">Milestone {i + 1}<div class="dot"></div></div>'
                        for i in range(len(ms)))
        H(f'<div class="tl">{items}</div>')
        H(f'<div class="ms-title">Milestone 1: {esc(ms[0]["title"])}</div>'
          f'<div class="note">About {ms[0]["weeks"]} week(s) · {len(ms[0]["tasks"])} tasks</div>')
        if len(ms) > 1:
            H(f'<div class="ms-next">Next: {esc(ms[1]["title"])}</div>')
        H(f'<div class="note" style="margin:14px 0 16px 0">About {plan["total_weeks"]} weeks in total at '
          f'{profile["hours_per_week"]} hrs/week</div>')
        st.button("View Learning Plan", key="vlp", type="primary", on_click=go_to, args=("Learning Plan",))

    bot_l, bot_r = st.columns(2, gap="medium")

    # ---- Industry demand analytics --------------------------------------
    with bot_l, st.container(border=True, height=470):
        t1, t2, t3 = st.columns([2, 1, 1])
        with t1:
            H('<div class="card-title">INDUSTRY DEMAND ANALYTICS</div>')
        scope = t2.selectbox("Scope", ["Target role", "Whole category"], key="scope_sel")
        level = t3.selectbox("Experience", ["All"] + E.EXPERIENCE_ORDER, key="level_sel")
        view = E.demand_view(df, analysis["role"], "category" if scope == "Whole category" else "role", level)
        g1, g2 = st.columns(2)
        with g1:
            H(f'<div class="sub-title">TOP DEMAND SKILLS ({esc(view["label"]).upper()})</div>')
            top = view["top"]
            fig = go.Figure(go.Bar(x=[s.title() for s in top.index], y=(top.values * 100).round(),
                                   marker_color=TEAL, text=(top.values * 100).round().astype(int),
                                   textposition="outside", cliponaxis=False))
            fig.update_yaxes(title="% of postings", gridcolor=GRID)
            fig.update_xaxes(tickangle=-30)
            st.plotly_chart(plotly_base(fig, 290), config={"displayModeBar": False})
        with g2:
            H('<div class="sub-title">OPENINGS BY EXPERIENCE LEVEL</div>')
            lv = view["levels"]
            fig = go.Figure(go.Scatter(x=lv.index, y=lv.values, mode="lines+markers", fill="tozeroy",
                                       line=dict(color=TEAL, width=3, shape="spline"),
                                       fillcolor="rgba(79,209,197,.18)"))
            fig.update_yaxes(title="postings", gridcolor=GRID)
            st.plotly_chart(plotly_base(fig, 290), config={"displayModeBar": False})
        H(f'<div class="note">Based on {view["postings"]} postings'
          f'{" (limited data for this role)" if analysis["limited_data"] and scope == "Target role" else ""}.</div>')

    # ---- Actionable insights --------------------------------------------
    with bot_r, st.container(border=True, height=470):
        H('<div class="card-title">ACTIONABLE INSIGHTS</div>')
        gaps = plan["gaps"][:3]
        if not gaps:
            H('<div class="ins-sub">You cover all the key skills for this role. Start your capstone project '
              'and begin interview prep.</div>')
            st.button("Open Learning Plan", key="ins_none", type="primary", on_click=go_to, args=("Learning Plan",))
        for i, g in enumerate(gaps):
            with st.container(border=True):
                a, b = st.columns([3.2, 1])
                with a:
                    H(f'<div class="ins-title">Bridge your {esc(g["skill"].title())} gap</div>'
                      f'<div class="ins-sub">Needed in {g["demand_pct"]}% of {esc(analysis["role"])} postings. '
                      f'About {g["estimated_hours"]} hrs, around {g["estimated_weeks"]} weeks at '
                      f'{profile["hours_per_week"]} hrs/week.</div>')
                with b:
                    st.button("View Details", key=f"ins_{i}", type="primary",
                              on_click=go_to, args=("Learning Plan", g["skill"]))


def page_plan(profile, analysis):
    plan = profile["plan"]
    source = "AI plan (Gemini)" if plan.get("source") == "gemini" else "Quick plan (rule-based)"
    H(f'<div class="card-title" style="font-size:22px">YOUR LEARNING PLAN '
      f'<span class="badge low" style="margin-left:8px">{source}</span></div>')
    st.write(plan["summary"])

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Skill match", f'{analysis["match_pct"]}%')
    m2.metric("Skills to learn", len(plan["gaps"]))
    m3.metric("Total study time", f'~{plan["total_hours"]} hrs')
    m4.metric("At your pace", f'~{plan["total_weeks"]} weeks', f'{profile["hours_per_week"]} hrs/week', delta_color="off")

    key = E.gemini_api_key(_secret("GEMINI_API_KEY"))
    label = "Regenerate AI plan" if plan.get("source") == "gemini" else "Generate my AI plan"
    if st.button(label, type="primary", key="gen_ai"):
        if not key:
            st.warning("Add your Gemini key first: set the GEMINI_API_KEY environment variable "
                       "(or put it in .streamlit/secrets.toml) and restart the app.")
        else:
            try:
                with st.spinner("Building your personalised plan..."):
                    new_plan = E.generate_ai_plan(profile, analysis, key)
                profile["plan"] = new_plan
                persist(profile)
                st.rerun()
            except Exception as ex:  # keep the saved plan if the AI call fails
                st.error(f"Could not generate the AI plan ({type(ex).__name__}: {ex}). Your current plan is unchanged.")

    if plan.get("quick_wins"):
        with st.container(border=True):
            H('<div class="card-title">QUICK WINS THIS WEEK</div>')
            for q in plan["quick_wins"]:
                st.markdown(f"- {q}")

    st.subheader("Skills you are missing")
    if not plan["gaps"]:
        st.success("No missing skills for this role. Focus on your portfolio and interviews.")
    focus = st.session_state.get("focus_gap")
    for i, g in enumerate(plan["gaps"]):
        title = f'{g["skill"].title()}  ·  {g["priority"]} priority  ·  ~{g["estimated_hours"]} hrs  ·  ~{g["estimated_weeks"]} weeks'
        with st.expander(title, expanded=(g["skill"] == focus) or (focus is None and i == 0)):
            if g["why_it_matters"]:
                st.write(g["why_it_matters"])
            st.markdown("**How to learn it**")
            for n, step in enumerate(g["how_to_learn"], 1):
                st.markdown(f"{n}. {step}")
            if g["practice_project"]:
                st.markdown(f"**Practice project:** {g['practice_project']}")
            if g["success_check"]:
                st.markdown(f"**You'll know you've got it when:** {g['success_check']}")

    st.subheader("Milestones")
    for i, m in enumerate(plan["milestones"]):
        with st.container(border=True):
            H(f'<div class="ins-title">Milestone {i + 1}: {esc(m["title"])}</div>'
              f'<div class="note">About {m["weeks"]} week(s)</div>')
            for task in m["tasks"]:
                st.markdown(f"- {task}")
            if m.get("deliverable"):
                H(f'<div class="note" style="margin-top:6px"><b>Deliverable:</b> {esc(m["deliverable"])}</div>')


def _secret(name):
    try:
        return st.secrets[name]
    except Exception:
        return None


def page_profile(profile, roles, vocab):
    with st.container(border=True):
        H('<div class="card-title">MY PROFILE</div>')
        H(f'<div class="note">Last updated {esc(profile["updated"])}. '
          f'Change anything below and press Save to refresh your analysis.</div>')
        profile_form(profile, roles, vocab, "profile_form")

    with st.container(border=True):
        H('<div class="card-title">HOW YOUR SKILLS WERE READ</div>')
        rows = ""
        label = {"exact": "recognised", "alias": "recognised", "fuzzy": "spelling corrected", "unknown": "not in our data"}
        for n in profile["skill_notes"]:
            arrow = f' → {esc(n["skill"])}' if n["input"].lower() != n["skill"] else ""
            cls = "chip dim" if n["status"] == "unknown" else "chip"
            rows += f'<span class="{cls}">{esc(n["input"])}{arrow} · {label[n["status"]]}</span>'
        H(rows)

    st.button("Log out", key="logout", on_click=logout)


# ----------------------------------------------------------------------
# main
# ----------------------------------------------------------------------
def main():
    init_state()
    try:
        df, roles, vocab = get_data()
    except FileNotFoundError:
        st.error(f"Dataset not found: {E.DATA_FILE}. Put jobs_clean.csv next to app.py "
                 f"or set the SKILLGAP_DATA environment variable.")
        st.stop()

    user = st.session_state.user
    if not user:
        page_onboarding(roles, vocab)
        return
    profile = st.session_state.profile
    if st.session_state.pop("welcome", False):
        st.toast(f"Welcome back, {profile['name'].split()[0]}!", icon="👋")

    render_header(profile)
    analysis = E.analyze(df, profile["matched_role"], profile["skills"], profile["exp_years"])
    page = st.session_state.page
    if page == "Learning Plan":
        page_plan(profile, analysis)
    elif page == "My Profile":
        page_profile(profile, roles, vocab)
    else:
        page_dashboard(profile, analysis, df)


main()
