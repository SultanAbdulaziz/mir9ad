from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Annotated, Any, Optional, TypeVar, TypedDict, cast

import pandas as pd
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field
from sklearn.linear_model import LinearRegression

# Always load .env from the same directory as this file, regardless of cwd
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

# ── Supabase ───────────────────────────────────────────────────────────────────
_supabase_client: Any = None

def _get_supabase() -> Any:
    """Lazy-load Supabase client. Returns None if credentials not configured."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client
    # Read env vars here (not at module level) so dotenv is already loaded
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        _supabase_client = create_client(url, key)
        return _supabase_client
    except Exception:
        return None

def _supabase_upsert(table: str, row: dict) -> None:
    """Upsert a row into a Supabase table. Silently skips if client unavailable."""
    sb = _get_supabase()
    if sb is None:
        return
    try:
        sb.table(table).upsert(row, on_conflict="candidate_id").execute()
    except Exception as exc:
        print(f"[supabase {table} write failed: {exc}]", file=sys.stderr)

# ── Model ──────────────────────────────────────────────────────────────────────
# Pro for the two high-stakes calls (CV analysis, final narrative).
# Flash for everything else — ~17× cheaper output, higher RPM, same accuracy on
# structured/rubric tasks. Keeps $25 credits usable across 1,500+ interviews.
_GEMINI_API_KEY   = os.getenv("GEMINI_API_KEY")
_GEMINI_PRO       = "gemini-2.5-pro"    # CV analysis + final evaluation
_GEMINI_FLASH     = "gemini-2.5-flash"  # question selection, scoring, transcription, delivery
_gemini_client: Any = None


def _get_gemini() -> Any:
    """Lazy-load the Gemini client. Returns None if no API key configured."""
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client
    if not _GEMINI_API_KEY:
        return None
    try:
        from google import genai
        _gemini_client = genai.Client(api_key=_GEMINI_API_KEY)
        return _gemini_client
    except ImportError:
        return None


_T = TypeVar("_T", bound=BaseModel)


def _gemini_structured(schema: type[_T], system: str, user: str, model: str = _GEMINI_FLASH) -> _T:
    """
    Call Gemini with structured output + exponential backoff retry.
    Retries up to 5 times on 429 / 503 (high demand) before raising.
    Defaults to Flash; pass model=_GEMINI_PRO for the two high-stakes calls.
    """
    import time

    client = _get_gemini()
    if client is None:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    from google.genai import types as gtypes

    max_retries = 5
    delay       = 2.0   # seconds — doubles each retry

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model,
                contents=[user],
                config=gtypes.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=0,
                ),
            )
            raw = response.text or "{}"
            return schema(**json.loads(raw))
        except Exception as exc:
            msg = str(exc).lower()
            is_retryable = (
                any(x in msg for x in ("429", "503", "quota", "overloaded", "resource_exhausted"))
                or "readerror" in type(exc).__name__.lower()   # httpx.ReadError (errno 35 / EAGAIN)
                or "resource temporarily unavailable" in msg
                or "errno 35" in msg
            )
            if is_retryable and attempt < max_retries - 1:
                wait = delay * (2 ** attempt)
                print(f"[gemini] retryable error (attempt {attempt+1}/{max_retries}): {exc} — retrying in {wait:.1f}s", file=sys.stderr)
                time.sleep(wait)
            else:
                raise

# ── Data ───────────────────────────────────────────────────────────────────────
# _cv_db is used ONLY to train the linear-regression fit-score formula at startup.
# _jd_db and _q_db are operational config (job description + question bank).
# At demo time the candidate's resume comes from an uploaded PDF, never from the CSV.
_DATA = "DATA"
_cv_db = pd.read_csv(f"{_DATA}/Datathon Database - CV Database.csv")
_jd_db = pd.read_csv(f"{_DATA}/Datathon Database - Job Descriptions.csv")
_q_db  = pd.read_csv(f"{_DATA}/Datathon Database - General Questionnaire.csv")

# ── Dimension weights ──────────────────────────────────────────────────────────
WEIGHTS: dict[str, float] = {
    "delivery_ownership":      0.18,
    "leadership_signals":      0.15,
    "business_impact":         0.15,
    "stakeholder_management":  0.12,
    "evidence_credibility":    0.12,
    "pm_readiness":            0.10,
    "strategic_thinking":      0.08,
    "communication_clarity":   0.05,
    "technical_fluency":       0.03,
    "authenticity_confidence": 0.02,
}

# ── Fit Score Formula (from analysis/verify_overfitting.py, R²=0.93) ───────────
# fit_score ≈ intercept + w_exp*years + w_skills*num_skills + w_tools*num_tools
def _count_items(text: Any) -> int:
    if pd.isna(text):
        return 0
    return len([
        x for x in str(text).split(",")
        if x.strip() and x.strip().lower() != "basic communication"
    ])


def _fit_formula() -> tuple[float, float, float, float]:
    df = _cv_db[_cv_db["Candidate Level"] != "Unusual/Surprise"].copy()
    df["Num_Skills"] = cast(Any, df["Core Skills"]).apply(_count_items)
    df["Num_Tools"]  = cast(Any, df["Tools"]).apply(_count_items)
    X = df[["Years Experience", "Num_Skills", "Num_Tools"]]
    y = df["Expected Fit Score"]
    model = LinearRegression().fit(X, y)
    coef = cast(Any, model.coef_).tolist()
    return (
        float(cast(Any, model.intercept_)),
        float(coef[0]),
        float(coef[1]),
        float(coef[2]),
    )


_F_INTERCEPT, _F_W_EXP, _F_W_SKILLS, _F_W_TOOLS = _fit_formula()


def compute_formula_score(years: float, num_skills: int, num_tools: int) -> float:
    raw = _F_INTERCEPT + _F_W_EXP * years + _F_W_SKILLS * num_skills + _F_W_TOOLS * num_tools
    return round(max(0.0, min(100.0, raw)), 1)


# ── Interview structure ────────────────────────────────────────────────────────
GENERAL_OPENING_IDS = []   # Introduction, Motivation
GENERAL_CLOSING_ID  = None               # Final Fit

# Map questionnaire categories to scoring dimensions
_CATEGORY_TO_DIM: dict[str, str] = {
    "Introduction":                    "communication_clarity",
    "Motivation":                      "pm_readiness",
    "Role Understanding":              "pm_readiness",
    "Experience":                      "delivery_ownership",
    "Problem Solving":                 "strategic_thinking",
    "Technical / Functional Knowledge": "technical_fluency",
    "Tools":                           "technical_fluency",
    "Communication":                   "communication_clarity",
    "Teamwork":                        "stakeholder_management",
    "Conflict Handling":               "stakeholder_management",
    "Time Management":                 "delivery_ownership",
    "Learning Ability":                "pm_readiness",
    "Failure / Mistake":               "leadership_signals",
    "Decision Making":                 "leadership_signals",
    "Work Quality":                    "evidence_credibility",
    "Stakeholder Management":          "stakeholder_management",
    "Pressure":                        "leadership_signals",
    "Initiative":                      "leadership_signals",
    "Ethics":                          "leadership_signals",
    "Final Fit":                       "pm_readiness",
}


def _num_personalized(
    risk_flags: list[str],
    dim_scores: dict[str, float],
    formula_score: float,
    llm_weighted: float,
) -> int:
    """Always 2 behavioural personalized questions + 1 skill_test (added separately)."""
    return 2


def _build_interview_plan(num_personalized: int) -> list[str]:
    """Plan: general openings + 2 personalized + 1 skill_test + optional closing."""
    return (
        [f"general:{q}" for q in GENERAL_OPENING_IDS]
        + ["personalized"] * num_personalized
        + ["skill_test"]
        + ([f"general:{GENERAL_CLOSING_ID}"] if GENERAL_CLOSING_ID else [])
    )

# ── State ──────────────────────────────────────────────────────────────────────
class InterviewState(TypedDict):
    candidate_id:    str
    resume_text:     str
    cv_metadata:     dict
    job_description: dict
    question_bank:   list

    cv_dimension_scores: Optional[dict]
    evidence_quotes:     list   # list of {dimension, quote} dicts
    risk_flags:          list
    resume_features:     Optional[dict]   # years_experience, num_skills, num_tools
    formula_score:       Optional[float]  # baseline score from rubric formula

    interview_mode:       bool
    interview_phase:      str
    current_question:     Optional[dict]
    current_answer_audio: Optional[dict]   # transient: {'b64': str, 'mime': str} for the answer in flight
    questions_asked:      list
    dimensions_covered:   list
    interview_plan:       list              # remaining slots: 'general:GQ-XXX' | 'personalized'

    final_evaluation: Optional[dict]
    messages: Annotated[list, add_messages]


# ── Pydantic output schemas ────────────────────────────────────────────────────
class DimensionScoresSchema(BaseModel):
    delivery_ownership:      float = Field(..., ge=0, le=10)
    business_impact:         float = Field(..., ge=0, le=10)
    stakeholder_management:  float = Field(..., ge=0, le=10)
    leadership_signals:      float = Field(..., ge=0, le=10)
    communication_clarity:   float = Field(..., ge=0, le=10)
    technical_fluency:       float = Field(..., ge=0, le=10)
    evidence_credibility:    float = Field(..., ge=0, le=10)
    strategic_thinking:      float = Field(..., ge=0, le=10)
    pm_readiness:            float = Field(..., ge=0, le=10)
    authenticity_confidence: float = Field(..., ge=0, le=10)


class ResumeFeatures(BaseModel):
    """Numeric features used by the linear-regression baseline scorer."""
    years_experience: float = Field(..., ge=0, description="Total years of professional experience inferred from the resume.")
    num_skills:       int   = Field(..., ge=0, description="Count of distinct core skills (not tools). Exclude 'basic communication'.")
    num_tools:        int   = Field(..., ge=0, description="Count of distinct named software tools/platforms (e.g. Jira, MS Project).")


class EvidenceQuote(BaseModel):
    """A direct quote from the resume backing a specific dimension score."""
    dimension: str = Field(..., description="One of: delivery_ownership, business_impact, stakeholder_management, leadership_signals, etc.")
    quote:     str = Field(..., description="Direct quote from the resume text.")


class ExtractedCVFields(BaseModel):
    """Structured fields parsed directly from the resume text."""
    candidate_name:  str = Field(default="", description="Full name of the candidate as written in the resume.")
    field:           str = Field(default="", description="Professional domain: Management | Finance | Marketing | Tech / Data | Tech / Software")
    candidate_level: str = Field(default="", description="Seniority: Strong | Average | Weak — based on years experience and evidence depth.")
    education:       str = Field(default="", description="Highest degree + field, e.g. 'BSc Industrial Engineering'.")
    certification:   str = Field(default="", description="Most relevant certifications, comma-separated. Empty string if none.")
    core_skills:     str = Field(default="", description="Comma-separated professional skills from the resume.")
    tools:           str = Field(default="", description="Comma-separated software tools and platforms from the resume.")


class CVAnalysisOutput(BaseModel):
    dimension_scores:    DimensionScoresSchema
    resume_features:     ResumeFeatures
    extracted_fields:    ExtractedCVFields   = Field(default_factory=ExtractedCVFields)
    evidence_quotes:     list[EvidenceQuote] = Field(default_factory=list)
    risk_flags:          list[str]           = Field(default_factory=list)
    behavioral_summary:  str
    trajectory_analysis: str


class QuestionSelection(BaseModel):
    question_id: str
    question:    str
    dimension:   str
    rationale:   str


class SkillTestSelection(BaseModel):
    skill:       str   # the specific skill from the resume being tested
    question_id: str   # use "ST-001"
    question:    str   # the generated skill-probe question
    dimension:   str   # typically "technical_fluency" or "evidence_credibility"
    rationale:   str


class AnswerScore(BaseModel):
    score:              float = Field(..., ge=0, le=10)
    rationale:          str
    follow_up_needed:   bool
    follow_up_question: str                        = ""
    flags:              list[str]                  = Field(default_factory=list)


class DeliveryScore(BaseModel):
    """Multimodal score derived from the candidate's audio response."""
    score:     float                  = Field(..., ge=0, le=10, description="0-10 delivery quality")
    tone:      float                  = Field(..., ge=0, le=10, description="Vocal tone & energy")
    pace:      float                  = Field(..., ge=0, le=10, description="Speaking pace (penalize too slow / too fast / monotone)")
    confidence: float                 = Field(..., ge=0, le=10, description="Vocal confidence vs nervousness")
    hesitation: float                 = Field(..., ge=0, le=10, description="10 = fluid, 0 = many fillers/pauses")
    flags:     list[str]              = Field(default_factory=list, description="Snake-case flags e.g. reading_from_script, anxious, monotone, evasive, confident, clear")
    notes:     str                    = Field(default="", description="One-sentence observation about delivery")


