import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, Languages, CheckCircle2, Loader2 } from 'lucide-react'
import ResumeUpload from './ResumeUpload'
import VideoRecord from './VideoRecord'
import Threads from '../../components/Threads'

const STEPS = ['upload', 'record', 'results']
const STEP_KEYS = ['upload', 'record', 'results']

// ── API config ────────────────────────────────────────────────────────────────
// Change this to your backend base URL e.g. 'http://localhost:8000'
const API_BASE = ''

/**
 * POST /api/cv
 * Body: FormData { cv: File }
 * Returns: { session_id: string, questions: string[] }
 */
async function uploadCV(file) {
  const form = new FormData()
  form.append('cv', file, file.name)
  const res = await fetch(`${API_BASE}/api/cv`, { method: 'POST', body: form })
  if (!res.ok) throw new Error(`CV upload failed: ${res.status}`)
  return res.json() // { session_id, questions }
}

/**
 * POST /api/submit
 * Body: FormData { session_id, video_0, video_1, ..., questions }
 * Returns: { ok: true }
 */
async function submitAnswers(sessionId, { blobs, questions }) {
  const form = new FormData()
  form.append('session_id', sessionId)
  blobs.forEach((blob, i) => {
    const ext = blob.type.includes('mp4') ? 'mp4' : 'webm'
    form.append(`video_${i}`, blob, `answer_${i + 1}.${ext}`)
  })
  form.append('questions', JSON.stringify(questions))
  const res = await fetch(`${API_BASE}/api/submit`, { method: 'POST', body: form })
  if (!res.ok) throw new Error(`Submit failed: ${res.status}`)
  return res.json()
}

