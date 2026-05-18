"""Request / response Pydantic schemas for the FastAPI layer."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Requests ───────────────────────────────────────────────────────────────────
class AnswerRequest(BaseModel):
    answer:     str           = Field(..., description="Transcribed text of the candidate's answer")
    audio_b64:  Optional[str] = Field(None, description="Optional base64-encoded audio of the answer for delivery scoring")
    audio_mime: str           = Field("audio/webm", description="MIME type of audio_b64 (e.g. audio/webm, audio/mp4, audio/wav)")


# ── Sub-shapes ─────────────────────────────────────────────────────────────────
class CurrentQuestion(BaseModel):
    question_id: str
    question:    str
    dimension:   str
    type:        str            = Field("personalized", description="'general' | 'personalized'")
    rationale:   Optional[str]  = None


class Progress(BaseModel):
    answered:      int
    total_planned: int


class CVPreview(BaseModel):
    years_experience: Optional[float] = None
    num_skills:       Optional[int]   = None
    num_tools:        Optional[int]   = None
    formula_score:    Optional[float] = None
    risk_flags:       list[str]       = Field(default_factory=list)
    dimension_scores: Optional[dict[str, float]] = None


# ── Responses ──────────────────────────────────────────────────────────────────
class InterviewSnapshot(BaseModel):
    """Returned by start, answer (in-progress), and get-state endpoints."""
    interview_id:     str
    status:           str                       = Field(..., description="'in_progress' | 'ready' | 'complete'")
    candidate_name:   Optional[str]             = None
    current_question: Optional[CurrentQuestion] = None
    progress:         Optional[Progress]        = None
    cv_preview:       Optional[CVPreview]       = None
    questions_asked:  list[dict[str, Any]]      = Field(default_factory=list)
    evaluation:       Optional[dict[str, Any]]  = Field(None, description="Populated when status == 'complete'")


class HealthResponse(BaseModel):
    status:      str
    llm_ready:   bool   = Field(..., description="True if Gemini API key is configured")