class FinalEvaluationNarrative(BaseModel):
    """Only the narrative fields — computed scores are injected after."""
    confidence_score:    float       = Field(..., ge=0.0, le=1.0)
    strongest_signals:   list[str]
    weakest_signals:     list[str]
    behavioral_summary:  str
    trajectory_analysis: str
    explanation:         str


# ── Delivery scoring prompt (audio-only path) ─────────────────────────────────
_DELIVERY_PROMPT = """
You are scoring the DELIVERY of a Project Manager interview answer based on the candidate's audio.
You are NOT scoring the content of what they said — only HOW they said it.

Listen for:
- tone:       vocal energy, warmth, engagement (0=flat/disengaged, 10=present and engaged)
- pace:       speaking rate appropriateness (0=too slow/fast/monotone, 10=natural well-paced delivery)
- confidence: vocal confidence (0=anxious/uncertain, 10=composed and assured)
- hesitation: fluency (0=many fillers/long pauses/restarts, 10=fluid clear speech)

Overall `score` = your holistic 0–10 read of delivery quality.

Flags (snake_case, only include what you actually detected):
reading_from_script | anxious | monotone | evasive | confident | clear | rushed | hesitant | engaged | disengaged

`notes`: one sentence observation. Do not judge content correctness.
""".strip()


