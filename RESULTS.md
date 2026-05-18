# mir9ad — Codebase Review

## Overview

mir9ad is a multimodal AI interview agent for evaluating Project Manager candidates. A candidate uploads their PDF resume, records video answers to 4–8 tailored questions, and receives a fit score. Recruiters review all candidates through a separate admin dashboard.

---

## Data Layer (`DATA/`)

| File | Rows | Purpose |
|---|---|---|
| `Datathon Database - CV Database.csv` | 34 | Master candidate profiles with expected scores and testing metadata |
| `Datathon Database - Resume Text.csv` | ~6,097 | Full resume text per candidate (multi-line, formatted like a real CV) |
| `Datathon Database - General Questionnaire.csv` | 19 | Question bank: categories, text, suggested follow-ups, evaluation focus |
| `Datathon Database - Job Descriptions.csv` | 4 | Role definitions for PM, Financial Analyst, Digital Marketing, Data Analyst |
| `Datathon Database - Summary.csv` | 6 | Dataset composition: 10 Strong + 10 Average + 10 Weak + 5 Surprise per role |
| `generated.csv` | 175 | Synthetically generated candidates — same schema as CV Database, sparser |
| `PROJECT MANAGER 135 csv.csv` | ~4,861 | Full resume text for the expanded PM candidate pool |

**Relationships:**
- CV Database / generated.csv → candidate metadata and expected scores
- Resume Text / PROJECT MANAGER 135 csv → the actual CV content fed to the agent
- Job Descriptions → role context used during CV analysis and scoring
- General Questionnaire → question bank the agent selects from at runtime

**Note:** The CV Database is only used at startup to train the linear regression formula (`Expected Fit Score ~ years_experience + num_skills + num_tools`, R²=0.93). At runtime, candidates upload their own PDFs — the CSV data is never queried per-candidate.

---

## Backend

### `agent.py` — LangGraph State Machine (974 lines)

#### Startup (module-level)
- Loads `.env`, lazily initializes Supabase and Gemini (`gemini-2.5-pro`) clients
- Reads three CSVs into DataFrames (`_cv_db`, `_jd_db`, `_q_db`)
- Trains a `sklearn.LinearRegression` to produce `_fit_formula()` → `(intercept, w_exp, w_skills, w_tools)`

#### Scoring architecture — three independent layers

| Layer | Method | Weight |
|---|---|---|
| Formula score | Linear regression on resume features | 50% of final |
| LLM weighted score | Weighted sum of 10 dimension scores × fixed weights | 50% of final |
| Overall fit score | `0.5 × formula + 0.5 × llm_weighted`, clamped 0–100 | Final output |

#### Dimension weights (sum = 1.0)

| Dimension | Weight |
|---|---|
| `delivery_ownership` | 0.18 |
| `leadership_signals` | 0.15 |
| `business_impact` | 0.15 |
| `stakeholder_management` | 0.12 |
| `evidence_credibility` | 0.12 |
| `pm_readiness` | 0.10 |
| `strategic_thinking` | 0.08 |
| `communication_clarity` | 0.05 |
| `technical_fluency` | 0.03 |
| `authenticity_confidence` | 0.02 |

#### LangGraph nodes

```
load_data → analyze_cv → [conditional] → select_question → ask_question → score_answer → [loop or finalize]
                                 ↓
                              finalize → END
```

| Node | Description |
|---|---|
| `load_data_node` | Hydrates state with resume text, job description, question bank |
| `analyze_cv_node` | Gemini structured output → 10 dimension scores, risk flags, evidence quotes, resume features. Computes formula score. Determines interview plan length (1–5 personalized questions). Writes to Supabase `cv_profiles`. |
| `select_question_node` | Pops next slot from `interview_plan`. For `general:GQ-XXX` slots: verbatim question. For `personalized`: Gemini picks + adapts from bank, targeting weakest uncovered dimensions. |
| `ask_question_node` | LangGraph `interrupt()` — pauses graph, surfaces question to API. Accepts `{text, audio_b64, audio_mime}`. Auto-transcribes audio via Gemini when `answer` is empty. |
| `score_answer_node` | Content score (Gemini text, 0–10) + delivery score (Gemini audio, 0–10). Blends `0.7 × content + 0.3 × delivery`. Pops answered slot, appends Q&A pair. |
| `finalize_node` | Merges CV scores (40%) + interview scores (60%) per dimension → weighted sum → LLM score. Blends with formula score (50/50). Calls Gemini for narrative (strengths, weaknesses, explanation). Writes to Supabase `candidates`. |

#### Interview plan

- 2 fixed general questions (opening) + 1 fixed closing → currently both `GENERAL_OPENING_IDS = []` and `GENERAL_CLOSING_ID = None`, so the plan is **only personalized questions** until those are populated with real question IDs from the bank.
- Number of personalized questions (1–5) scales with CV uncertainty: risk flags, low dimension scores, large formula↔LLM discrepancy.

#### Recommendation thresholds

| Score | Recommendation |
|---|---|
| ≥ 75 | Recommend |
| ≥ 55 | Recommend with Reservations |
| < 55 | Do Not Recommend |

#### Persistence
- **In-process RAM** (`MemorySaver`) — state lost on server restart
- Supabase writes are fire-and-forget (failures logged to stderr, never surfaced to API)
- Production swap: `SqliteSaver` in `api/main.py` (documented in CLAUDE.md)

---

### `api/main.py` — FastAPI (158 lines)

