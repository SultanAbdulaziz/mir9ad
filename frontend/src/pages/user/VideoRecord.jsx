import { useState, useRef, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Video, Square, Send, AlertCircle, Mic, Loader2 } from 'lucide-react'

const THINK_SECONDS  = 30
const RECORD_SECONDS = 60

// Video MIME for preview
const VIDEO_MIME = ['video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus', 'video/webm', 'video/mp4']
  .find(m => MediaRecorder.isTypeSupported(m)) || ''

// Audio MIME sent to backend (as per CLAUDE.md: audio/webm)
const AUDIO_MIME = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg']
  .find(m => MediaRecorder.isTypeSupported(m)) || 'audio/webm'

function fmt(s) {
  return `${String(Math.floor(s / 60)).padStart(2,'0')}:${String(s % 60).padStart(2,'0')}`
}

// Chunked base64 — safe for large audio blobs (avoids stack overflow)
async function blobToBase64(blob) {
  const buffer = await blob.arrayBuffer()
  const bytes  = new Uint8Array(buffer)
  const CHUNK  = 8192
  let binary   = ''
  for (let i = 0; i < bytes.length; i += CHUNK)
    binary += String.fromCharCode(...bytes.subarray(i, i + CHUNK))
  return btoa(binary)
}

/**
 * Props:
 *   question  — { question_id, question, dimension, type }
 *   progress  — { answered, total_planned }
 *   onSubmit  — async (answer: string, audio_b64: string, audio_mime: string) => void
 *               answer is always "" — backend transcribes from audio via Gemini
 *   disabled  — true while parent awaits backend response
 */