def score_delivery_from_audio(audio_bytes: bytes, mime_type: str = "audio/webm") -> Optional[dict]:
    """
    Score delivery quality from a candidate's audio response.
    Returns DeliveryScore dict, or None if Gemini is unavailable or call fails.
    """
    client = _get_gemini()
    if client is None:
        return None

    from google.genai import types as gtypes

    try:
        response = client.models.generate_content(
            model=_GEMINI_FLASH,
            contents=[
                gtypes.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                _DELIVERY_PROMPT,
            ],
            config=gtypes.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=DeliveryScore,
                temperature=0.0,
            ),
        )
        raw = response.text or "{}"
        data = json.loads(raw)
        # Validate through Pydantic to clamp and coerce
        return DeliveryScore(**data).model_dump()
    except Exception as exc:
        print(f"[delivery scoring failed: {exc}]", file=sys.stderr)
        return None

# ── Prompts ────────────────────────────────────────────────────────────────────
_SYS_CV_ANALYSIS = """
You are an elite AI recruitment intelligence engine evaluating candidates for PROJECT MANAGER.
You perform deep behavioral analysis — NOT keyword matching. Infer real PM capability from evidence.

Score each of the 10 dimensions (0–10 float):

1. delivery_ownership     — Ownership verbs (led, drove, executed, launched, coordinated). Initiative and execution responsibility.
2. business_impact        — Quantified outcomes ONLY. %, revenue, time saved, KPI gains. "Improved workflows" with no number = low score.
3. stakeholder_management — Cross-functional coordination, executive communication, vendor management, multi-team alignment.
4. leadership_signals     — Strategic thinking, prioritization, decision ownership, navigating ambiguity, directing teams.
5. communication_clarity  — Clear, concise, specific writing. Penalize buzzwords, fluff, generic claims.
6. technical_fluency      — PM tools (Jira, MS Project, Asana, Confluence) and methodologies (Agile, Scrum, PMP, PRINCE2).
7. evidence_credibility   — Only trust claims with context + scale + outcome. Weak claim = low score.
8. strategic_thinking     — Roadmap thinking, business alignment, prioritization frameworks, cross-dept vision.
9. pm_readiness           — Overall readiness: experience level + trajectory + role-specific maturity combined.
10. authenticity_confidence — Detect red flags: keyword stuffing, title inflation (2 yrs exp + "enterprise transformation leader"), tool dumping, unrealistic claims.

Risk flag values (use these exact snake_case strings):
keyword_stuffing | title_inflation | experience_mismatch | vague_impact | tool_dumping | career_instability | seniority_inconsistency | not_serious

not_serious: raise this flag if the candidate is clearly not taking the process seriously — joke answers, one-word responses, refusal to engage, or obvious lack of preparation. This flag triggers a heavy score penalty.

resume_features (used by an independent statistical baseline — be PRECISE):
  - years_experience: sum of years across the candidate's professional roles. Infer from job dates if not stated.
  - num_skills: count of ALL comma-separated items listed under "Core Skills" or similar sections.
            Include everything listed there — including software and tools that appear in that section.
            Only exclude "basic communication". Count exactly what is written, item by item.
  - num_tools:  count of distinct named software/platforms (Jira, Asana, MS Project, Excel, Confluence, etc.).
  
evidence_quotes: list of {dimension, quote} records — pull direct quotes from the resume backing your scores for delivery_ownership, business_impact, stakeholder_management, leadership_signals. One record per quote.
behavioral_summary: 2–3 sentence behavioral profile of this specific candidate.
trajectory_analysis: 1–2 sentence career progression insight.
""".strip()

