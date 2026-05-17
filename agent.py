from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode
from langchain.tools import tool
from typing import TypedDict, Annotated, Optional
from langgraph.graph.message import add_messages

import os
load_dotenv()

llm = ChatOpenAI(model="gpt-4o",
                 api_key= os.getenv("GITHUB_TOKEN"),
                 base_url=os.getenv("GITHUB_API_URL"))


class DimensionScores(TypedDict):
    delivery_ownership:      float  # 0-10
    business_impact:         float
    stakeholder_management:  float
    leadership_signals:      float
    communication_clarity:   float
    technical_fluency:       float
    evidence_credibility:    float
    strategic_thinking:      float
    pm_readiness:            float
    authenticity_confidence: float

class QAPair(TypedDict):
    question_id:       str
    dimension:         str
    question:          str
    answer:            str
    answer_score:      float
    follow_up:         Optional[str]
    follow_up_answer:  Optional[str]

class InterviewState(TypedDict):
    # ── Inputs ──────────────────────────────────────────
    candidate_id:        str
    resume_text:         str
    cv_metadata:         dict          # row from CV Database sheet
    job_description:     dict          # PM row from Job Descriptions sheet

    # ── Interview progress ───────────────────────────────
    interview_phase:     str           # "cv_analysis" | "questioning" | "follow_up" | "scoring" | "done"
    questions_asked:     list[QAPair]
    dimensions_covered:  list[str]     # which of the 10 dimensions have been probed
    questions_remaining: int           # countdown; stop at 0

    # ── Accumulating evidence ────────────────────────────
    cv_dimension_scores:        Optional[DimensionScores]   # from resume alone
    interview_dimension_scores: Optional[DimensionScores]   # from answers alone
    evidence_quotes:     dict          # dimension -> [quote strings from resume]
    risk_flags:          list[str]

    # ── Final output ─────────────────────────────────────
    final_evaluation:    Optional[dict]  # full output JSON per spec

    # ── Conversation ─────────────────────────────────────
    messages: Annotated[list, add_messages]

# ── Data retrieval (pure Python, no LLM) ─────────────────────────────

@tool
def lookup_candidate(candidate_id: str) -> dict:
    """Fetches CV metadata + raw resume text for a candidate from the Excel sheets."""

@tool
def lookup_job_description(role: str = "Project Manager") -> dict:
    """Returns job description, required skills, tools, and evaluation focus for a role."""

@tool
def get_question_bank(category: str = None) -> list[dict]:
    """Returns interview questions from General Questionnaire, optionally filtered by category."""


# ── CV intelligence (LLM-powered) ────────────────────────────────────

@tool
def analyze_cv_dimensions(resume_text: str, cv_metadata: dict, job_description: dict) -> dict:
    """
    Scores all 10 dimensions from resume text alone.
    Returns DimensionScores + risk_flags + evidence_quotes.
    Uses: ownership verbs, quantified impact, trajectory analysis, authenticity signals.
    """

@tool
def detect_authenticity_signals(resume_text: str, cv_metadata: dict) -> list[str]:
    """
    Scans for red flags: keyword stuffing, title inflation, seniority/experience mismatch,
    unrealistic claims, tool dumping, inconsistent career progression.
    Returns list of risk flag strings.
    """


# ── Interview conduct (LLM-powered) ──────────────────────────────────

@tool
def generate_interview_question(
    cv_metadata: dict,
    dimension_to_probe: str,
    questions_already_asked: list[str],
    job_description: dict
) -> str:
    """
    Generates a CV-specific, role-relevant question targeting a particular dimension.
    Avoids repeating covered ground. Anchors to specific resume claims.
    """

@tool
def generate_followup_question(
    original_question: str,
    candidate_answer: str,
    dimension: str,
    cv_context: dict
) -> str:
    """
    Generates a probing follow-up when an answer is vague, generic, or shallow.
    Pushes for specifics: metrics, decisions, outcomes, tradeoffs.
    """

@tool
def score_interview_answer(
    question: str,
    answer: str,
    dimension: str,
    cv_context: dict,
    job_description: dict
) -> dict:
    """
    Returns: { score: float(0-10), rationale: str, flags: list[str] }
    Penalizes: buzzword answers, vagueness, inconsistency with resume claims.
    Rewards: specificity, ownership language, measurable outcomes, honest tradeoffs.
    """


# ── Final evaluation (LLM-powered) ───────────────────────────────────

@tool
def compute_final_evaluation(
    candidate_id: str,
    candidate_name: str,
    cv_dimension_scores: dict,
    interview_dimension_scores: dict,
    qa_pairs: list[dict],
    evidence_quotes: dict,
    risk_flags: list[str]
) -> dict:
    """
    Merges CV + interview scores with weights (CV 40%, Interview 60%).
    Returns the complete output JSON per spec:
    overall_fit_score, confidence_score, recommendation, risk_flags,
    strongest/weakest signals, all dimension scores, behavioral_summary,
    trajectory_analysis, explanation.
    """
