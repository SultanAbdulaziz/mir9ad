"""
FastAPI app exposing the PM interview agent to the React frontend.

Endpoints:
  POST   /interviews              upload PDF resume -> start interview, return first question
  GET    /interviews/{id}         current snapshot (for reconnect / polling)
  POST   /interviews/{id}/answer  submit answer (text + optional audio), return next question or final eval
  GET    /interviews/{id}/result  final evaluation (409 if not complete)
  DELETE /interviews/{id}         cancel + cleanup

  GET    /healthz                 liveness probe
"""
from __future__ import annotations

import csv
import io
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

import agent
from api import schemas


# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="SBR PM Interview Agent",
    description="Multimodal AI agent for Project Manager candidate evaluation.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten to your Railway domain before going public
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ─────────────────────────────────────────────────────────────────────
@app.get("/healthz", response_model=schemas.HealthResponse, tags=["meta"])
def healthz() -> schemas.HealthResponse:
    return schemas.HealthResponse(
        status="ok",
        llm_ready=agent._get_gemini() is not None,
    )


_CSV_REQUIRED_COLS = {"Candidate ID", "Role", "Resume Text"}

# ── Interview lifecycle ────────────────────────────────────────────────────────
@app.post("/interviews", response_model=schemas.InterviewSnapshot, tags=["interviews"])
async def start_interview_from_pdf(
    resume:         UploadFile = File(..., description="Candidate resume — PDF or CSV"),
    candidate_name: str        = Form("Candidate"),
) -> dict:
    """Start a new interview from an uploaded PDF or CSV resume file."""
    filename = (resume.filename or "").lower()
    content  = await resume.read()

    # ── CSV path ──────────────────────────────────────────────────────────────
    if filename.endswith(".csv"):
        try:
            reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
            rows   = list(reader)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not parse CSV file — ensure it is UTF-8 encoded.",
            )

        missing = _CSV_REQUIRED_COLS - set(reader.fieldnames or [])
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"CSV is missing required columns: {', '.join(sorted(missing))}. "
                       f"Required: Candidate ID, Role, Resume Text",
            )

        if not rows:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CSV file is empty — no candidate rows found.",
            )

        row         = rows[0]   # process first candidate
        resume_text = row["Resume Text"].strip()
        cid         = row.get("Candidate ID", "").strip()
        candidate_name = cid or candidate_name

        if not resume_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Resume Text column is empty in the first row.",
            )

        interview_id = cid or str(uuid.uuid4())

    # ── PDF path ──────────────────────────────────────────────────────────────
    else:
        if (resume.content_type or "").lower() not in {"application/pdf", "application/octet-stream"}:
            if not filename.endswith(".pdf"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Only PDF or CSV files are accepted.",
                )

        resume_text = agent.parse_pdf_resume(content)
        if not resume_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not extract text from PDF — file may be image-only or corrupted.",
            )

        interview_id = str(uuid.uuid4())

    return agent.start_interview(
        interview_id=interview_id,
        resume_text=resume_text,
        candidate_name=candidate_name,
        interview_mode=True,
    )


@app.get("/interviews/{interview_id}", response_model=schemas.InterviewSnapshot, tags=["interviews"])
def get_interview(interview_id: str) -> dict:
    """Get current interview snapshot (use for polling / reconnect)."""
    snap = agent.get_interview_snapshot(interview_id)
    if not snap.get("candidate_name") and not snap.get("current_question") and not snap.get("evaluation"):
        raise HTTPException(status_code=404, detail=f"interview_id={interview_id!r} not found")
    return snap


@app.post("/interviews/{interview_id}/answer", response_model=schemas.InterviewSnapshot, tags=["interviews"])
def post_answer(interview_id: str, req: schemas.AnswerRequest) -> dict:
    """Submit the candidate's answer; returns the next question or the final evaluation."""
    try:
        return agent.submit_answer(
            interview_id=interview_id,
            audio_b64=req.audio_b64,
            audio_mime=req.audio_mime,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not submit answer: {exc}")


@app.get("/interviews/{interview_id}/result", tags=["interviews"])
def get_result(interview_id: str) -> dict[str, Any]:
    """Final evaluation. Returns 409 if interview is not yet complete."""
    snap = agent.get_interview_snapshot(interview_id)
    if snap.get("status") != "complete":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Interview {interview_id} not complete — status={snap.get('status')}",
        )
    return snap["evaluation"]


@app.delete("/interviews/{interview_id}", tags=["interviews"])
def delete_interview(interview_id: str) -> dict[str, str]:
    """Cancel and drop the interview state from the checkpointer."""
    config = {"configurable": {"thread_id": interview_id}}
    try:
        agent.graph.update_state(config, {"interview_phase": "cancelled"})
    except Exception:
        pass
    return {"interview_id": interview_id, "status": "cancelled"}


# ── Admin ──────────────────────────────────────────────────────────────────────
@app.get("/admin/candidates", tags=["admin"])
def get_admin_candidates() -> list[dict]:
    """Return all candidate records merged from both DB tables."""
    sb = agent._get_supabase()
    if sb is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not configured.",
        )

    candidates  = sb.table("candidates").select("*").execute().data or []
    cv_profiles = sb.table("cv_profiles").select("*").execute().data or []

    candidates_by_id = {c["candidate_id"]: c for c in candidates}
    profiles_by_id   = {p["candidate_id"]: p for p in cv_profiles}

    merged = []
    for cid, candidate in candidates_by_id.items():
        if cid not in profiles_by_id:
            continue
        profile = profiles_by_id[cid]
        merged.append({**profile, **candidate})

    merged.sort(key=lambda x: x.get("fit_score") or 0, reverse=True)
    return merged


@app.delete("/admin/candidates/{candidate_id}", tags=["admin"])
def delete_candidate(candidate_id: str) -> dict[str, str]:
    """Delete a candidate from both DB tables."""
    sb = agent._get_supabase()
    if sb is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not configured.",
        )
    sb.table("candidates").delete().eq("candidate_id", candidate_id).execute()
    sb.table("cv_profiles").delete().eq("candidate_id", candidate_id).execute()
    return {"candidate_id": candidate_id, "status": "deleted"}


# ── Serve built React frontend ─────────────────────────────────────────────────
# MUST be registered LAST so the catch-all doesn't intercept API routes
_STATIC = Path(__file__).parent.parent / "static"
if _STATIC.exists():
    app.mount("/assets", StaticFiles(directory=_STATIC / "assets"), name="assets")

    _API_PREFIXES = ("interviews", "admin", "healthz")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str) -> FileResponse:
        # Safety net: never serve HTML for known API paths
        if any(full_path.startswith(p) for p in _API_PREFIXES):
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(_STATIC / "index.html")
