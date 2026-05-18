from __future__ import annotations

import json
import os
import sys
from typing import Annotated, Any, Optional, TypedDict, cast

import pandas as pd
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field, SecretStr
from sklearn.linear_model import LinearRegression

load_dotenv()

# ── Models ─────────────────────────────────────────────────────────────────────
llm = ChatOpenAI(
    model="gpt-4o",
    api_key=SecretStr(os.getenv("GITHUB_TOKEN") or ""),
    base_url=os.getenv("GITHUB_API_URL"),
    temperature=0,
)

# Gemini client for multimodal (audio) delivery scoring — lazy init, optional
_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
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

# ── Data ───────────────────────────────────────────────────────────────────────
_DATA = "DATA"
_cv_db     = pd.read_csv(f"{_DATA}/Datathon Database - CV Database.csv")
_resume_db = pd.read_csv(f"{_DATA}/Datathon Database - Resume Text.csv")
_jd_db     = pd.read_csv(f"{_DATA}/Datathon Database - Job Descriptions.csv")
_q_db      = pd.read_csv(f"{_DATA}/Datathon Database - General Questionnaire.csv")
_pm135     = pd.read_csv(f"{_DATA}/PROJECT MANAGER 135 csv.csv")

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
GENERAL_OPENING_IDS = ["GQ-001", "GQ-002"]   # Introduction, Motivation
GENERAL_CLOSING_ID  = "GQ-020"               # Final Fit

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
    """1-5 personalized questions based on CV uncertainty signals."""
    n = 1
    n += min(len(risk_flags), 2)
    n += min(sum(1 for s in dim_scores.values() if s < 6), 2)
    if abs(formula_score - llm_weighted) > 15:
        n += 1
    return max(1, min(5, n))


def _build_interview_plan(num_personalized: int) -> list[str]:
    """Returns list like ['general:GQ-001', 'general:GQ-002', 'personalized', ..., 'general:GQ-020']."""
    return (
        [f"general:{q}" for q in GENERAL_OPENING_IDS]
        + ["personalized"] * num_personalized
        + [f"general:{GENERAL_CLOSING_ID}"]
    )

# ── State ──────────────────────────────────────────────────────────────────────
class InterviewState(TypedDict):
    candidate_id:    str
    resume_text:     str
    cv_metadata:     dict
    job_description: dict
    question_bank:   list

    cv_dimension_scores: Optional[dict]
    evidence_quotes:     dict
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


class CVAnalysisOutput(BaseModel):
    dimension_scores:    DimensionScoresSchema
    resume_features:     ResumeFeatures
    evidence_quotes:     dict[str, list[str]] = Field(default_factory=dict)
    risk_flags:          list[str]            = Field(default_factory=list)
    behavioral_summary:  str
    trajectory_analysis: str


class QuestionSelection(BaseModel):
    question_id: str
    question:    str
    dimension:   str
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


# ── Structured LLM chains (module-level, built once) ──────────────────────────
_cv_llm       = llm.with_structured_output(CVAnalysisOutput,        method="function_calling")
_question_llm = llm.with_structured_output(QuestionSelection,       method="function_calling")
_score_llm    = llm.with_structured_output(AnswerScore,             method="function_calling")
_finalize_llm = llm.with_structured_output(FinalEvaluationNarrative, method="function_calling")


_GEMINI_MODEL = "gemini-2.0-flash"
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
    Score delivery quality from a candidate's audio response using Gemini 2.0 Flash.
    Returns DeliveryScore dict, or None if Gemini is unavailable or call fails.
    """
    client = _get_gemini()
    if client is None:
        return None

    from google.genai import types as gtypes

    try:
        response = client.models.generate_content(
            model=_GEMINI_MODEL,
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
keyword_stuffing | title_inflation | experience_mismatch | vague_impact | tool_dumping | career_instability | seniority_inconsistency

resume_features (used by an independent statistical baseline — be PRECISE):
  - years_experience: sum of years across the candidate's professional roles. Infer from job dates if not stated.
  - num_skills: count of distinct core/professional skills under "Core Skills" or similar sections.
                Do NOT count tools/software here. Exclude generic items like "basic communication".
  - num_tools:  count of distinct named software/platforms (Jira, Asana, MS Project, Excel, Confluence, etc.).

evidence_quotes: pull direct quotes from the resume for delivery_ownership, business_impact, stakeholder_management, leadership_signals.
behavioral_summary: 2–3 sentence behavioral profile of this specific candidate.
trajectory_analysis: 1–2 sentence career progression insight.
""".strip()