_SYS_SELECT_QUESTION = """
You are a skilled PM interviewer choosing the next question for a candidate.

Strategy:
- Target uncovered dimensions only — the available questions list is pre-filtered to these dimensions
- Personalize the question using specific details from the resume (mention real companies, projects, or claims)
- Prefer questions that surface depth: specific decisions, tradeoffs, metrics, ownership level
- Avoid repeating what was already covered, including dimensions already addressed

question_id: must be one of the Question IDs from the available questions list.
question: adapt and personalize from the question bank using resume details.
dimension: target dimension name in snake_case.
rationale: why this question for this specific candidate.
""".strip()

_SYS_SKILL_TEST = """
You are generating a targeted skill-probe question for a PM interview.

Your task: pick ONE skill from the candidate's Core Skills list and write a scenario-based question
that tests whether they can actually apply it — not just name it.

Rules:
- Pick a PM-relevant skill (e.g. Agile/Scrum, Risk management, Budget tracking, Stakeholder communication).
  Avoid generic software tools like PowerPoint or Excel.
- The question must reference the specific skill by name.
- Frame it as a specific scenario or challenge, NOT a generic "tell me about a time you used X".
  Example: "You listed Agile/Scrum — your team has just missed two consecutive sprint goals.
  Walk me through how you would diagnose and fix the issue in your next sprint planning."
- Keep it concise: one scenario, one clear ask.

skill: the exact skill name as it appears in the resume.
question_id: use "ST-001".
question: the full question text.
dimension: the scoring dimension (technical_fluency or evidence_credibility).
rationale: why this skill is worth probing for this candidate.
""".strip()

_SYS_SCORE_ANSWER = """
You are scoring a Project Manager interview answer on a 0–10 scale.
Score CONTENT ONLY — what the candidate said, not how they said it.
Vocal delivery, speaking pace, and confidence are scored separately by a dedicated delivery scorer.

Scoring rubric:
- 9–10: Specific example, quantified outcome, clear ownership, decision context, tradeoffs mentioned
- 7–8:  Mostly concrete, good specificity, minor vagueness
- 5–6:  Some substance but generic, lacks metrics or depth
- 3–4:  Vague, buzzword-heavy, no concrete evidence
- 0–2:  Off-topic, refused, or directly contradicts resume claims

rationale: reference specific parts of the answer.
follow_up_needed: true if answer was shallow or vague.
follow_up_question: probing follow-up question if follow_up_needed, else null.
flags: list of red flag strings if any. Include "not_serious" if the candidate gave a joke answer,
  one-word response, laughed through the question, went off-topic, or clearly wasn't attempting to answer.
""".strip()

_SYS_FINALIZE = """
You are writing the narrative section of a PM candidate evaluation report.
The dimension scores and overall fit score are already computed — do NOT invent numbers.
Be specific — quote from the resume and interview answers.

confidence_score (0.0–1.0):
- 0.8–1.0: Strong consistent evidence, no major flags
- 0.5–0.79: Some vagueness or minor inconsistencies
- 0.2–0.49: Multiple flags, inconsistent signals

strongest_signals: exactly 3 specific evidence-backed PM strengths (quote resume text).
weakest_signals:   exactly 3 specific gaps or concerns with evidence.
explanation: 3–4 sentences explaining the hiring decision — sound like executive HR intelligence, not keyword matching.

behavioral_summary: 2–3 sentences synthesizing BOTH CV signals and interview performance.
  Do not re-read the resume — this should reflect how the candidate performed under questioning,
  whether their answers matched their CV claims, and their overall behavioral pattern.
trajectory_analysis: 1–2 sentences on career progression informed by how the candidate
  discussed their experience during the interview, not just what the resume lists.

Note: some Q&A pairs may have null delivery_score (audio was not provided for that answer).
  Only reference delivery quality when delivery_score is present. Do not flag missing delivery data.
""".strip()


# ── Helper ─────────────────────────────────────────────────────────────────────
def _weighted_score(merged: dict[str, float]) -> float:
    return round(sum(merged[d] * WEIGHTS[d] for d in WEIGHTS if d in merged) * 10, 1)


# ── Nodes ──────────────────────────────────────────────────────────────────────