// ── UI components ─────────────────────────────────────────────────────────────
function StepBar({ current }) {
  const { t } = useTranslation()
  return (
    <nav aria-label="Progress" className="w-full">
      <ol role="list" className="flex items-start justify-center gap-0">
        {STEPS.map((step, idx) => {
          const done   = idx < current
          const active = idx === current
          const last   = idx === STEPS.length - 1
          return (
            <li key={step} className="flex items-center">
              <div className="flex flex-col items-center gap-2">
                <div
                  aria-current={active ? 'step' : undefined}
                  className={[
                    'flex items-center justify-center w-8 h-8 rounded-full border text-xs font-semibold transition-all duration-200',
                    done   ? 'border-white bg-white text-black'
                    : active ? 'border-white/60 bg-white/5 text-white'
                    :          'border-white/10 bg-transparent text-white/30',
                  ].join(' ')}
                >
                  {done ? <Check size={14} aria-hidden="true" /> : <span aria-hidden="true">{idx + 1}</span>}
                </div>
                <span className={[
                  'text-[10px] font-medium tracking-widest uppercase whitespace-nowrap',
                  active ? 'text-white' : done ? 'text-white/50' : 'text-white/20',
                ].join(' ')}>
                  {t(`user.steps.${step}`)}
                </span>
              </div>
              {!last && (
                <div
                  aria-hidden="true"
                  className={[
                    'w-16 sm:w-24 h-px mx-3 mb-5 transition-colors duration-300',
                    done ? 'bg-white/60' : 'bg-white/10',
                  ].join(' ')}
                />
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}

function LangToggle() {
  const { i18n, t } = useTranslation()
  function toggle() {
    const next = i18n.language === 'ar' ? 'en' : 'ar'
    i18n.changeLanguage(next)
    document.documentElement.dir  = next === 'ar' ? 'rtl' : 'ltr'
    document.documentElement.lang = next
  }
  return (
    <button
      onClick={toggle}
      aria-label={`Switch to ${t('nav.switchTo')}`}
      className="flex items-center justify-center w-9 h-9 rounded-full border border-white/10 bg-white/5 hover:bg-white/10 hover:border-white/20 text-zinc-300 hover:text-white transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40 cursor-pointer"
    >
      <Languages size={16} aria-hidden="true" />
    </button>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function UserPage() {
  const { t } = useTranslation()

  const [step,        setStep]        = useState(0)
  const [sessionId,   setSessionId]   = useState(null)
  const [questions,   setQuestions]   = useState([])
  const [cvLoading,   setCvLoading]   = useState(false)   // uploading CV + fetching questions
  const [cvError,     setCvError]     = useState('')
  const [submitting,  setSubmitting]  = useState(false)
  const [submitError, setSubmitError] = useState('')

  const stepKey = STEP_KEYS[step]

  // Step 0 → 1: upload CV, receive questions from backend
  async function handleCVUploaded(file) {
    setCvLoading(true)
    setCvError('')
    try {
      const { session_id, questions: qs } = await uploadCV(file)
      setSessionId(session_id)
      setQuestions(qs)
      setStep(1)
    } catch (err) {
      setCvError(err.message)
    } finally {
      setCvLoading(false)
    }
  }

  // Step 1 → 2: submit all video answers
  async function handleVideosDone(data) {
    setSubmitting(true)
    setSubmitError('')
    try {
      await submitAnswers(sessionId, data)
      setStep(2)
    } catch (err) {
      setSubmitError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-dvh bg-black text-white flex flex-col overflow-x-hidden">
      {/* Threads — angled ambiance */}
      <div
        className="fixed z-0 pointer-events-none opacity-30"
        style={{ inset: '-20%', transform: 'rotate(-18deg) scaleX(1.4)', transformOrigin: 'center center' }}
      >
        <Threads amplitude={1.4} distance={0.5} enableMouseInteraction={false} color={[1, 1, 1]} />
      </div>

      <header className="fixed top-0 inset-x-0 z-50 border-b border-white/[0.06] bg-black/80 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <span className="font-semibold text-white text-base tracking-tight">mir9ad</span>
          <LangToggle />
        </div>
      </header>

      <main className="flex-1 flex flex-col items-center px-4 pt-32 pb-16 gap-12 relative z-10">
        <div className="flex justify-center w-full">
          <StepBar current={step} />
        </div>

        {/* Heading */}
        <div className="text-center max-w-md animate-fade-in-up">
          <h1 className="text-4xl sm:text-5xl font-bold tracking-tighter mb-4">
            <span className="shiny-text">{t(`user.${stepKey}.heading`)}</span>
          </h1>
          <p className="text-base text-zinc-400 leading-relaxed">
            {t(`user.${stepKey}.subheading`)}
          </p>
        </div>

        {/* Step 0 — resume upload */}
        {step === 0 && (
          <>
            <ResumeUpload onNext={handleCVUploaded} disabled={cvLoading} />
            {/* Loading overlay while fetching questions */}
            {cvLoading && (
              <div className="flex items-center gap-3 text-sm text-zinc-400 animate-fade-in-up">
                <Loader2 size={16} className="animate-spin text-zinc-500" aria-hidden="true" />
                {t('user.upload.fetchingQuestions')}
              </div>
            )}
            {cvError && (
              <div role="alert" aria-live="polite" className="w-full max-w-lg flex items-start gap-3 px-4 py-3 rounded-xl border border-white/10 bg-zinc-900/90 text-sm text-zinc-400">
                <span className="shrink-0 mt-0.5 text-zinc-500">⚠</span>
                {cvError}
              </div>
            )}
          </>
        )}

        {/* Step 1 — record answers */}
        {step === 1 && (
          <>
            <VideoRecord questions={questions} disabled={submitting} onNext={handleVideosDone} />
            {submitError && (
              <div role="alert" aria-live="polite" className="w-full max-w-xl flex items-start gap-3 px-4 py-3 rounded-xl border border-white/10 bg-zinc-900/90 text-sm text-zinc-400">
                <span className="shrink-0 mt-0.5 text-zinc-500">⚠</span>
                {submitError}
              </div>
            )}
          </>
        )}

        {/* Step 2 — success */}
        {step === 2 && (
          <div className="flex flex-col items-center gap-6 max-w-md text-center animate-fade-in-up">
            <div className="flex items-center justify-center w-20 h-20 rounded-full border border-white/10 bg-zinc-900/90">
              <CheckCircle2 size={36} className="text-white" aria-hidden="true" />
            </div>
            <div>
              <p className="text-[10px] font-semibold tracking-widest uppercase text-zinc-500 mb-4">
                {t('user.results.tag')}
              </p>
              <p className="text-zinc-400 text-base leading-relaxed">
                {t('user.results.body')}
              </p>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
