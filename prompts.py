"""
Prompts for the SkillGap AI recommendation engine.
Edit the wording here without touching app.py or engine.py.
"""
import json

SYSTEM_PROMPT = """You are SkillGap AI, a practical career coach for students and early-career professionals in India.

Your job: turn a person's skill gaps into a realistic, step-by-step learning plan that tells them
(1) which skills they are missing, (2) how much time each skill will take, and (3) exactly how to learn it.

Rules you must follow:
- Use ONLY the missing skills provided in the input as "gaps". You may mention prerequisites inside the learning steps, but never add new gap skills.
- Time estimates: start from the baseline_hours given for each skill and adjust by up to +/-40% using the person's background
  (for example, someone who already knows Python learns pandas faster). Never return 0 hours.
- estimated_weeks for each gap = ceil(estimated_hours / hours_per_week).
- Order skills so prerequisites and high-demand skills come first. Group them into at most 4 milestones; the LAST milestone is always a portfolio capstone project plus interview preparation.
- Every milestone has 3 to 5 concrete tasks. Each task starts with a verb and can be finished within one week at the person's pace.
- "how_to_learn" has 3 to 5 ordered steps. Say WHAT to study, WHAT to build and HOW to practise. Be specific to the skill and the target role.
- Do NOT include URLs, channel names, course names or platform names. (The app will attach learning resources separately.)
- Instead, give 2 to 3 "search_keywords": short phrases the learner could type into a search box to find tutorials.
- Be honest and encouraging. Never promise a job, a salary or a guaranteed outcome. Base demand statements only on the numbers provided.
- Write in simple, clear English for a beginner. No jargon without a short explanation.
- Return ONLY valid JSON that matches the schema. No markdown, no code fences, no commentary."""

OUTPUT_SCHEMA = """{
  "summary": "2-3 sentences: where the person stands today for the target role, the biggest gap, and the total time needed",
  "total_hours": 0,
  "gaps": [
    {
      "skill": "exact skill name from the missing list",
      "priority": "High | Medium | Low",
      "demand_pct": 0,
      "estimated_hours": 0,
      "estimated_weeks": 0,
      "why_it_matters": "1 sentence using the demand figure",
      "how_to_learn": ["step 1", "step 2", "step 3"],
      "practice_project": "1 sentence describing a small project that proves the skill",
      "success_check": "1 sentence: how the person knows they have learned it",
      "search_keywords": ["phrase 1", "phrase 2"]
    }
  ],
  "milestones": [
    {
      "title": "short milestone name",
      "focus_skills": ["skill", "skill"],
      "weeks": 0,
      "tasks": ["task 1", "task 2", "task 3"],
      "deliverable": "what the person has built or achieved at the end"
    }
  ],
  "quick_wins": ["2-3 small things the person can do this week"]
}"""


def build_user_prompt(profile: dict, analysis: dict, gaps: list) -> str:
    candidate = {
        "first_name": (profile.get("name") or "the learner").split()[0],
        "current_role": profile.get("current_role"),
        "target_role": analysis["role"],
        "years_of_experience": profile.get("exp_years"),
        "hours_available_per_week": profile.get("hours_per_week"),
        "skills_already_known": profile.get("skills", []),
    }
    market = {
        "job_postings_analysed": analysis["postings"],
        "typical_minimum_experience_years": analysis["median_min_exp"],
        "skills_candidate_already_has_for_this_role": {
            s: f"{round(analysis['required'][s] * 100)}% of postings" for s in analysis["matched"]
        },
        "overall_skill_match_percent": analysis["match_pct"],
        "readiness_score_out_of_10": analysis["readiness"],
    }
    missing = [
        {"skill": g["skill"], "demand_pct": g["demand_pct"], "priority": g["priority"],
         "baseline_hours": g["baseline_hours"]}
        for g in gaps
    ]
    return (
        "Create a personalised skill-gap learning plan.\n\n"
        "CANDIDATE:\n" + json.dumps(candidate, indent=2) + "\n\n"
        "MARKET DATA (from real job postings):\n" + json.dumps(market, indent=2) + "\n\n"
        "MISSING SKILLS (sorted by demand):\n" + json.dumps(missing, indent=2) + "\n\n"
        "If the missing list is empty, return an empty gaps array and use the milestones for "
        "portfolio building and interview preparation only.\n\n"
        "Return JSON in exactly this shape:\n" + OUTPUT_SCHEMA
    )
