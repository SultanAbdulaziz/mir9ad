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

load_dotenv()

# ── Model ──────────────────────────────────────────────────────────────────────
llm = ChatOpenAI(
    model="gpt-4o",
    api_key=SecretStr(os.getenv("GITHUB_TOKEN") or ""),
    base_url=os.getenv("GITHUB_API_URL"),
    temperature=0,
)

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

    interview_mode:      bool
    interview_phase:     str
    current_question:    Optional[dict]
    questions_asked:     list
    dimensions_covered:  list
    questions_remaining: int

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


class CVAnalysisOutput(BaseModel):
    dimension_scores:    DimensionScoresSchema
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

    resume_row = _pm135[_pm135["Candidate ID"] == cid]
    if resume_row.empty:
        resume_row = _resume_db[_resume_db["Candidate ID"] == cid]
    resume_text = str(cast(Any, resume_row["Resume Text"]).iloc[0]) if not resume_row.empty else ""

    meta_row = _cv_db[_cv_db["Candidate ID"] == cid]
    cv_metadata = (
        meta_row.iloc[0].to_dict() if not meta_row.empty
        else {"Candidate ID": cid, "Role": "Project Manager"}
    )

    jd        = _jd_db[_jd_db["Role"] == "Project Manager"].iloc[0].to_dict()
    questions = _q_db.to_dict(orient="records")

    return {
        "resume_text":        resume_text,
        "cv_metadata":        cv_metadata,
        "job_description":    jd,
        "question_bank":      questions,
        "evidence_quotes":    {},
        "risk_flags":         [],
        "questions_asked":    [],
        "dimensions_covered": [],
        "current_question":   None,
        "interview_phase":    "cv_analysis",
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

    return {
        "cv_dimension_scores": result.dimension_scores.model_dump(),
        "evidence_quotes":     result.evidence_quotes,
        "risk_flags":          result.risk_flags,
        "interview_phase":     "questioning" if state.get("interview_mode") else "done",
        "messages": [AIMessage(content=f"[CV analysis complete — {state['candidate_id']}]")],
    }


def select_question_node(state: InterviewState) -> dict:
    scores  = state.get("cv_dimension_scores") or {}
    covered = set(state.get("dimensions_covered", []))
    asked   = {q["question_id"] for q in state.get("questions_asked", [])}

    uncovered = sorted(
        [(d, s) for d, s in scores.items() if d not in covered],
        key=lambda x: x[1]
    )
    weakest   = [d for d, _ in uncovered[:4]]
    available = [q for q in state["question_bank"] if q["Question ID"] not in asked]

    user_msg = (
        f"CV DIMENSION SCORES:\n{json.dumps(scores, indent=2)}\n\n"
        f"DIMENSIONS ALREADY COVERED: {list(covered)}\n"
        f"WEAKEST UNCOVERED DIMENSIONS: {weakest}\n"
        f"RISK FLAGS: {state.get('risk_flags', [])}\n\n"
        f"RESUME EXCERPT (first 700 chars):\n{state['resume_text'][:700]}\n\n"
        f"AVAILABLE QUESTIONS:seniority_inconsistency\n{json.dumps(available, ensure_ascii=False, indent=2)}"
    )

    result = cast(QuestionSelection, _question_llm.invoke(
        [SystemMessage(content=_SYS_SELECT_QUESTION), HumanMessage(content=user_msg)]
    ))

    return {"current_question": result.model_dump()}


def ask_question_node(state: InterviewState) -> dict:
    q      = state["current_question"] or {}
    answer = interrupt({"question": q["question"]})

    return {
        "interview_phase": "scoring",
        "messages": [
            AIMessage(content=f"Interviewer: {q['question']}"),
            HumanMessage(content=str(answer)),
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

    result = cast(AnswerScore, _score_llm.invoke(
        [SystemMessage(content=_SYS_SCORE_ANSWER), HumanMessage(content=user_msg)]
    ))

    qa_pair = {
        "question_id":      q.get("question_id", ""),
        "dimension":        q.get("dimension", ""),
        "question":         q.get("question", ""),
        "answer":           answer,
        "answer_score":     result.score,
        "follow_up":        result.follow_up_question if result.follow_up_needed else None,  # noqa: E501
        "follow_up_answer": None,
    }

    new_remaining = state.get("questions_remaining", 0) - 1

    return {
        "questions_asked":     state.get("questions_asked", []) + [qa_pair],
        "dimensions_covered":  state.get("dimensions_covered", []) + [q.get("dimension", "")],
        "questions_remaining": new_remaining,
        "risk_flags":          state.get("risk_flags", []) + result.flags,
        "current_question":    None,
        "interview_phase":     "questioning" if new_remaining > 0 else "done",
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

    overall = _weighted_score(merged)

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
        f"OVERALL FIT SCORE: {overall} | RECOMMENDATION: {recommendation}\n\n"
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
        "overall_fit_score": overall,
        "confidence_score":  narrative.confidence_score,
        "recommendation":    recommendation,
        "risk_flags":        deduped_flags,
        "strongest_signals": narrative.strongest_signals,
        "weakest_signals":   narrative.weakest_signals,
        "dimension_scores":  merged,
        "behavioral_summary":  narrative.behavioral_summary,
        "trajectory_analysis": narrative.trajectory_analysis,
        "explanation":         narrative.explanation,
    }

    return {
        "final_evaluation": evaluation,
        "interview_phase":  "done",
        "messages": [AIMessage(content=json.dumps(evaluation, ensure_ascii=False, indent=2))],
    }


# ── Routing ────────────────────────────────────────────────────────────────────
def _route_after_cv(state: InterviewState) -> str:
    if state.get("interview_mode") and state.get("questions_remaining", 0) > 0:
        return "select_question"
    return "finalize"


def _route_after_score(state: InterviewState) -> str:
    return "select_question" if state.get("questions_remaining", 0) > 0 else "finalize"


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
    num_questions: int = 4,
) -> dict | None:
    """
    Evaluate a single PM candidate.
    - interview_mode=False  → CV-only (fast, used for batch)
    - interview_mode=True   → live interview via stdin
    """
    config: dict = {"configurable": {"thread_id": candidate_id}}

    initial: InterviewState = {
        "candidate_id":        candidate_id,
        "resume_text":         "",
        "cv_metadata":         {},
        "job_description":     {},
        "question_bank":       [],
        "cv_dimension_scores": None,
        "evidence_quotes":     {},
        "risk_flags":          [],
        "interview_mode":      interview_mode,
        "interview_phase":     "cv_analysis",
        "current_question":    None,
        "questions_asked":     [],
        "dimensions_covered":  [],
        "questions_remaining": num_questions if interview_mode else 0,
        "final_evaluation":    None,
        "messages":            [],
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
        question_text = paused[0]["value"]["question"]
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
