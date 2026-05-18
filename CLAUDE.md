# SBR PM Interview Agent — Frontend Integration Guide

## Running the API

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and fill env vars
cp example.env .env
# Required: GITHUB_TOKEN (or GEMINI_API_KEY if migrating to Gemini-only)
# Optional: GEMINI_API_KEY — enables audio delivery scoring

uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

Swagger UI: http://localhost:8000/docs  
OpenAPI JSON: http://localhost:8000/openapi.json

---

## Interview Session Lifecycle

Every interview is a **stateful session** keyed by `interview_id` (UUID). The backend
holds the graph state in memory (`MemorySaver`). The frontend drives it forward one
answer at a time.

```
POST /interviews              ← upload PDF → returns interview_id + first question
      │
      ▼
POST /interviews/{id}/answer  ← submit answer (repeat until status == "complete")
      │
      ▼  (when status == "complete")
GET  /interviews/{id}/result  ← full evaluation JSON
```

The total number of questions is **4–8**: 3 fixed general questions
(Introduction → Motivation → [1–5 personalized] → Final Fit) determined
after CV analysis. `progress.total_planned` tells you the count upfront.

---

## Key Endpoints

### Start interview — PDF upload

```
POST /interviews
Content-Type: multipart/form-data

resume:         <PDF file>
candidate_name: "Ibrahim Alharbi"   (optional, defaults to "Candidate")
```

**Response** (`InterviewSnapshot`):
```json
{
  "interview_id": "f47ac10b-...",
  "status": "in_progress",
  "candidate_name": "Ibrahim Alharbi",
  "current_question": {
    "question_id": "GQ-001",
    "question": "Tell me about yourself and your professional background.",
    "dimension": "communication_clarity",
    "type": "general"
  },
  "progress": { "answered": 0, "total_planned": 6 },
  "cv_preview": {
    "years_experience": 9,
    "num_skills": 8,
    "formula_score": 89.0,
    "risk_flags": [],
    "dimension_scores": { "delivery_ownership": 8.5, "..." : 0 }
  },
  "questions_asked": [],
  "evaluation": null
}
```

### Submit answer

```
POST /interviews/{interview_id}/answer
Content-Type: application/json

{
  "answer":     "I have 9 years of PM experience...",
  "audio_b64":  "<base64-encoded audio blob>",   // optional
  "audio_mime": "audio/webm"                      // optional, default audio/webm
}
```

**While in progress** — returns next question:
```json
{
  "interview_id": "...",
  "status": "in_progress",
  "current_question": { "question_id": "GQ-002", "question": "Why are you interested...", "type": "general" },
  "progress": { "answered": 1, "total_planned": 6 },
  ...
}
```

**When complete** — evaluation is populated:
```json
{
  "interview_id": "...",
  "status": "complete",
  "current_question": null,
  "evaluation": {
    "overall_fit_score": 82.5,
    "formula_score": 89.0,
    "llm_weighted_score": 76.0,
    "recommendation": "Recommend",
    "confidence_score": 0.85,
    "risk_flags": ["vague_impact"],
    "strongest_signals": ["...", "...", "..."],
    "weakest_signals": ["...", "...", "..."],
    "dimension_scores": {
      "delivery_ownership": 8.5,
      "business_impact": 7.0,
      "stakeholder_management": 8.0,
      "leadership_signals": 7.5,
      "communication_clarity": 8.0,
      "technical_fluency": 7.5,
      "evidence_credibility": 7.0,
      "strategic_thinking": 7.0,
      "pm_readiness": 8.0,
      "authenticity_confidence": 9.0
    },
    "behavioral_summary": "...",
    "trajectory_analysis": "...",
    "explanation": "...",
    "interview_qa": [
      {
        "question_id": "GQ-001",
        "dimension": "communication_clarity",
        "type": "general",
        "question": "Tell me about yourself...",
        "answer": "I have 9 years...",
        "answer_score": 7.8,
        "content_score": 7.5,
        "delivery_score": 8.5,       // null if no audio was sent
        "delivery_detail": {         // null if no audio was sent
          "score": 8.5,
          "tone": 8.0,
          "pace": 9.0,
          "confidence": 8.5,
          "hesitation": 8.5,
          "flags": ["confident", "clear"],
          "notes": "Composed delivery with natural pacing."
        },
        "follow_up": null
      }
    ],
    "resume_features": {
      "years_experience": 9,
      "num_skills": 8,
      "num_tools": 3
    }
  }
}
```

### Reconnect / polling

```
GET /interviews/{interview_id}
```
Same `InterviewSnapshot` shape. Use if the user refreshes or reconnects.

### Final result only

```
GET /interviews/{interview_id}/result
```
Returns the `evaluation` dict directly. Returns **409** if interview is not yet complete.

### Cancel

```
DELETE /interviews/{interview_id}
```

---

## Audio — How to Record and Send

The frontend records the candidate's video response. Before POSTing `/answer`:

1. Extract the audio track from the recorded `MediaRecorder` blob
2. Convert to base64
3. Include as `audio_b64` alongside the transcribed `answer` text

```js
// After MediaRecorder stops:
const audioBlob = new Blob(chunks, { type: 'audio/webm' });
const buffer    = await audioBlob.arrayBuffer();
const base64    = btoa(String.fromCharCode(...new Uint8Array(buffer)));

await fetch(`/interviews/${interviewId}/answer`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    answer:     transcript,   // from Web Speech API or Whisper
    audio_b64:  base64,
    audio_mime: 'audio/webm',
  }),
});
```

If `audio_b64` is omitted, the API falls back to text-only scoring with no error.
`delivery_score` and `delivery_detail` will be `null` in the response.

---

## Status Values

| `status`      | Meaning                                              |
|---------------|------------------------------------------------------|
| `ready`       | Interview created but first question not yet emitted |
| `in_progress` | Active — `current_question` is populated            |
| `complete`    | All questions answered — `evaluation` is populated  |
| `cancelled`   | Deleted by `DELETE /interviews/{id}`                |

---

## CORS

All origins are allowed in development (`allow_origins=["*"]`).
Tighten in `api/main.py` before deploying:

```python
allow_origins=["https://your-frontend-domain.com"]
```

---

## Architecture Overview

```
React Frontend
     │
     │  HTTP (JSON + multipart)
     ▼
FastAPI  (api/main.py)
     │
     │  calls agent helpers
     ▼
agent.py  (LangGraph StateGraph)
     ├── GPT-4o  — CV analysis, question selection, text scoring, final eval
     └── Gemini 2.0 Flash — audio delivery scoring (optional, per-answer)
```

State is held in `MemorySaver` (in-process RAM).
`interview_id` = LangGraph `thread_id`. Each `POST /answer` resumes
the graph with `Command(resume={text, audio_b64, audio_mime})`.

For production persistence (survives server restart), swap in `api/main.py`:
```python
from langgraph.checkpoint.sqlite import SqliteSaver
# pass to builder.compile(checkpointer=SqliteSaver.from_conn_string("interviews.db"))
```

---

## File Layout

```
mir9ad/
├── agent.py          — LangGraph graph + all agent logic + API helpers
├── api/
│   ├── main.py       — FastAPI app, routes, CORS
│   └── schemas.py    — Pydantic request/response models
├── DATA/             — CSV source files (loaded at startup into pandas DataFrames)
├── analysis/         — Formula derivation + EDA notebooks
├── requirements.txt
└── example.env
```