_SYS_SELECT_QUESTION = """
You are a skilled PM interviewer choosing the next question for a candidate.

Strategy:
- Target the weakest uncovered dimensions first
- Personalize the question using specific details from the resume (mention real companies, projects, or claims)
- Prefer questions that surface depth: specific decisions, tradeoffs, metrics, ownership level
- Avoid repeating what was already covered

question_id: must be one of the Question IDs from the available questions list.
question: adapt and personalize from the question bank using resume details.
dimension: target dimension name in snake_case.
rationale: why this question for this specific candidate.
""".strip()

_SYS_SCORE_ANSWER = """
You are scoring a Project Manager interview answer on a 0–10 scale.

Scoring rubric:
- 9–10: Specific example, quantified outcome, clear ownership, decision context, tradeoffs mentioned
- 7–8:  Mostly concrete, good specificity, minor vagueness
- 5–6:  Some substance but generic, lacks metrics or depth
- 3–4:  Vague, buzzword-heavy, no concrete evidence
- 0–2:  Off-topic, refused, or directly contradicts resume claims

rationale: reference specific parts of the answer.
follow_up_needed: true if answer was shallow or vague.
follow_up_question: probing follow-up question if follow_up_needed, else null.
flags: list of red flag strings if any.
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
""".strip()


# ── Helper ─────────────────────────────────────────────────────────────────────
def _weighted_score(merged: dict[str, float]) -> float:
    return round(sum(merged[d] * WEIGHTS[d] for d in WEIGHTS if d in merged) * 10, 1)


# ── Nodes ──────────────────────────────────────────────────────────────────────

