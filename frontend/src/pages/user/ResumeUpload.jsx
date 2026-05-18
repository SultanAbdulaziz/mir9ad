import { useRef, useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { UploadCloud, FileText, X, AlertCircle, CheckCircle2, Loader2 } from 'lucide-react'

const ACCEPTED_TYPES = ['application/pdf']
const ACCEPTED_EXTS  = ['.pdf']
const MAX_BYTES     = 5 * 1024 * 1024

function formatBytes(b) {
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / (1024 * 1024)).toFixed(1)} MB`
}

export default function ResumeUpload({ onNext, disabled: parentDisabled = false }) {
  const { t }    = useTranslation()
  const inputRef = useRef(null)
  const [file,     setFile]     = useState(null)
  const [dragging, setDragging] = useState(false)
  const [error,    setError]    = useState('')
  const [loading,  setLoading]  = useState(false)
  const frozen = loading || parentDisabled

  function validate(f) {
    const ok = ACCEPTED_TYPES.includes(f.type) ||
      ACCEPTED_EXTS.some(e => f.name.toLowerCase().endsWith(e))
    if (!ok) return t('user.upload.errors.type')
    if (f.size > MAX_BYTES) return t('user.upload.errors.size')
    return ''
  }

  async function handleFile(f) {
    const err = validate(f)
    if (err) { setError(err); setFile(null); return }
    setError('')
    setFile(f)
    // Brief visual feedback before advancing
    setLoading(true)
    await new Promise(r => setTimeout(r, 600))
    onNext?.(f)
  }

  const onDrop      = useCallback((e) => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) handleFile(f) }, [])
  const onDragOver  = useCallback((e) => { e.preventDefault(); setDragging(true)  }, [])
  const onDragLeave = useCallback(() => setDragging(false), [])

  return (
    <div className="w-full max-w-lg flex flex-col gap-5 animate-fade-in-up">

      {/* Drop zone */}
      <div
        role="button"
        tabIndex={0}
        aria-label={t('user.upload.dropzone')}
        onClick={() => !frozen && inputRef.current?.click()}
        onKeyDown={(e) => e.key === 'Enter' && !frozen && inputRef.current?.click()}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        className={[
          'relative flex flex-col items-center justify-center gap-4 rounded-2xl border px-8 py-14 text-center select-none outline-none',
          'transition-all duration-200',
          'focus-visible:ring-2 focus-visible:ring-white/40',
          frozen   ? 'cursor-default border-white/20 bg-zinc-900/90'
          : dragging ? 'cursor-copy border-white/40 bg-zinc-800/90'
          : file    ? 'cursor-default border-white/20 bg-zinc-900/90'
          :            'cursor-pointer border-white/10 bg-zinc-900/80 hover:border-white/20 hover:bg-zinc-900/90',
        ].join(' ')}
      >
        {/* Shimmer on drag */}
        {dragging && (
          <div className="absolute inset-0 rounded-2xl overflow-hidden pointer-events-none" aria-hidden="true">
            <div className="absolute top-0 left-[-100%] w-[50%] h-full bg-gradient-to-r from-transparent via-white/10 to-transparent skew-x-12 animate-[shimmer_1s_infinite]" />
          </div>
        )}

        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_EXTS.join(',')}
          className="sr-only"
          aria-hidden="true"
          onChange={(e) => e.target.files[0] && handleFile(e.target.files[0])}
        />

        {/* Icon */}
        <div className={[
          'flex items-center justify-center w-14 h-14 rounded-2xl border transition-all duration-200',
          loading  ? 'border-white/20 bg-white/10 text-white'
          : dragging ? 'border-white/30 bg-white/10 text-white'
          :            'border-white/10 bg-zinc-900/90 text-zinc-400',
        ].join(' ')}>
          {loading
            ? <Loader2 size={26} className="animate-spin" aria-hidden="true" />
            : <UploadCloud size={26} aria-hidden="true" />
          }
        </div>

        {loading ? (
          <p className="text-sm text-zinc-400">{t('user.upload.uploading')}</p>
        ) : (
          <>
            <div>
              <p className="text-base font-medium text-white mb-1">{t('user.upload.dropzone')}</p>
              <p className="text-sm text-zinc-500">
                {t('user.upload.or')}{' '}
                <span className="text-zinc-300 underline underline-offset-2 decoration-white/30">
                  {t('user.upload.browse')}
                </span>
              </p>
            </div>
            <p className="text-xs text-zinc-600">{t('user.upload.accepted')}</p>
          </>
        )}
      </div>

      {/* Error */}
      {error && (
        <div
          role="alert"
          aria-live="polite"
          className="flex items-start gap-3 px-4 py-3 rounded-xl bg-zinc-900/90 border border-white/10 text-sm text-zinc-400"
        >
          <AlertCircle size={16} className="shrink-0 mt-0.5 text-zinc-500" aria-hidden="true" />
          {error}
        </div>
      )}

      {/* Selected file (shown briefly before advancing) */}
      {file && !error && (
        <div className="flex items-center gap-3 px-4 py-3 rounded-xl border border-white/10 bg-zinc-900/90">
          <div className="flex items-center justify-center w-9 h-9 rounded-lg border border-white/10 bg-white/5 text-zinc-300 shrink-0">
            <FileText size={18} aria-hidden="true" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-white truncate">{file.name}</p>
            <p className="text-xs text-zinc-500">{formatBytes(file.size)}</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <CheckCircle2 size={16} className="text-white/60" aria-hidden="true" />
            {!loading && (
              <button
                onClick={(e) => { e.stopPropagation(); setFile(null) }}
                aria-label={t('user.upload.remove')}
                className="flex items-center justify-center w-8 h-8 rounded-lg text-zinc-600 hover:text-white hover:bg-white/10 transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/30 cursor-pointer"
              >
                <X size={15} aria-hidden="true" />
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