def load_data_node(state: InterviewState) -> dict:
    cid = state["candidate_id"]

    resume_text = state.get("resume_text") or ""
    cv_metadata = state.get("cv_metadata") or {"Candidate ID": cid, "Role": "Project Manager"}

    jd        = _jd_db[_jd_db["Role"] == "Project Manager"].iloc[0].to_dict()
    questions = _q_db.to_dict(orient="records")

    return {
        "resume_text":          resume_text,
        "cv_metadata":          cv_metadata,
        "job_description":      jd,
        "question_bank":        questions,
        "evidence_quotes":      [],
        "risk_flags":           [],
        "questions_asked":      [],
        "dimensions_covered":   [],
        "current_question":     None,
        "current_answer_audio": None,
        "interview_plan":       [],
        "interview_phase":      "cv_analysis",
    }


def analyze_cv_node(state: InterviewState) -> dict:
    meta = state["cv_metadata"]
    jd   = state["job_description"]

    user_msg = (
        f"RESUME TEXT:\n{state['resume_text']}\n\n"
        f"CANDIDATE METADATA:\n{json.dumps(meta, ensure_ascii=False)}\n\n"
        f"JOB DESCRIPTION:\n"
        f"Summary: {jd.get('Role Summary', '')}\n"
        f"Responsibilities: {jd.get('Key Responsibilities', '')}\n"
        f"Required Skills: {jd.get('Required Skills', '')}\n"
        f"Evaluation Focus: {jd.get('Evaluation Focus', '')}"
    )

    result = _gemini_structured(CVAnalysisOutput, _SYS_CV_ANALYSIS, user_msg, model=_GEMINI_PRO)

    features      = result.resume_features
    dim_scores    = result.dimension_scores.model_dump()
    formula_score = compute_formula_score(features.years_experience, features.num_skills, features.num_tools)
    llm_weighted  = _weighted_score(dim_scores)

    if state.get("interview_mode"):
        n_personalized = _num_personalized(result.risk_flags, dim_scores, formula_score, llm_weighted)
        plan = _build_interview_plan(n_personalized)
        phase = "questioning"
    else:
        plan, phase = [], "done"

    # ── Write cv_profiles row ─────────────────────────────────────────────────
    ef = result.extracted_fields
    _supabase_upsert("cv_profiles", {
        "candidate_id":            state["candidate_id"],
        "role":                    meta.get("Role") or jd.get("Role", ""),
        "field":                   ef.field           or meta.get("Field", ""),
        "candidate_level":         ef.candidate_level or meta.get("Candidate Level", ""),
        "candidate_name":          ef.candidate_name  or meta.get("Candidate Name", ""),
        "years_experience":        int(features.years_experience),
        "education":               ef.education       or meta.get("Education", ""),
        "certification":           ef.certification   or meta.get("Certification", ""),
        "core_skills":             ef.core_skills     or meta.get("Core Skills", ""),
        "tools":                   ef.tools           or meta.get("Tools", ""),
        "experience_summary":      result.behavioral_summary,
        "expected_strengths":      "; ".join(q.quote for q in result.evidence_quotes[:3]),
        "expected_weaknesses":     "; ".join(result.risk_flags[:3]),
        "expected_fit_score":      int(formula_score),
        "expected_recommendation": "",
    })

    return {
        "cv_dimension_scores": dim_scores,
        "evidence_quotes":     [q.model_dump() for q in result.evidence_quotes],
        "risk_flags":          result.risk_flags,
        "resume_features":     features.model_dump(),
        "formula_score":       formula_score,
        "interview_plan":      plan,
        "interview_phase":     phase,
        "messages": [AIMessage(
            content=f"[CV analysis — {state['candidate_id']} | formula={formula_score} | "
                    f"llm_weighted={llm_weighted} | plan={plan}]"
        )],
    }


def select_question_node(state: InterviewState) -> dict:
    plan = state.get("interview_plan", [])
    if not plan:
        return {"current_question": None}

    next_slot   = plan[0]
    bank        = state["question_bank"]
    asked_ids   = {q["question_id"] for q in state.get("questions_asked", [])}

    # ── General slot: ask the prescribed question verbatim ───────────────────
    if next_slot.startswith("general:"):
        qid = next_slot.split(":", 1)[1]
        q   = next((r for r in bank if r["Question ID"] == qid), None)
        if q is not None:
            return {"current_question": {
                "question_id": qid,
                "question":    q["Question Text"],
                "dimension":   _CATEGORY_TO_DIM.get(q["Category"], "pm_readiness"),
                "rationale":   f"Standard {q['Category']} question",
                "type":        "general",
            }}
        # Fallback: question id missing from bank — degrade to personalized
        next_slot = "personalized"

    # ── Skill-test slot: LLM picks a skill from resume and writes a probe ─────
    if next_slot == "skill_test":
        ef = (state.get("cv_metadata") or {})
        skill_user_msg = (
            f"CANDIDATE CORE SKILLS: {ef.get('Core Skills', state['resume_text'][:300])}\n\n"
            f"RESUME EXCERPT (first 600 chars):\n{state['resume_text'][:600]}"
        )
        st_result = _gemini_structured(SkillTestSelection, _SYS_SKILL_TEST, skill_user_msg)
        return {"current_question": {**st_result.model_dump(), "type": "skill_test"}}

    # ── Personalized slot: LLM picks + adapts from the bank ──────────────────
    scores    = state.get("cv_dimension_scores") or {}
    covered   = set(state.get("dimensions_covered", []))
    uncovered = sorted([(d, s) for d, s in scores.items() if d not in covered], key=lambda x: x[1])
    weakest   = [d for d, _ in uncovered[:4]]
    # Hard-filter: only offer questions whose dimension hasn't been covered yet.
    # This prevents the LLM from circling back to already-asked topics.
    available = [
        q for q in bank
        if q["Question ID"] not in asked_ids
        and q["Question ID"] not in GENERAL_OPENING_IDS
        and q["Question ID"] != GENERAL_CLOSING_ID
        and _CATEGORY_TO_DIM.get(q.get("Category", ""), "pm_readiness") not in covered
    ]

    # Fallback: if every uncovered-dimension question is exhausted, open the full pool
    if not available:
        available = [
            q for q in bank
            if q["Question ID"] not in asked_ids
            and q["Question ID"] not in GENERAL_OPENING_IDS
            and q["Question ID"] != GENERAL_CLOSING_ID
        ]

    user_msg = (
        f"CV DIMENSION SCORES:\n{json.dumps(scores, indent=2)}\n\n"
        f"DIMENSIONS ALREADY COVERED (do NOT ask about these again): {list(covered)}\n"
        f"WEAKEST UNCOVERED DIMENSIONS (prioritize these): {weakest}\n"
        f"RISK FLAGS: {state.get('risk_flags', [])}\n\n"
        f"RESUME EXCERPT (first 700 chars):\n{state['resume_text'][:700]}\n\n"
        f"AVAILABLE QUESTIONS (all target uncovered dimensions):\n{json.dumps(available, ensure_ascii=False, indent=2)}"
    )

    result = _gemini_structured(QuestionSelection, _SYS_SELECT_QUESTION, user_msg)

    return {"current_question": {**result.model_dump(), "type": "personalized"}}