def load_data_node(state: InterviewState) -> dict:
    cid = state["candidate_id"]

    # Honor pre-supplied resume text (e.g. from PDF upload via API)
    resume_text = state.get("resume_text") or ""
    if not resume_text:
        resume_row = _pm135[_pm135["Candidate ID"] == cid]
        if resume_row.empty:
            resume_row = _resume_db[_resume_db["Candidate ID"] == cid]
        resume_text = str(cast(Any, resume_row["Resume Text"]).iloc[0]) if not resume_row.empty else ""

    # Honor pre-supplied metadata (e.g. {"Candidate Name": "Alice"} from API)
    cv_metadata = state.get("cv_metadata") or {}
    if not cv_metadata or set(cv_metadata.keys()) <= {"Candidate ID", "Candidate Name", "Role"}:
        meta_row = _cv_db[_cv_db["Candidate ID"] == cid]
        if not meta_row.empty:
            db_meta = meta_row.iloc[0].to_dict()
            cv_metadata = {**db_meta, **cv_metadata}  # caller's values win
        elif not cv_metadata:
            cv_metadata = {"Candidate ID": cid, "Role": "Project Manager"}

    jd        = _jd_db[_jd_db["Role"] == "Project Manager"].iloc[0].to_dict()
    questions = _q_db.to_dict(orient="records")

    return {
        "resume_text":          resume_text,
        "cv_metadata":          cv_metadata,
        "job_description":      jd,
        "question_bank":        questions,
        "evidence_quotes":      {},
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

    result = cast(CVAnalysisOutput, _cv_llm.invoke(
        [SystemMessage(content=_SYS_CV_ANALYSIS), HumanMessage(content=user_msg)]
    ))

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

    return {
        "cv_dimension_scores": dim_scores,
        "evidence_quotes":     result.evidence_quotes,
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

    # ── Personalized slot: LLM picks + adapts from the bank ──────────────────
    scores    = state.get("cv_dimension_scores") or {}
    covered   = set(state.get("dimensions_covered", []))
    uncovered = sorted([(d, s) for d, s in scores.items() if d not in covered], key=lambda x: x[1])
    weakest   = [d for d, _ in uncovered[:4]]
    available = [
        q for q in bank
        if q["Question ID"] not in asked_ids
        and q["Question ID"] not in GENERAL_OPENING_IDS
        and q["Question ID"] != GENERAL_CLOSING_ID
    ]

    user_msg = (
        f"CV DIMENSION SCORES:\n{json.dumps(scores, indent=2)}\n\n"
        f"DIMENSIONS ALREADY COVERED: {list(covered)}\n"
        f"WEAKEST UNCOVERED DIMENSIONS: {weakest}\n"
        f"RISK FLAGS: {state.get('risk_flags', [])}\n\n"
        f"RESUME EXCERPT (first 700 chars):\n{state['resume_text'][:700]}\n\n"
        f"AVAILABLE QUESTIONS:\n{json.dumps(available, ensure_ascii=False, indent=2)}"
    )

    result = cast(QuestionSelection, _question_llm.invoke(
        [SystemMessage(content=_SYS_SELECT_QUESTION), HumanMessage(content=user_msg)]
    ))

    return {"current_question": {**result.model_dump(), "type": "personalized"}}


def ask_question_node(state: InterviewState) -> dict:
    q = state["current_question"] or {}

    # interrupt() returns whatever the API passed via Command(resume=...)
    # Accepts: str  (plain text answer, backward-compatible)
    #          dict {"text": "...", "audio_b64": "...", "audio_mime": "audio/webm"}
    payload = interrupt({"question": q["question"]})

    if isinstance(payload, dict):
        answer_text  = str(payload.get("text", ""))
        audio_b64    = payload.get("audio_b64")
        audio_mime   = payload.get("audio_mime", "audio/webm")
        audio_state  = {"b64": audio_b64, "mime": audio_mime} if audio_b64 else None
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
    result = cast(AnswerScore, _score_llm.invoke(
        [SystemMessage(content=_SYS_SCORE_ANSWER), HumanMessage(content=user_msg)]
    ))
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
        "risk_flags":          state.get("risk_flags", []) + result.flags + delivery_flags,
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
    # Blend formula (rubric-grounded baseline) with LLM (behavioral) — 50/50
    if formula_score is not None:
        overall = round(0.5 * formula_score + 0.5 * llm_weighted, 1)
    else:
        overall = llm_weighted
    overall = max(0.0, min(100.0, overall))

    if overall >= 75:
        recommendation = "Recommend"
    elif overall >= 55:
        recommendation = "Recommend with Reservations"
    else:
        recommendation = "Do Not Recommend"

    deduped_flags = list(dict.fromkeys(state.get("risk_flags", [])))

    user_msg = (
        f"CANDIDATE: {meta.get('Candidate Name', 'Unknown')} | "
        f"EXP: {meta.get('Years Experience', 'N/A')} yrs\n\n"
        f"DIMENSION SCORES:\n{json.dumps(merged, indent=2)}\n\n"
        f"FORMULA BASELINE: {formula_score} | LLM WEIGHTED: {llm_weighted}\n"
        f"BLENDED OVERALL FIT SCORE: {overall} | RECOMMENDATION: {recommendation}\n\n"
        f"INTERVIEW Q&A:\n"
        + (json.dumps(qa_pairs, ensure_ascii=False, indent=2) if qa_pairs else "CV-only — no interview conducted.")
        + f"\n\nEVIDENCE QUOTES:\n{json.dumps(state.get('evidence_quotes', {}), ensure_ascii=False, indent=2)}"
        + f"\n\nRISK FLAGS: {deduped_flags}"
    )

    narrative = cast(FinalEvaluationNarrative, _finalize_llm.invoke(
        [SystemMessage(content=_SYS_FINALIZE), HumanMessage(content=user_msg)]
    ))

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


# ── Public API ─────────────────────────────────────────────────────────────────

def evaluate_candidate(
    candidate_id: str,
    interview_mode: bool = False,
) -> dict | None:
    """
    Evaluate a single PM candidate.
    - interview_mode=False  → CV-only (fast, used for batch)
    - interview_mode=True   → live interview: 3 general (GQ-001, GQ-002, GQ-020) + 1–5 personalized
                              (count derived from risk flags + weak dimensions + formula/LLM delta)
    """
    config: dict = {"configurable": {"thread_id": candidate_id}}

    initial: InterviewState = {
        "candidate_id":        candidate_id,
        "resume_text":         "",
        "cv_metadata":         {},
        "job_description":     {},
        "question_bank":       [],
        "cv_dimension_scores": None,
        "evidence_quotes":      {},
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

    if not interview_mode:
        result = graph.invoke(initial, config)
        return result["final_evaluation"]

    # Interactive mode — loop until no more interrupts
    result = graph.invoke(initial, config)
    while True:
        paused = result.get("__interrupt__")
        if not paused:
            break
        # Interrupt objects expose `.value` (LangGraph ≥0.2); fall back to dict access
        first   = paused[0]
        payload = first.value if hasattr(first, "value") else first["value"]
        question_text = payload["question"] if isinstance(payload, dict) else str(payload)
        print(f"\nInterviewer: {question_text}")
        answer = input("Candidate: ").strip()
        result = graph.invoke(Command(resume=answer), config)

    return graph.get_state(config).values.get("final_evaluation")


def run_batch(output_file: str = "results.json", limit: int | None = None) -> list[dict]:
    """Evaluate all 135 PM candidates (CV-only). Saves JSON to output_file."""
    ids = _pm135["Candidate ID"].tolist()
    if limit:
        ids = ids[:limit]

    results: list[dict] = []
    for i, cid in enumerate(ids, 1):
        print(f"[{i:3}/{len(ids)}] {cid} ...", end=" ", flush=True)
        try:
            ev = evaluate_candidate(cid, interview_mode=False)
            if ev is None:
                raise ValueError("evaluate_candidate returned None")
            results.append(ev)
            score = ev["overall_fit_score"]
            rec   = ev["recommendation"]
            flags = ev.get("risk_flags", [])
            print(f"{score:5.1f} | {rec}" + (f" | flags: {flags}" if flags else ""))
        except Exception as exc:
            print(f"ERROR: {exc}")
            results.append({"candidate_id": cid, "error": str(exc)})

    with open(output_file, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)

    print(f"\nSaved {len(results)} results → {output_file}")
    return results


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
        "evidence_quotes":      {},
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


def start_interview_from_cv_id(
    interview_id: str,
    cv_id: str,
    interview_mode: bool = True,
) -> dict:
    """Start an interview using an existing CV-XXX from the dataset (demo path)."""
    config  = {"configurable": {"thread_id": interview_id}}
    initial = _initial_state(cv_id, interview_mode=interview_mode)
    # candidate_id drives the CSV lookup in load_data_node
    initial["candidate_id"] = cv_id
    graph.invoke(initial, config)
    return _snapshot_response(interview_id)


def submit_answer(
    interview_id: str,
    answer_text: str,
    audio_b64: Optional[str] = None,
    audio_mime: str = "audio/webm",
) -> dict:
    """
    Resume an interrupted interview with the candidate's answer.
    Returns snapshot response — either next question or final evaluation.
    """
    config  = {"configurable": {"thread_id": interview_id}}
    payload: Any = {"text": answer_text}
    if audio_b64:
        payload["audio_b64"]  = audio_b64
        payload["audio_mime"] = audio_mime
    graph.invoke(Command(resume=payload), config)
    return _snapshot_response(interview_id)


def get_interview_snapshot(interview_id: str) -> dict:
    """Fetch current interview state without progressing it."""
    return _snapshot_response(interview_id)


def list_candidates(role: Optional[str] = None) -> list[dict]:
    """List candidate IDs from the dataset (for the demo dropdown)."""
    df = _cv_db
    if role:
        df = df[df["Role"] == role]
    cols = ["Candidate ID", "Candidate Name", "Role", "Candidate Level", "Years Experience"]
    return cast(Any, df[cols]).to_dict(orient="records")


# ── CLI ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "batch":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
        run_batch(limit=limit)

    elif len(sys.argv) > 1:
        cid  = sys.argv[1]
        mode = "--interview" in sys.argv
        out  = evaluate_candidate(cid, interview_mode=mode)
        if out is not None:
            print(json.dumps(out, ensure_ascii=False, indent=2))

    else:
        out = evaluate_candidate("CV-001")
        if out is not None:
            print(json.dumps(out, ensure_ascii=False, indent=2))