export default function VideoRecord({ question, progress, onSubmit, disabled = false }) {
  const { t } = useTranslation()

  const liveRef          = useRef(null)
  const previewRef       = useRef(null)
  const streamRef        = useRef(null)      // kept alive across ALL questions
  const videoRecorderRef = useRef(null)
  const audioRecorderRef = useRef(null)
  const videoChunksRef   = useRef([])
  const audioChunksRef   = useRef([])
  const thinkTimerRef    = useRef(null)
  const recordTimerRef   = useRef(null)

  // phases: idle | thinking | recording | preview
  const [phase,        setPhase]        = useState('idle')
  const [thinkElapsed, setThinkElapsed] = useState(0)
  const [recElapsed,   setRecElapsed]   = useState(0)
  const [audioBlob,    setAudioBlob]    = useState(null)
  const [error,        setError]        = useState('')

  const thinkRemaining = THINK_SECONDS  - thinkElapsed
  const recRemaining   = RECORD_SECONDS - recElapsed
  const recPct         = (recElapsed / RECORD_SECONDS) * 100
  const totalQ         = progress?.total_planned ?? '?'
  const answeredQ      = progress?.answered ?? 0

  // ── camera — asked only ONCE ─────────────────────────────────────────────
  const startCamera = useCallback(async () => {
    setError('')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true })
      streamRef.current = stream
      if (liveRef.current) { liveRef.current.srcObject = stream; liveRef.current.play() }
      setPhase('thinking')
    } catch {
      setError(t('user.record.errors.permission'))
    }
  }, [t])

  // ── think timer — auto-starts recording when it expires ──────────────────
  useEffect(() => {
    if (phase !== 'thinking') return
    if (liveRef.current && streamRef.current) {
      liveRef.current.srcObject = streamRef.current
      liveRef.current.play().catch(() => {})
    }
    thinkTimerRef.current = setInterval(() => {
      setThinkElapsed(s => {
        if (s + 1 >= THINK_SECONDS) {
          clearInterval(thinkTimerRef.current)
          startRecording()
          return THINK_SECONDS
        }
        return s + 1
      })
    }, 1000)
    return () => clearInterval(thinkTimerRef.current)
  }, [phase]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── dual recording ───────────────────────────────────────────────────────
  function startRecording() {
    clearInterval(thinkTimerRef.current)
    const stream = streamRef.current
    if (!stream) return

    videoChunksRef.current = []
    audioChunksRef.current = []

    // Video recorder — for preview only
    const videoRec = new MediaRecorder(stream, { mimeType: VIDEO_MIME })
    videoRec.ondataavailable = (e) => { if (e.data.size > 0) videoChunksRef.current.push(e.data) }

    // Audio-only recorder — sent to backend as per CLAUDE.md
    const audioStream = new MediaStream(stream.getAudioTracks())
    const audioRec    = new MediaRecorder(audioStream, { mimeType: AUDIO_MIME })
    audioRec.ondataavailable = (e) => { if (e.data.size > 0) audioChunksRef.current.push(e.data) }

    let vDone = false, aDone = false
    function onBothDone() {
      if (!vDone || !aDone) return
      const aBlob = new Blob(audioChunksRef.current, { type: AUDIO_MIME })
      const vBlob = new Blob(videoChunksRef.current, { type: VIDEO_MIME || 'video/webm' })
      setAudioBlob(aBlob)
      if (previewRef.current) {
        previewRef.current.src = URL.createObjectURL(vBlob)
        previewRef.current.load()
      }
      setPhase('preview')
    }
    videoRec.onstop = () => { vDone = true; onBothDone() }
    audioRec.onstop = () => { aDone = true; onBothDone() }

    videoRec.start(250)
    audioRec.start(250)
    videoRecorderRef.current = videoRec
    audioRecorderRef.current = audioRec

    setRecElapsed(0)
    recordTimerRef.current = setInterval(() => {
      setRecElapsed(s => {
        if (s + 1 >= RECORD_SECONDS) {
          clearInterval(recordTimerRef.current)
          videoRecorderRef.current?.stop()
          audioRecorderRef.current?.stop()
        }
        return s + 1
      })
    }, 1000)

    setPhase('recording')
  }

  function stopRecording() {
    clearInterval(recordTimerRef.current)
    videoRecorderRef.current?.stop()
    audioRecorderRef.current?.stop()
  }

  // ── submit — backend transcribes from audio_b64 via Gemini ──────────────
  async function handleSubmit() {
    if (!audioBlob) return
    const audio_b64 = await blobToBase64(audioBlob)
    await onSubmit?.(audio_b64, 'audio/webm')
  }

  // ── cleanup on unmount only ───────────────────────────────────────────────
  useEffect(() => () => {
    streamRef.current?.getTracks().forEach(tr => tr.stop())
    streamRef.current = null
    clearInterval(thinkTimerRef.current)
    clearInterval(recordTimerRef.current)
  }, [])

  // ── reset on new question — reuse stream, never ask camera again ─────────
  useEffect(() => {
    if (!question?.question_id) return
    clearInterval(thinkTimerRef.current)
    clearInterval(recordTimerRef.current)
    setThinkElapsed(0)
    setRecElapsed(0)
    setAudioBlob(null)
    setError('')
    if (previewRef.current) previewRef.current.src = ''
    setPhase(streamRef.current ? 'thinking' : 'idle')
  }, [question?.question_id])

  return (
    <div className="w-full max-w-xl flex flex-col gap-6 animate-fade-in-up">

      {/* Question card */}
      <div className="rounded-2xl border border-white/10 bg-zinc-900/90 px-6 py-5">
        <div className="flex items-center justify-between mb-3">
          <p className="text-[10px] font-semibold tracking-widest uppercase text-zinc-500">
            {t('user.record.questionLabel')}
          </p>
          <div className="flex items-center gap-3">
            {phase === 'thinking' && (
              <span className="text-[10px] font-mono text-zinc-500 tabular-nums">
                {t('user.record.thinkTime')} {fmt(thinkRemaining)}
              </span>
            )}
            <span className="text-[10px] font-mono text-zinc-600 tabular-nums">
              {answeredQ + 1} / {totalQ}
            </span>
          </div>
        </div>
        <div className="flex flex-col gap-2">
          {(question?.question ?? t('user.record.noQuestion'))
            .split(/(?<=[.?])\s+/)
            .map((sentence, i) => (
              <p key={i} className="text-sm text-zinc-200 leading-relaxed">
                {sentence}
              </p>
            ))
          }
        </div>
        {phase === 'thinking' && (
          <div className="mt-4 h-0.5 bg-white/10 rounded-full overflow-hidden">
            <div className="h-full bg-white/40 transition-all duration-1000 rounded-full"
              style={{ width: `${((THINK_SECONDS - thinkElapsed) / THINK_SECONDS) * 100}%` }} />
          </div>
        )}
      </div>

      {/* Camera / preview */}
      <div className="relative rounded-2xl border border-white/10 bg-black overflow-hidden aspect-video">

        {/* Idle — first load only */}
        {phase === 'idle' && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-4">
            <div className="flex items-center justify-center w-16 h-16 rounded-2xl border border-white/10 bg-zinc-900/90 text-zinc-500">
              <Video size={28} aria-hidden="true" />
            </div>
            <p className="text-sm text-zinc-400 px-6 text-center">{t('user.record.allow')}</p>
          </div>
        )}

        {/* Live — thinking + recording */}
        <video ref={liveRef} muted playsInline aria-label="Camera preview"
          className={['absolute inset-0 w-full h-full object-cover transition-opacity duration-300',
            phase === 'thinking' || phase === 'recording' ? 'opacity-100' : 'opacity-0 pointer-events-none'].join(' ')} />

        {/* Playback */}
        <video ref={previewRef} controls playsInline aria-label={t('user.record.preview')}
          className={['absolute inset-0 w-full h-full object-cover transition-opacity duration-300',
            phase === 'preview' ? 'opacity-100' : 'opacity-0 pointer-events-none'].join(' ')} />

        {/* Thinking overlay */}
        {phase === 'thinking' && (
          <>
            <div className="absolute top-4 left-4 flex items-center gap-2 px-3 py-1.5 rounded-full bg-black/70 backdrop-blur-sm border border-white/10">
              <span className="text-xs text-zinc-300">{t('user.record.thinkingLabel')}</span>
              <span className="text-xs font-mono text-white tabular-nums">{fmt(thinkRemaining)}</span>
            </div>
            <div className="absolute top-4 right-4 flex items-center justify-center w-8 h-8 rounded-full bg-black/60 border border-white/10 text-zinc-400">
              <Mic size={14} aria-hidden="true" />
            </div>
          </>
        )}

        {/* Recording HUD */}
        {phase === 'recording' && (
          <>
            <div className="absolute top-4 left-4 flex items-center gap-2 px-3 py-1.5 rounded-full bg-black/70 backdrop-blur-sm border border-white/10">
              <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" aria-hidden="true" />
              <span className="text-xs font-mono text-white tabular-nums">{fmt(recElapsed)}</span>
              <span className="text-xs text-zinc-400">{t('user.record.recording')}</span>
            </div>
            <div className="absolute bottom-0 inset-x-0">
              <div className={['h-1 transition-all duration-1000', recRemaining <= 5 ? 'bg-red-500' : 'bg-white/60'].join(' ')}
                style={{ width: `${recPct}%` }}
                role="progressbar" aria-valuenow={recElapsed} aria-valuemax={RECORD_SECONDS}
                aria-label={`${recRemaining}s remaining`} />
            </div>
            {recRemaining <= 5 && (
              <div className="absolute top-4 right-4 px-2 py-1 rounded-lg bg-black/70 backdrop-blur-sm">
                <span className="text-xs font-mono text-red-400 tabular-nums">:{String(recRemaining).padStart(2,'0')}</span>
              </div>
            )}
          </>
        )}
      </div>

      {/* Error */}
      {error && (
        <div role="alert" aria-live="polite" className="flex items-start gap-3 px-4 py-3 rounded-xl border border-white/10 bg-zinc-900/90 text-sm text-zinc-400">
          <AlertCircle size={16} className="shrink-0 mt-0.5 text-zinc-500" aria-hidden="true" />
          {error}
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-3">

        {/* First load — request camera once */}
        {phase === 'idle' && (
          <button onClick={startCamera}
            className="flex-1 h-12 rounded-full bg-white text-black text-sm font-semibold tracking-tight hover:scale-[1.02] hover:shadow-[0_0_20px_rgba(255,255,255,0.2)] active:scale-[0.98] transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40 cursor-pointer flex items-center justify-center gap-2">
            <Video size={16} aria-hidden="true" />
            {t('user.record.allow')}
          </button>
        )}

        {/* Thinking — skip think time */}
        {phase === 'thinking' && (
          <button onClick={startRecording}
            className="flex-1 h-12 rounded-full border border-white/20 bg-zinc-900/90 text-white text-sm font-semibold tracking-tight hover:bg-white/10 active:scale-[0.98] transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40 cursor-pointer flex items-center justify-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500" aria-hidden="true" />
            {t('user.record.startNow')}
          </button>
        )}

        {/* Recording — stop early */}
        {phase === 'recording' && (
          <button onClick={stopRecording}
            className="flex-1 h-12 rounded-full border border-white/20 bg-zinc-800/90 text-white text-sm font-semibold tracking-tight hover:bg-white/10 active:scale-[0.98] transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40 cursor-pointer flex items-center justify-center gap-2">
            <Square size={14} aria-hidden="true" />
            {t('user.record.stopRecording')}
          </button>
        )}

        {/* Preview — submit directly, no transcript needed */}
        {phase === 'preview' && (
          <button onClick={handleSubmit} disabled={disabled || !audioBlob}
            aria-disabled={disabled || !audioBlob}
            className="flex-1 h-12 rounded-full bg-white text-black text-sm font-semibold tracking-tight hover:scale-[1.02] hover:shadow-[0_0_20px_rgba(255,255,255,0.2)] active:scale-[0.98] disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:scale-100 disabled:hover:shadow-none transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40 cursor-pointer flex items-center justify-center gap-2">
            {disabled
              ? <Loader2 size={14} className="animate-spin" aria-hidden="true" />
              : <Send size={14} aria-hidden="true" />}
            {disabled ? t('user.record.submitting') : t('user.record.submit')}
          </button>
        )}
      </div>
    </div>
  )
}
