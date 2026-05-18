import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, CheckCircle2 } from 'lucide-react'
import ResumeUpload from './ResumeUpload'
import VideoRecord from './VideoRecord'
import Threads from '../../components/Threads'
import LangToggle from '../../components/LangToggle'

const STEPS = ['upload', 'record', 'results']
const STEP_KEYS = ['upload', 'record', 'results']

// ── API ───────────────────────────────────────────────────────────────────────
// Backend runs on :8000 in dev. Change to your deployed URL in production.
const API = 'http://localhost:8000'

/**
 * POST /interviews
 * Upload PDF → returns InterviewSnapshot (interview_id + first question)
 * candidate_name is optional (defaults to "Candidate" on backend)
 */
async function startInterview(file, candidateName = '') {
  const form = new FormData()
  form.append('resume', file, file.name)
  if (candidateName) form.append('candidate_name', candidateName)
  const res = await fetch(`${API}/interviews`, { method: 'POST', body: form })
  if (!res.ok) throw new Error(`Failed to start interview: ${res.status}`)
  return res.json()
}

/**
 * GET /interviews/{id}
 * Reconnect after page refresh — returns current InterviewSnapshot
 */
async function reconnect(interviewId) {
  const res = await fetch(`${API}/interviews/${interviewId}`)
  if (!res.ok) throw new Error(`Reconnect failed: ${res.status}`)
  return res.json()
}

/**
 * POST /interviews/{id}/answer
 * Submit one answer → returns next InterviewSnapshot
 * When snapshot.status === 'complete', snapshot.evaluation is populated
 */