Thin wrapper over `agent.py`. CORS currently restricted to `localhost:5173` and `127.0.0.1:5173`.

| Method | Path | Description |
|---|---|---|
| `POST` | `/interviews` | Upload PDF → extract text → start interview → return first question |
| `GET` | `/interviews/{id}` | Current snapshot (for reconnect / polling) |
| `POST` | `/interviews/{id}/answer` | Resume graph with candidate's answer → return next question or final evaluation |
| `GET` | `/interviews/{id}/result` | Final evaluation only; 409 if not complete |
| `DELETE` | `/interviews/{id}` | Mark interview as cancelled |
| `GET` | `/admin/candidates` | Merge `candidates` + `cv_profiles` from Supabase for dashboard |

---

### `api/schemas.py` — Pydantic contracts (54 lines)

- `AnswerRequest` — `{ answer, audio_b64?, audio_mime }`
- `InterviewSnapshot` — unified response for all in-progress endpoints
- `HealthResponse` — liveness + Gemini key status

---

## Frontend (`frontend/src/`)

React + Vite, Tailwind CSS, React Router v6, `react-i18next`, Lucide icons. Two routes:

| Route | Component | Audience |
|---|---|---|
| `/user` | `UserPage` | Candidate |
| `/admin` | `AdminPage` | Recruiter |

### Candidate flow — `UserPage.jsx`

Three-step linear flow (no routing between steps, just `useState`):

**Step 0 — Upload (`ResumeUpload.jsx`)**
- Drag-and-drop or file picker; PDF only, max 5 MB
- On selection: `POST /interviews` → receives `interview_id` + first question
- Saves `interview_id` to `localStorage` for reconnect

**Step 1 — Record (`VideoRecord.jsx`)**
- Four internal phases: `idle → thinking → recording → preview`
- Camera/mic requested **once** — `MediaStream` kept alive across all questions in `streamRef`
- Dual `MediaRecorder`: video for local playback preview, audio-only sent to backend
- 30-second think time + 30-second recording cap; user can skip/stop early
- Submit sends `answer=""` + `audio_b64` — backend transcribes from audio via Gemini
- Base64 encoding done in 8 KB chunks to avoid stack overflow on large blobs
- Loops until `snapshot.status === 'complete'`

**Step 2 — Results (inline in `UserPage`)**
- Shows `overall_fit_score`, `recommendation`, `strongest_signals`, `weakest_signals`
- Clears `localStorage` session key

**Reconnect:** on mount, checks `localStorage` for a saved `interview_id` and calls `GET /interviews/{id}`. Jumps to step 1 or 2 depending on status. Clears the key on 404/error.

### Admin dashboard — `AdminPage.jsx`

Split-pane layout (responsive: list hides on mobile when detail is open).

- On mount: `GET /admin/candidates` → populates left list
- Left: `CandidateRow` per candidate — name, role, years, fit score, recommendation icon
- Right: `CandidateDetail` — recommendation banner, 4-bar score breakdown, strengths/weaknesses, CV profile fields, experience summary, edge case note

### Shared components

- **`LangToggle.jsx`** — toggles `en` ↔ `ar`; sets `document.dir` and `document.lang` directly
- **`Threads.jsx`** — animated canvas background (flowing lines), decorative, `pointer-events-none`
- **`i18n/`** — `i18next` with browser language detection (localStorage → navigator), fallback `en`; translations for `en` and `ar`

---

## Issues & Gaps

### Bug — `REC_ICON` mismatch in `AdminPage.jsx`

The backend emits three recommendation strings:
- `"Recommend"`
- `"Recommend with Reservations"`
- `"Do Not Recommend"`

The `REC_ICON` map in `AdminPage.jsx` keys on:
- `"Recommend"` ✓
- `"Maybe / needs further assessment"` ✗ (never emitted)
- `"Do not recommend"` ✗ (casing mismatch — backend emits `"Do Not Recommend"`)
- `"Conditional / requires follow-up interview"` ✗ (never emitted)

Result: `"Recommend with Reservations"` and `"Do Not Recommend"` both fall through to the default `MinusCircle` icon. The map needs to be aligned with the backend's actual strings.

### `GENERAL_OPENING_IDS` and `GENERAL_CLOSING_ID` are empty

In `agent.py`:
```python
GENERAL_OPENING_IDS = []
GENERAL_CLOSING_ID  = None
```

The interview plan currently contains **only personalized questions** — no fixed opening (Introduction, Motivation) or closing (Final Fit) questions. These constants need to be populated with actual question IDs from the bank (e.g. `"GQ-001"`, `"GQ-002"`, `"GQ-020"`) for the intended structure to work.

### Silent transcription failure

In `ask_question_node`, if Gemini transcription fails, `answer_text` stays `""` and the empty string is scored. There is no error propagated to the frontend. The `score_answer_node` will score an empty answer, potentially penalizing the candidate unfairly.

### Scores visible to candidates

Step 2 shows `overall_fit_score`, `recommendation`, and signal lists to the candidate. This may be intentional for transparency, but is worth a deliberate decision — many hiring pipelines keep scores internal.

### CORS is dev-only

`api/main.py` only allows `localhost:5173` and `127.0.0.1:5173`. Must be updated before any deployment.

### State not persisted across server restarts

`MemorySaver` is in-process RAM. A server restart during an active interview loses the graph state. The `interview_id` stored in the candidate's browser will 404 on reconnect. The SqliteSaver swap is documented but not wired up.
