import { useState, useRef, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Video, Square, RotateCcw, Send, AlertCircle, Mic, Loader2 } from 'lucide-react'

const MAX_SECONDS = 30

const MIME = ['video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus', 'video/webm', 'video/mp4']
  .find(m => MediaRecorder.isTypeSupported(m)) || ''

function fmt(s) {
  const m   = String(Math.floor(s / 60)).padStart(2, '0')
  const sec = String(s % 60).padStart(2, '0')
  return `${m}:${sec}`
}

async function blobToBase64(blob) {
  const buffer = await blob.arrayBuffer()
  const bytes  = new Uint8Array(buffer)
  let binary   = ''
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i])
  return btoa(binary)
}

/**
 * Props:
 *   question    — { question_id, question, dimension, type }
 *   progress    — { answered, total_planned }
 *   onSubmit    — async (answer: string, audio_b64: string, audio_mime: string) => void
 *   disabled    — true while parent is awaiting backend response
 */
export default function VideoRecord({ question, progress, onSubmit, disabled = false }) {
  const { t } = useTranslation()

  const liveRef     = useRef(null)
  const previewRef  = useRef(null)
  const streamRef   = useRef(null)
  const recorderRef = useRef(null)
  const chunksRef   = useRef([])
  const timerRef    = useRef(null)
  const speechRef   = useRef(null)

  const [phase,      setPhase]      = useState('idle')       // idle|live|recording|preview
  const [elapsed,    setElapsed]    = useState(0)
  const [error,      setError]      = useState('')
  const [transcript, setTranscript] = useState('')            // editable by user
  const [audioBlob,  setAudioBlob]  = useState(null)

  const remaining = MAX_SECONDS - elapsed
  const pct       = (elapsed / MAX_SECONDS) * 100

  // ── camera ──────────────────────────────────────────────────────────────────
  const startCamera = useCallback(async () => {
    setError('')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true })
      streamRef.current = stream
      if (liveRef.current) { liveRef.current.srcObject = stream; liveRef.current.play() }
      setPhase('live')
    } catch {
      setError(t('user.record.errors.permission'))
    }
  }, [t])

  function stopStream() {
    streamRef.current?.getTracks().forEach(tr => tr.stop())
    streamRef.current = null
  }

  // ── speech recognition (best-effort, Chrome/Edge) ──────────────────────────
  function startSpeechRecognition() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) return
    const sr = new SR()
    sr.continuous       = true
    sr.interimResults   = false
    sr.lang             = document.documentElement.lang === 'ar' ? 'ar-SA' : 'en-US'
    sr.onresult = (e) => {
      const text = Array.from(e.results).map(r => r[0].transcript).join(' ')
      setTranscript(text)
    }
    sr.start()
    speechRef.current = sr
  }

  function stopSpeechRecognition() {
    try { speechRef.current?.stop() } catch {}
    speechRef.current = null
  }

  // ── recording ───────────────────────────────────────────────────────────────
  function startRecording() {
    if (!streamRef.current) return
    chunksRef.current = []
    setTranscript('')
    const rec = new MediaRecorder(streamRef.current, { mimeType: MIME })
    rec.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data) }
    rec.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: MIME || 'video/webm' })
      setAudioBlob(blob)
      if (previewRef.current) {
        previewRef.current.src = URL.createObjectURL(blob)
        previewRef.current.load()
      }
      stopStream()
      stopSpeechRecognition()
      setPhase('preview')
    }
    rec.start(250)
    recorderRef.current = rec
    setElapsed(0)
    timerRef.current = setInterval(() => {
      setElapsed(s => {
        if (s + 1 >= MAX_SECONDS) {
          clearInterval(timerRef.current)
          recorderRef.current?.stop()
        }
        return s + 1
      })
    }, 1000)
    startSpeechRecognition()
    setPhase('recording')
  }

  function stopRecording() {
    clearInterval(timerRef.current)
    recorderRef.current?.stop()
  }

  async function reRecord() {
    setElapsed(0)
    setAudioBlob(null)
    setTranscript('')
    if (previewRef.current) previewRef.current.src = ''
    await startCamera()
  }

  // ── submit ───────────────────────────────────────────────────────────────────
  async function handleSubmit() {
    if (!transcript.trim()) { setError(t('user.record.errors.noTranscript')); return }
    const audio_b64  = audioBlob ? await blobToBase64(audioBlob) : ''
    const audio_mime = audioBlob?.type || 'audio/webm'
    await onSubmit?.(transcript.trim(), audio_b64, audio_mime)
  }

  useEffect(() => () => { stopStream(); stopSpeechRecognition(); clearInterval(timerRef.current) }, [])

  // Reset to idle when question changes (new question arrived)
  useEffect(() => {
    setPhase('idle')
    setElapsed(0)
    setTranscript('')
    setAudioBlob(null)
    setError('')
    if (previewRef.current) previewRef.current.src = ''
    stopStream()
  }, [question?.question_id])

  const totalQ    = progress?.total_planned ?? '?'
  const answeredQ = progress?.answered ?? 0

  return (
    <div className="w-full max-w-xl flex flex-col gap-6 animate-fade-in-up">

      {/* Question card */}
      <div className="rounded-2xl border border-white/10 bg-zinc-900/90 px-6 py-5">
        <div className="flex items-center justify-between mb-3">
          <p className="text-[10px] font-semibold tracking-widest uppercase text-zinc-500">
            {t('user.record.questionLabel')}
          </p>
          <span className="text-[10px] font-mono text-zinc-600 tabular-nums">
            {answeredQ + 1} / {totalQ}
          </span>
        </div>
        <p className="text-base font-medium text-white leading-relaxed">
          {question?.question ?? t('user.record.noQuestion')}
        </p>
      </div>

      {/* Camera / preview */}
      <div className="relative rounded-2xl border border-white/10 bg-black overflow-hidden aspect-video">

        {/* Idle */}
        {phase === 'idle' && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-4">
            <div className="flex items-center justify-center w-16 h-16 rounded-2xl border border-white/10 bg-zinc-900/90 text-zinc-500">
              <Video size={28} aria-hidden="true" />
            </div>
            <p className="text-sm text-zinc-400 px-6 text-center">{t('user.record.allow')}</p>
          </div>
        )}

        {/* Live */}
        <video ref={liveRef} muted playsInline aria-label="Camera preview"
          className={['absolute inset-0 w-full h-full object-cover transition-opacity duration-300',
            phase === 'live' || phase === 'recording' ? 'opacity-100' : 'opacity-0 pointer-events-none'].join(' ')} />

        {/* Playback */}
        <video ref={previewRef} controls playsInline aria-label={t('user.record.preview')}
          className={['absolute inset-0 w-full h-full object-cover transition-opacity duration-300',
            phase === 'preview' ? 'opacity-100' : 'opacity-0 pointer-events-none'].join(' ')} />

        {/* Recording HUD */}
        {phase === 'recording' && (
          <>
            <div className="absolute top-4 left-4 flex items-center gap-2 px-3 py-1.5 rounded-full bg-black/70 backdrop-blur-sm border border-white/10">
              <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" aria-hidden="true" />
              <span className="text-xs font-mono text-white tabular-nums">{fmt(elapsed)}</span>
              <span className="text-xs text-zinc-400">{t('user.record.recording')}</span>
            </div>
            <div className="absolute bottom-0 inset-x-0">
              <div className={['h-1 transition-all duration-1000', remaining <= 5 ? 'bg-red-500' : 'bg-white/60'].join(' ')}
                style={{ width: `${pct}%` }}
                role="progressbar" aria-valuenow={elapsed} aria-valuemax={MAX_SECONDS}
                aria-label={`${remaining}s remaining`} />
            </div>
            {remaining <= 5 && (
              <div className="absolute top-4 right-4 px-2 py-1 rounded-lg bg-black/70 backdrop-blur-sm">
                <span className="text-xs font-mono text-red-400 tabular-nums">:{String(remaining).padStart(2,'0')}</span>
              </div>
            )}
          </>
        )}

        {phase === 'live' && (
          <div className="absolute top-4 right-4 flex items-center justify-center w-8 h-8 rounded-full bg-black/60 border border-white/10 text-zinc-400">
            <Mic size={14} aria-hidden="true" />
          </div>
        )}
      </div>

      {/* Transcript — editable after recording */}
      {phase === 'preview' && (
        <div className="flex flex-col gap-2">
          <label htmlFor="transcript" className="text-[10px] font-semibold tracking-widest uppercase text-zinc-500">
            {t('user.record.transcriptLabel')}
          </label>
          <textarea
            id="transcript"
            value={transcript}
            onChange={(e) => setTranscript(e.target.value)}
            rows={4}
            placeholder={t('user.record.transcriptPlaceholder')}
            className="w-full rounded-xl border border-white/10 bg-zinc-900/90 text-sm text-white placeholder:text-zinc-600 px-4 py-3 resize-none outline-none focus:border-white/30 transition-colors duration-150 leading-relaxed"
          />
        </div>
      )}

      {/* Error */}
      {error && (
        <div role="alert" aria-live="polite" className="flex items-start gap-3 px-4 py-3 rounded-xl border border-white/10 bg-zinc-900/90 text-sm text-zinc-400">
          <AlertCircle size={16} className="shrink-0 mt-0.5 text-zinc-500" aria-hidden="true" />
          {error}
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-col sm:flex-row gap-3">
        {phase === 'idle' && (
          <button onClick={startCamera}
            className="flex-1 h-12 rounded-full bg-white text-black text-sm font-semibold tracking-tight hover:scale-[1.02] hover:shadow-[0_0_20px_rgba(255,255,255,0.2)] active:scale-[0.98] transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40 cursor-pointer flex items-center justify-center gap-2">
            <Video size={16} aria-hidden="true" />
            {t('user.record.startRecording')}
          </button>
        )}

        {phase === 'live' && (
          <button onClick={startRecording}
            className="flex-1 h-12 rounded-full bg-white text-black text-sm font-semibold tracking-tight hover:scale-[1.02] hover:shadow-[0_0_20px_rgba(255,255,255,0.2)] active:scale-[0.98] transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40 cursor-pointer flex items-center justify-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500" aria-hidden="true" />
            {t('user.record.startRecording')}
          </button>
        )}

        {phase === 'recording' && (
          <button onClick={stopRecording}
            className="flex-1 h-12 rounded-full border border-white/20 bg-zinc-800/90 text-white text-sm font-semibold tracking-tight hover:bg-white/10 active:scale-[0.98] transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40 cursor-pointer flex items-center justify-center gap-2">
            <Square size={14} aria-hidden="true" />
            {t('user.record.stopRecording')}
          </button>
        )}

        {phase === 'preview' && (
          <>
            <button onClick={reRecord}
              className="flex-1 h-12 rounded-full border border-white/10 bg-zinc-900/90 text-zinc-300 text-sm font-medium tracking-tight hover:bg-white/10 hover:text-white active:scale-[0.98] transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/30 cursor-pointer flex items-center justify-center gap-2">
              <RotateCcw size={14} aria-hidden="true" />
              {t('user.record.reRecord')}
            </button>
            <button onClick={handleSubmit} disabled={disabled || !transcript.trim()} aria-disabled={disabled || !transcript.trim()}
              className="flex-1 h-12 rounded-full bg-white text-black text-sm font-semibold tracking-tight hover:scale-[1.02] hover:shadow-[0_0_20px_rgba(255,255,255,0.2)] active:scale-[0.98] disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:scale-100 disabled:hover:shadow-none transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40 cursor-pointer flex items-center justify-center gap-2">
              {disabled
                ? <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                : <Send size={14} aria-hidden="true" />}
              {disabled ? t('user.record.submitting') : t('user.record.submit')}
            </button>
          </>
        )}
      </div>
    </div>
  )
}