async function submitAnswer(interviewId, audio_b64, audio_mime) {
  const res = await fetch(`${API}/interviews/${interviewId}/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ audio_b64, audio_mime }),
  })
  if (!res.ok) throw new Error(`Failed to submit answer: ${res.status}`)
  return res.json()
}

const STORAGE_KEY = 'mir9ad_interview_id'

// ── UI helpers ────────────────────────────────────────────────────────────────
function StepBar({ current }) {
  const { t } = useTranslation()
  const last = STEPS.length - 1

  return (
    <nav aria-label="Progress" className="flex flex-col items-center gap-2">
      {/* Row 1 — circles + connectors, completely isolated from labels */}
      <div className="flex items-center">
        {STEPS.map((step, idx) => {
          const done   = idx < current
          const active = idx === current
          return (
            <div key={step} className="flex items-center">
              <div
                aria-current={active ? 'step' : undefined}
                className={['flex items-center justify-center w-8 h-8 rounded-full border text-xs font-semibold transition-all duration-200',
                  done   ? 'border-white bg-white text-black'
                  : active ? 'border-white/60 bg-white/5 text-white'
                  :          'border-white/10 bg-transparent text-white/30'].join(' ')}
              >
                {done ? <Check size={14} aria-hidden="true" /> : <span aria-hidden="true">{idx + 1}</span>}
              </div>
              {idx < last && (
                <div aria-hidden="true"
                  className={['w-16 sm:w-24 h-px mx-3 transition-colors duration-300',
                    done ? 'bg-white/60' : 'bg-white/10'].join(' ')} />
              )}
            </div>
          )
        })}
      </div>

      {/* Row 2 — labels centred under each circle using the same fixed widths */}
      <div className="flex items-start">
        {STEPS.map((step, idx) => {
          const done   = idx < current
          const active = idx === current
          return (
            <div key={step} className="flex items-start">
              {/* circle-width anchor so label centres under it */}
              <div className="w-8 flex justify-center">
                <span className={['text-[10px] font-medium tracking-widest uppercase text-center',
                  active ? 'text-white' : done ? 'text-white/50' : 'text-white/20'].join(' ')}>
                  {t(`user.steps.${step}`)}
                </span>
              </div>
              {/* spacer matching connector width */}
              {idx < last && <div className="w-[88px] sm:w-[120px]" aria-hidden="true" />}
            </div>
          )
        })}
      </div>
    </nav>
  )
}


// ── Page ──────────────────────────────────────────────────────────────────────
export default function UserPage() {
  const { t } = useTranslation()

  const [step,        setStep]        = useState(0)
  const [interviewId, setInterviewId] = useState(null)
  const [question,    setQuestion]    = useState(null)   // current_question from backend
  const [progress,    setProgress]    = useState(null)   // { answered, total_planned }
  const [evaluation,  setEvaluation]  = useState(null)   // final evaluation object
  const [cvLoading,   setCvLoading]   = useState(false)
  const [cvError,     setCvError]     = useState('')
  const [answering,   setAnswering]   = useState(false)
  const [answerError, setAnswerError] = useState('')
  const [barVisible, setBarVisible] = useState(false)
  const barFillRef  = useRef(null)   // direct DOM ref — no React state for width
  const barPctRef   = useRef(0)
  const barTimer    = useRef(null)

  function setBarWidth(pct) {
    barPctRef.current = pct
    if (barFillRef.current)
      barFillRef.current.style.width = `${pct}%`
  }

  // Fake progress bar — imperative DOM updates to avoid re-render flicker
  useEffect(() => {
    if (cvLoading) {
      setBarWidth(0)
      setBarVisible(true)
      barTimer.current = setInterval(() => {
        const p = barPctRef.current
        const next = p < 70 ? p + 4 : p < 88 ? p + 1.2 : p < 94 ? p + 0.25 : p
        setBarWidth(next)
      }, 200)
    } else {
      clearInterval(barTimer.current)
      if (barFillRef.current) {
        barFillRef.current.style.transition = 'width 400ms ease-out'
        setBarWidth(100)
      }
      setTimeout(() => { setBarVisible(false); setBarWidth(0) }, 600)
    }
    return () => clearInterval(barTimer.current)
  }, [cvLoading])

  const stepKey = STEP_KEYS[step]

  // Reconnect on page refresh if a session was in progress
  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (!saved) return
    reconnect(saved)
      .then(snapshot => {
        if (snapshot.status === 'complete') {
          setEvaluation(snapshot.evaluation)
          setStep(2)
        } else if (snapshot.status === 'in_progress') {
          setInterviewId(snapshot.interview_id)
          setQuestion(snapshot.current_question)
          setProgress(snapshot.progress)
          setStep(1)
        }
      })
      .catch(() => localStorage.removeItem(STORAGE_KEY))
  }, [])

  // Step 0 → 1: upload PDF, get interview_id + first question
  async function handleCVUploaded(file) {
    setCvLoading(true)
    setCvError('')
    try {
      const snapshot = await startInterview(file)
      localStorage.setItem(STORAGE_KEY, snapshot.interview_id)
      setInterviewId(snapshot.interview_id)
      setQuestion(snapshot.current_question)
      setProgress(snapshot.progress)
      setStep(1)
    } catch (err) {
      setCvError(err.message)
    } finally {
      setCvLoading(false)
    }
  }

  // Step 1: submit one answer, get next question or evaluation
  async function handleAnswer(audio_b64, audio_mime) {
    setAnswering(true)
    setAnswerError('')
    try {
      const snapshot = await submitAnswer(interviewId, audio_b64, audio_mime)
      setProgress(snapshot.progress)

      if (snapshot.status === 'complete') {
        setEvaluation(snapshot.evaluation)
        localStorage.removeItem(STORAGE_KEY)
        setStep(2)
      } else {
        setQuestion(snapshot.current_question)
      }
    } catch (err) {
      setAnswerError(err.message)
    } finally {
      setAnswering(false)
    }
  }

  return (
    <div className="min-h-dvh bg-black text-white flex flex-col overflow-x-hidden">
      {/* Threads background */}
      <div className="fixed z-0 pointer-events-none opacity-30"
        style={{ inset: '-20%', transform: 'rotate(-18deg) scaleX(1.4)', transformOrigin: 'center center' }}>
        <Threads amplitude={1.4} distance={0.5} enableMouseInteraction={false} color={[1, 1, 1]} />
      </div>

      <header className="fixed top-0 inset-x-0 z-50 border-b border-white/[0.06] bg-black/80 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <span className="font-semibold text-white text-base" dir="rtl">مرصاد</span>
          <LangToggle />
        </div>
      </header>


      <main className="flex-1 flex flex-col items-center px-4 pt-32 pb-16 gap-12 relative z-10">
        <StepBar current={step} />

        {/* Heading */}
        <div className="text-center max-w-md animate-fade-in-up">
          <h1 className="text-4xl sm:text-5xl font-bold tracking-tighter mb-4">
            <span className="shiny-text">{t(`user.${stepKey}.heading`)}</span>
          </h1>
          <p className="text-base text-zinc-400 leading-relaxed">
            {t(`user.${stepKey}.subheading`)}
          </p>
        </div>

        {/* Step 0 — upload CV */}
        {step === 0 && (
          <>
            <ResumeUpload onNext={handleCVUploaded} disabled={cvLoading} />
            {/* Progress bar below the uploader */}
            {barVisible && (
              <div className="w-full max-w-lg h-0.5 bg-white/10 rounded-full overflow-hidden">
                <div
                  ref={barFillRef}
                  className="h-full bg-white rounded-full"
                  style={{ width: '0%', willChange: 'width' }}
                />
              </div>
            )}
            {cvError && (
              <div role="alert" aria-live="polite" className="w-full max-w-lg flex items-start gap-3 px-4 py-3 rounded-xl border border-white/10 bg-zinc-900/90 text-sm text-zinc-400">
                <span className="shrink-0 mt-0.5 text-zinc-500">⚠</span>{cvError}
              </div>
            )}
          </>
        )}

        {/* Step 1 — one question at a time */}
        {step === 1 && (
          <>
            <VideoRecord
              question={question}
              progress={progress}
              onSubmit={handleAnswer}
              disabled={answering}
            />
            {answerError && (
              <div role="alert" aria-live="polite" className="w-full max-w-xl flex items-start gap-3 px-4 py-3 rounded-xl border border-white/10 bg-zinc-900/90 text-sm text-zinc-400">
                <span className="shrink-0 mt-0.5 text-zinc-500">⚠</span>{answerError}
              </div>
            )}
          </>
        )}

        {/* Step 2 — results */}
        {step === 2 && evaluation && (
          <div className="flex flex-col items-center gap-6 w-full max-w-xl animate-fade-in-up">
            <div className="flex items-center justify-center w-20 h-20 rounded-full border border-white/10 bg-zinc-900/90">
              <CheckCircle2 size={36} className="text-white" aria-hidden="true" />
            </div>
            <div className="text-center">
              <p className="text-[10px] font-semibold tracking-widest uppercase text-zinc-500 mb-2">
                {t('user.results.tag')}
              </p>
              <p className="text-zinc-400 text-base leading-relaxed">{t('user.results.body')}</p>
            </div>

            {/* Score summary */}
            <div className="w-full rounded-2xl border border-white/10 bg-zinc-900/90 px-6 py-5 flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-zinc-400">{t('user.results.overallScore')}</span>
                <span className="text-2xl font-bold text-white tabular-nums">
                  {evaluation.overall_fit_score?.toFixed(1)}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-zinc-400">{t('user.results.recommendation')}</span>
                <span className="text-sm font-semibold text-white">{evaluation.recommendation}</span>
              </div>
              {evaluation.strongest_signals?.length > 0 && (
                <div>
                  <p className="text-[10px] uppercase tracking-widest text-zinc-600 mb-2">{t('user.results.strengths')}</p>
                  <ul className="space-y-1">
                    {evaluation.strongest_signals.map((s, i) => (
                      <li key={i} className="text-xs text-zinc-400">· {s}</li>
                    ))}
                  </ul>
                </div>
              )}
              {evaluation.weakest_signals?.length > 0 && (
                <div>
                  <p className="text-[10px] uppercase tracking-widest text-zinc-600 mb-2">{t('user.results.weaknesses')}</p>
                  <ul className="space-y-1">
                    {evaluation.weakest_signals.map((s, i) => (
                      <li key={i} className="text-xs text-zinc-400">· {s}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