def ask_question_node(state: InterviewState) -> dict:
    q = state["current_question"] or {}

    # interrupt() returns whatever the API passed via Command(resume=...)
    # Accepts: str  (plain text answer, backward-compatible)
    #          dict {"text": "...", "audio_b64": "...", "audio_mime": "audio/webm"}
    payload = interrupt({"question": q["question"]})

    if isinstance(payload, dict):
        audio_b64   = payload.get("audio_b64")
        audio_mime  = payload.get("audio_mime", "audio/webm")
        audio_state = {"b64": audio_b64, "mime": audio_mime} if audio_b64 else None
        answer_text = ""

        # Transcribe audio → text via Gemini
        if audio_b64:
            import base64
            from google.genai import types as gtypes
            client = _get_gemini()
            if client is not None:
                try:
                    audio_bytes = base64.b64decode(audio_b64)
                    resp = client.models.generate_content(
                        model=_GEMINI_FLASH,
                        contents=[
                            gtypes.Part.from_bytes(data=audio_bytes, mime_type=audio_mime),
                            "Transcribe this audio exactly as spoken. Return only the transcript text, nothing else.",
                        ],
                    )
                    answer_text = (resp.text or "").strip()
                except Exception as exc:
                    print(f"[transcription failed: {exc}]", file=sys.stderr)
    else:
        answer_text  = str(payload)
        audio_state  = None

    return {
        "interview_phase":      "scoring",
        "current_answer_audio": audio_state,
        "messages": [
            AIMessage(content=f"Interviewer: {q['question']}"),
            HumanMessage(content=answer_text),
        ],
    }


def score_answer_node(state: InterviewState) -> dict:
    q          = state["current_question"] or {}
    last_human = next(
        (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), None
    )
    answer = last_human.content if last_human else ""

    user_msg = (
        f"QUESTION: {q.get('question', '')}\n"
        f"DIMENSION: {q.get('dimension', '')}\n"
        f"CANDIDATE ANSWER: {answer}\n\n"
        f"CV SCORE FOR THIS DIMENSION: {(state.get('cv_dimension_scores') or {}).get(q.get('dimension', ''), 'N/A')}\n"
        f"RESUME EXCERPT: {state['resume_text'][:400]}"
    )

    # ── Content score (text-based) ────────────────────────────────────────────
    result = _gemini_structured(AnswerScore, _SYS_SCORE_ANSWER, user_msg)
    content_score = float(result.score)

    # ── Delivery score (audio-based, optional) ────────────────────────────────
    delivery: Optional[dict] = None
    audio_state = state.get("current_answer_audio")
    if audio_state and audio_state.get("b64"):
        import base64
        try:
            audio_bytes = base64.b64decode(audio_state["b64"])
            delivery    = score_delivery_from_audio(audio_bytes, audio_state.get("mime", "audio/webm"))
        except Exception as exc:
            print(f"[audio decode failed: {exc}]", file=sys.stderr)

    # ── Blend: 70% content + 30% delivery (only if delivery available) ───────
    if delivery is not None:
        final_score = round(0.7 * content_score + 0.3 * float(delivery["score"]), 2)
    else:
        final_score = round(content_score, 2)

    qa_pair = {
        "question_id":      q.get("question_id", ""),
        "dimension":        q.get("dimension", ""),
        "question":         q.get("question", ""),
        "type":             q.get("type", "personalized"),
        "answer":           answer,
        "answer_score":     final_score,
        "content_score":    round(content_score, 2),
        "delivery_score":   delivery["score"] if delivery else None,
        "delivery_detail":  delivery,
        "follow_up":        result.follow_up_question if result.follow_up_needed else None,
        "follow_up_answer": None,
    }

    new_plan = state.get("interview_plan", [])[1:]  # pop the slot we just answered

    delivery_flags = delivery.get("flags", []) if delivery else []

    return {
        "questions_asked":     state.get("questions_asked", []) + [qa_pair],
        "dimensions_covered":  state.get("dimensions_covered", []) + [q.get("dimension", "")],
        "interview_plan":      new_plan,
        "risk_flags":          list(dict.fromkeys(
            state.get("risk_flags", []) + result.flags + delivery_flags
        )),
        "current_question":    None,
        "current_answer_audio": None,
        "interview_phase":     "questioning" if new_plan else "done",
    }


