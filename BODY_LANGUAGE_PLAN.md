# Body Language Scoring — Implementation Plan

Video is already recorded in `VideoRecord.jsx` but only used for local preview.
This plan wires the video blob through to Gemini for body language analysis alongside the existing audio delivery scoring.

---

## Blending Logic (final answer score)

| Signals available | Formula |
|---|---|
| content + audio + video | `0.60 × content + 0.25 × audio + 0.15 × video` |
| content + audio only | `0.70 × content + 0.30 × audio` ← existing, unchanged |
| content + video only | `0.75 × content + 0.25 × video` |
| content only | `content` ← existing, unchanged |

---

## 1 — `api/schemas.py`

Add two optional fields to `AnswerRequest`:

```python
video_b64:  Optional[str] = Field(None, description="Base64-encoded 30s video blob for body language scoring")
video_mime: str           = Field("video/webm", description="MIME type of video_b64")
```

---

## 2 — `api/main.py`

In the `POST /interviews/{interview_id}/answer` route, forward the new fields to `submit_answer()`:

```python
answer_agent.submit_answer(
    interview_id,
    body.answer,
    audio_b64=body.audio_b64,
    audio_mime=body.audio_mime,
    video_b64=body.video_b64,       # new
    video_mime=body.video_mime,     # new
)
```

---

## 3 — `agent.py`

### 3a — `BodyLanguageScore` schema (new Pydantic model)

```python
class BodyLanguageScore(BaseModel):
    score:              float      = Field(..., ge=0, le=10, description="Holistic 0-10 body language quality")
    eye_contact:        float      = Field(..., ge=0, le=10, description="Camera gaze vs. looking away / reading notes")
    posture:            float      = Field(..., ge=0, le=10, description="Upright/engaged vs. slouched/closed")
    gesture_fluency:    float      = Field(..., ge=0, le=10, description="Natural supporting gestures vs. fidgeting or rigid stillness")
    facial_engagement:  float      = Field(..., ge=0, le=10, description="Expressiveness vs. flat/blank affect")
    composure:          float      = Field(..., ge=0, le=10, description="Physical calm vs. nervous tells (face-touching, shifting)")
    flags:              list[str]  = Field(default_factory=list, description="reading_from_notes | poor_eye_contact | fidgeting | rigid | engaged | composed | nervous | expressive")
    notes:              str        = Field(default="", description="One-sentence observation about body language")
```

### 3b — `_BODY_LANGUAGE_PROMPT` (new constant)

```python
_BODY_LANGUAGE_PROMPT = """
You are scoring the BODY LANGUAGE of a Project Manager interview answer from a video.
Score only what you observe visually — ignore audio content entirely.

Dimensions (0-10):
- eye_contact:       Is the candidate looking at the camera? Penalize frequent look-aways or visible note-reading.
- posture:           Upright and open = 10. Slouched, turned away, or visibly closed-off = low.
- gesture_fluency:   Natural hand gestures that support speech = high. Fidgeting, tapping, rigid stillness = low.
- facial_engagement: Appropriate expressiveness and affect. Blank or flat face = low. Engaged and natural = high.
- composure:         Physical calm under pressure. Nervous tells (touching face, shifting seat, hair adjusting) = low.

Overall `score` = holistic 0-10 read of body language quality.

Flags (snake_case, only include what you actually observe):
reading_from_notes | poor_eye_contact | fidgeting | rigid | engaged | composed | nervous | expressive

`notes`: one sentence. Describe only visible behavior, not content judgment.
""".strip()
```

### 3c — `score_body_language_from_video()` (new function, mirrors `score_delivery_from_audio`)

```python
def score_body_language_from_video(video_bytes: bytes, mime_type: str = "video/webm") -> Optional[dict]:
    client = _get_gemini()
    if client is None:
        return None
    from google.genai import types as gtypes
    try:
        response = client.models.generate_content(
            model=_GEMINI_FLASH,
            contents=[
                gtypes.Part.from_bytes(data=video_bytes, mime_type=mime_type),
                _BODY_LANGUAGE_PROMPT,
            ],
            config=gtypes.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=BodyLanguageScore,
                temperature=0.0,
            ),
        )
        raw = response.text or "{}"
        return BodyLanguageScore(**json.loads(raw)).model_dump()
    except Exception as exc:
        print(f"[body language scoring failed: {exc}]", file=sys.stderr)
        return None
```

### 3d — `InterviewState` (update)

Add one transient field alongside the existing `current_answer_audio`:

```python
current_answer_video: Optional[dict]   # transient: {'b64': str, 'mime': str}
```

Also add it to `_initial_state()`:

```python
"current_answer_video": None,
```

### 3e — `ask_question_node` (update)

Extract `video_b64` from the payload dict (same pattern as audio):

```python
video_b64  = payload.get("video_b64")
video_mime = payload.get("video_mime", "video/webm")
video_state = {"b64": video_b64, "mime": video_mime} if video_b64 else None

return {
    ...
    "current_answer_audio": audio_state,
    "current_answer_video": video_state,   # new
    ...
}
```

### 3f — `score_answer_node` (update)

Call video scorer, then blend with three-way logic:

```python
# ── Body language score (video-based, optional) ───────────────────────────
body_language: Optional[dict] = None
video_state = state.get("current_answer_video")
if video_state and video_state.get("b64"):
    import base64
    try:
        video_bytes   = base64.b64decode(video_state["b64"])
        body_language = score_body_language_from_video(video_bytes, video_state.get("mime", "video/webm"))
    except Exception as exc:
        print(f"[video decode failed: {exc}]", file=sys.stderr)

# ── Three-way blend ───────────────────────────────────────────────────────
if delivery is not None and body_language is not None:
    final_score = round(0.60 * content_score + 0.25 * float(delivery["score"]) + 0.15 * float(body_language["score"]), 2)
elif delivery is not None:
    final_score = round(0.70 * content_score + 0.30 * float(delivery["score"]), 2)
elif body_language is not None:
    final_score = round(0.75 * content_score + 0.25 * float(body_language["score"]), 2)
else:
    final_score = round(content_score, 2)
```

Add to `qa_pair` dict:

```python
"body_language_score":  body_language["score"] if body_language else None,
"body_language_detail": body_language,
```

Reset video state alongside audio in the return dict:

```python
"current_answer_video": None,
```

### 3g — `submit_answer()` helper (update signature + payload)

```python
def submit_answer(
    interview_id: str,
    answer_text:  str,
    audio_b64:    Optional[str] = None,
    audio_mime:   str = "audio/webm",
    video_b64:    Optional[str] = None,   # new
    video_mime:   str = "video/webm",     # new
) -> dict:
    payload: Any = {"text": answer_text}
    if audio_b64:
        payload["audio_b64"]  = audio_b64
        payload["audio_mime"] = audio_mime
    if video_b64:
        payload["video_b64"]  = video_b64   # new
        payload["video_mime"] = video_mime  # new
    graph.invoke(Command(resume=payload), {"configurable": {"thread_id": interview_id}})
    return _snapshot_response(interview_id)
```

---

## 4 — `frontend/src/pages/user/VideoRecord.jsx`

### 4a — Store `videoBlob` in state (alongside `audioBlob`)

```js
const [videoBlob, setVideoBlob] = useState(null)
```

In `onBothDone()`:

```js
const vBlob = new Blob(videoChunksRef.current, { type: VIDEO_MIME || 'video/webm' })
setVideoBlob(vBlob)     // store for submission
setAudioBlob(aBlob)
```

Currently `vBlob` is only used for the preview URL — this persists it for submission too.

### 4b — Update `onSubmit` prop signature

Old:
```js
onSubmit(answer: string, audio_b64: string, audio_mime: string)
```

New:
```js
onSubmit(answer: string, audio_b64: string, audio_mime: string, video_b64: string, video_mime: string)
```

### 4c — Update `handleSubmit`

```js
async function handleSubmit() {
  if (!audioBlob) return
  const audio_b64 = await blobToBase64(audioBlob)
  const video_b64 = videoBlob ? await blobToBase64(videoBlob) : null
  await onSubmit?.('', audio_b64, 'audio/webm', video_b64, VIDEO_MIME || 'video/webm')
}
```

### 4d — Reset `videoBlob` on new question

In the `useEffect` that resets on `question?.question_id`:

```js
setVideoBlob(null)
```

---

## 5 — `frontend/src/pages/user/UserPage.jsx`

### 5a — Update `submitAnswer` API function

```js
async function submitAnswer(interviewId, answer, audio_b64, audio_mime, video_b64, video_mime) {
  const res = await fetch(`${API}/interviews/${interviewId}/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ answer, audio_b64, audio_mime, video_b64, video_mime }),
  })
  if (!res.ok) throw new Error(`Failed to submit answer: ${res.status}`)
  return res.json()
}
```

### 5b — Update `handleAnswer`

```js
async function handleAnswer(answer, audio_b64, audio_mime, video_b64, video_mime) {
  ...
  const snapshot = await submitAnswer(interviewId, answer, audio_b64, audio_mime, video_b64, video_mime)
  ...
}
```

Pass the new params down to `VideoRecord`:

```jsx
<VideoRecord
  question={question}
  progress={progress}
  onSubmit={handleAnswer}
  disabled={answering}
/>
```

No change to the JSX — `VideoRecord` calls `onSubmit` with all 5 args, `handleAnswer` now accepts all 5.

---

## File Change Summary

| File | Change |
|---|---|
| `api/schemas.py` | Add `video_b64`, `video_mime` to `AnswerRequest` |
| `api/main.py` | Forward `video_b64`, `video_mime` to `submit_answer()` |
| `agent.py` | Add `BodyLanguageScore`, `_BODY_LANGUAGE_PROMPT`, `score_body_language_from_video()`, update `InterviewState`, `ask_question_node`, `score_answer_node`, `submit_answer()` |
| `frontend/src/pages/user/VideoRecord.jsx` | Store `videoBlob`, encode to base64, pass to `onSubmit` |
| `frontend/src/pages/user/UserPage.jsx` | Update `submitAnswer()` and `handleAnswer()` signatures |

No new files. No schema migrations. Gracefully degrades — if `video_b64` is absent, scoring falls back to audio-only or text-only exactly as before.