def finalize_node(state: InterviewState) -> dict:
    meta      = state.get("cv_metadata", {})
    cv_scores = state.get("cv_dimension_scores") or {}
    qa_pairs  = state.get("questions_asked", [])

    # Average interview scores per dimension
    iv_buckets: dict[str, list] = {}
    for qa in qa_pairs:
        iv_buckets.setdefault(qa["dimension"], []).append(qa["answer_score"])
    iv_scores = {k: sum(v) / len(v) for k, v in iv_buckets.items()}

    # Merge: CV 40% + interview 60% where available
    merged: dict[str, float] = {}
    for dim in WEIGHTS:
        cv_val = float(cv_scores.get(dim, 5.0))
        iv_val = iv_scores.get(dim)
        merged[dim] = round(cv_val * 0.4 + iv_val * 0.6, 2) if iv_val is not None else round(cv_val, 2)

    llm_weighted  = _weighted_score(merged)
    formula_score = state.get("formula_score")

    deduped_flags = list(dict.fromkeys(state.get("risk_flags", [])))

    # not_serious flag — disqualifying: zero behavioral score, ignore CV baseline
    not_serious = "not_serious" in deduped_flags
    if not_serious:
        llm_weighted = 0.0

    # Blend formula (rubric-grounded baseline) with LLM (behavioral) — 50/50
    if formula_score is not None:
        overall = round(0.50 * formula_score + 0.50 * llm_weighted, 1)
    else:
        overall = llm_weighted
    overall = max(0.0, min(100.0, overall))

    # Hard cap — good CV cannot save an unserious candidate
    if not_serious:
        overall = min(overall, 30.0)

    if overall >= 75:
        recommendation = "Recommend"
    elif overall >= 55:
        recommendation = "Recommend with Reservations"
    else:
        recommendation = "Do Not Recommend"

    # Force Do Not Recommend for unserious candidates regardless of score
    if not_serious:
        recommendation = "Do Not Recommend"

    user_msg = (
        f"CANDIDATE: {meta.get('Candidate Name', 'Unknown')} | "
        f"EXP: {meta.get('Years Experience', 'N/A')} yrs\n\n"
        f"DIMENSION SCORES:\n{json.dumps(merged, indent=2)}\n\n"
        f"FORMULA BASELINE: {formula_score} | LLM WEIGHTED: {llm_weighted}\n"
        f"BLENDED OVERALL FIT SCORE: {overall} | RECOMMENDATION: {recommendation}\n\n"
        f"INTERVIEW Q&A:\n"
        + (json.dumps(qa_pairs, ensure_ascii=False, indent=2) if qa_pairs else "CV-only — no interview conducted.")
        + f"\n\nEVIDENCE QUOTES:\n{json.dumps(state.get('evidence_quotes', []), ensure_ascii=False, indent=2)}"
        + f"\n\nRISK FLAGS: {deduped_flags}"
    )

    narrative = _gemini_structured(FinalEvaluationNarrative, _SYS_FINALIZE, user_msg, model=_GEMINI_PRO)

    # Merge LLM narrative with computed values — never trust LLM for numbers
    evaluation: dict = {
        "candidate_id":      meta.get("Candidate ID", state["candidate_id"]),
        "candidate_name":    meta.get("Candidate Name", "Unknown"),
        "predicted_role_fit": "Project Manager",
        "overall_fit_score":  overall,
        "formula_score":      formula_score,
        "llm_weighted_score": llm_weighted,
        "resume_features":    state.get("resume_features"),
        "confidence_score":   narrative.confidence_score,
        "recommendation":     recommendation,
        "risk_flags":         deduped_flags,
        "strongest_signals":  narrative.strongest_signals,
        "weakest_signals":    narrative.weakest_signals,
        "dimension_scores":   merged,
        "behavioral_summary":  narrative.behavioral_summary,
        "trajectory_analysis": narrative.trajectory_analysis,
        "explanation":         narrative.explanation,
        "interview_qa":        qa_pairs,
    }

    # ── Write candidates row ──────────────────────────────────────────────────
    knowledge_skills = round(
        10 * (
            merged.get("delivery_ownership",   5) * 0.35 +
            merged.get("evidence_credibility", 5) * 0.35 +
            merged.get("technical_fluency",    5) * 0.30
        ), 1
    )
    communication = round(merged.get("communication_clarity", 5) * 10, 1)
    uncertainty   = round((1.0 - float(narrative.confidence_score)) * 100, 1)
    # not_serious → maximum uncertainty regardless of LLM confidence reading
    if not_serious:
        uncertainty = 100

    _supabase_upsert("candidates", {
        "candidate_id":               state["candidate_id"],
        "fit_score":                  int(overall),
        "knowledge_and_skills_score": int(knowledge_skills),
        "communication_score":        int(communication),
        "uncertainty_and_risk_score": int(uncertainty),
        "final_recommendation":       recommendation,
        "strengths":                  "; ".join(narrative.strongest_signals),
        "weaknesses":                 "; ".join(narrative.weakest_signals),
        "interview_qa":               json.dumps(qa_pairs, ensure_ascii=False),
    })

    # Also update expected_recommendation in cv_profiles now that we have it
    _supabase_upsert("cv_profiles", {
        "candidate_id":            state["candidate_id"],
        "expected_recommendation": recommendation,
    })

    return {
        "final_evaluation": evaluation,
        "interview_phase":  "done",
        "messages": [AIMessage(content=json.dumps(evaluation, ensure_ascii=False, indent=2))],
    }


# ── Routing ────────────────────────────────────────────────────────────────────
def _route_after_cv(state: InterviewState) -> str:
    if state.get("interview_mode") and state.get("interview_plan"):
        return "select_question"
    return "finalize"


def _route_after_score(state: InterviewState) -> str:
    return "select_question" if state.get("interview_plan") else "finalize"


# ── Graph ──────────────────────────────────────────────────────────────────────
def _build_graph() -> Any:
    b = StateGraph(InterviewState)

    b.add_node("load_data",       load_data_node)
    b.add_node("analyze_cv",      analyze_cv_node)
    b.add_node("select_question", select_question_node)
    b.add_node("ask_question",    ask_question_node)
    b.add_node("score_answer",    score_answer_node)
    b.add_node("finalize",        finalize_node)

    b.add_edge(START,             "load_data")
    b.add_edge("load_data",       "analyze_cv")
    b.add_conditional_edges("analyze_cv",   _route_after_cv)
    b.add_edge("select_question", "ask_question")
    b.add_edge("ask_question",    "score_answer")
    b.add_conditional_edges("score_answer", _route_after_score)
    b.add_edge("finalize",        END)

    return b.compile(checkpointer=MemorySaver())


graph = _build_graph()


# ── PDF parsing ────────────────────────────────────────────────────────────────
def parse_pdf_resume(pdf_bytes: bytes) -> str:
    """Extract text from an uploaded PDF resume."""
    import io
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages  = [(page.extract_text() or "") for page in reader.pages]
    return "\n".join(pages).strip()


# ── API helpers (used by FastAPI layer) ────────────────────────────────────────
def _initial_state(interview_id: str, interview_mode: bool = True) -> InterviewState:
    return {
        "candidate_id":         interview_id,
        "resume_text":          "",
        "cv_metadata":          {},
        "job_description":      {},
        "question_bank":        [],
        "cv_dimension_scores":  None,
        "evidence_quotes":      [],
        "risk_flags":           [],
        "resume_features":      None,
        "formula_score":        None,
        "interview_mode":       interview_mode,
        "interview_phase":      "cv_analysis",
        "current_question":     None,
        "current_answer_audio": None,
        "questions_asked":      [],
        "dimensions_covered":   [],
        "interview_plan":       [],
        "final_evaluation":     None,
        "messages":             [],
    }


def _snapshot_response(interview_id: str) -> dict:
    """Build a normalized API response from the current graph state."""
    config = {"configurable": {"thread_id": interview_id}}
    snap   = graph.get_state(config)
    values = snap.values

    if values.get("final_evaluation"):
        return {
            "interview_id":   interview_id,
            "status":         "complete",
            "candidate_name": (values.get("cv_metadata") or {}).get("Candidate Name"),
            "evaluation":     values["final_evaluation"],
        }

    asked = values.get("questions_asked", [])
    plan  = values.get("interview_plan", [])
    feat  = values.get("resume_features") or {}

    cv_preview = None
    if feat or values.get("cv_dimension_scores"):
        cv_preview = {
            "years_experience": feat.get("years_experience"),
            "num_skills":       feat.get("num_skills"),
            "num_tools":        feat.get("num_tools"),
            "formula_score":    values.get("formula_score"),
            "risk_flags":       values.get("risk_flags", []),
            "dimension_scores": values.get("cv_dimension_scores"),
        }

    return {
        "interview_id":   interview_id,
        "status":         "in_progress" if values.get("current_question") else "ready",
        "candidate_name": (values.get("cv_metadata") or {}).get("Candidate Name"),
        "current_question": values.get("current_question"),
        "progress": {
            "answered":      len(asked),
            "total_planned": len(asked) + len(plan),
        },
        "cv_preview":     cv_preview,
        "questions_asked": asked,
    }


def start_interview(
    interview_id: str,
    resume_text: str,
    candidate_name: str = "Candidate",
    interview_mode: bool = True,
) -> dict:
    """
    Start a new interview thread. Runs CV analysis and pauses at the first question.
    Returns the snapshot response (status='in_progress' with current_question populated).
    """
    config  = {"configurable": {"thread_id": interview_id}}
    initial = _initial_state(interview_id, interview_mode=interview_mode)
    initial["resume_text"] = resume_text
    initial["cv_metadata"] = {
        "Candidate ID":   interview_id,
        "Candidate Name": candidate_name,
        "Role":           "Project Manager",
    }
    graph.invoke(initial, config)
    return _snapshot_response(interview_id)


def submit_answer(
    interview_id: str,
    audio_b64: Optional[str] = None,
    audio_mime: str = "audio/webm",
) -> dict:
    """
    Resume an interrupted interview. Backend transcribes audio via Gemini.
    Returns snapshot response — either next question or final evaluation.
    """
    config  = {"configurable": {"thread_id": interview_id}}
    payload: Any = {}
    if audio_b64:
        payload["audio_b64"]  = audio_b64
        payload["audio_mime"] = audio_mime
    graph.invoke(Command(resume=payload), config)
    return _snapshot_response(interview_id)


def get_interview_snapshot(interview_id: str) -> dict:
    """Fetch current interview state without progressing it."""
    return _snapshot_response(interview_id)
