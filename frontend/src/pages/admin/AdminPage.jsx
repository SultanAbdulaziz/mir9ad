import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { User, ChevronRight, X, TrendingUp, Brain, Mic2, AlertTriangle, CheckCircle, XCircle, MinusCircle, Shield } from 'lucide-react'
import Threads from '../../components/Threads'
import LangToggle from '../../components/LangToggle'

const API = import.meta.env.VITE_API_URL ?? ''


// ── helpers ───────────────────────────────────────────────────────────────────
const LEVEL_STYLE = {
  'Strong':           'bg-white/10 text-white border-white/20',
  'Average':          'bg-zinc-800 text-zinc-300 border-zinc-700',
  'Weak':             'bg-zinc-900 text-zinc-500 border-zinc-800',
  'Unusual/Surprise': 'bg-zinc-800 text-zinc-400 border-zinc-700',
}

const REC_ICON = {
  'Recommend':                          { icon: CheckCircle,  color: 'text-white' },
  'Maybe / needs further assessment':   { icon: MinusCircle,  color: 'text-zinc-400' },
  'Do not recommend':                   { icon: XCircle,      color: 'text-zinc-600' },
  'Conditional / requires follow-up interview': { icon: Shield, color: 'text-zinc-400' },
}

function ScoreBar({ value, max = 100 }) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100))
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-1.5 bg-white/10 rounded-full overflow-hidden">
        <div className="h-full bg-white rounded-full transition-all duration-500" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-mono tabular-nums text-white w-8 text-right">{value}</span>
    </div>
  )
}

// ── candidate list row ────────────────────────────────────────────────────────
function CandidateRow({ c, selected, onClick }) {
  const { t } = useTranslation()
  const { icon: RecIcon, color } = REC_ICON[c.final_recommendation] ?? { icon: MinusCircle, color: 'text-zinc-500' }
  return (
    <button
      onClick={onClick}
      aria-pressed={selected}
      className={[
        'w-full text-left px-4 py-4 flex items-center gap-3 border-b border-white/[0.06]',
        'transition-colors duration-150 cursor-pointer focus-visible:outline-none focus-visible:ring-inset focus-visible:ring-1 focus-visible:ring-white/30',
        selected ? 'bg-white/[0.06]' : 'hover:bg-white/[0.03]',
      ].join(' ')}
    >
      <div className="flex items-center justify-center w-9 h-9 rounded-full border border-white/10 bg-zinc-900/90 shrink-0">
        <User size={16} className="text-zinc-500" aria-hidden="true" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-white truncate">{c.candidate_name}</p>
        <p className="text-xs text-zinc-400 truncate">
          {c.role} · {t('admin.yearsExp', { count: c.years_experience })}
        </p>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <span className="text-sm font-bold tabular-nums text-white">{c.fit_score}</span>
        <RecIcon size={14} className={color} aria-hidden="true" />
        <ChevronRight size={14} className="text-zinc-500" aria-hidden="true" />
      </div>
    </button>
  )
}

// ── candidate detail panel ────────────────────────────────────────────────────
function CandidateDetail({ c, onDelete }) {
  const { t } = useTranslation()
  const [confirm,   setConfirm]   = useState(false)
  const [deleting,  setDeleting]  = useState(false)
  const { icon: RecIcon, color: recColor } = REC_ICON[c.final_recommendation] ?? { icon: MinusCircle, color: 'text-zinc-500' }

  const scores = [
    { label: t('admin.fields.fitScore'),        icon: TrendingUp,    value: c.fit_score },
    { label: t('admin.fields.knowledgeSkills'), icon: Brain,         value: c.knowledge_and_skills_score },
    { label: t('admin.fields.communication'),   icon: Mic2,          value: c.communication_score },
    { label: t('admin.fields.uncertaintyRisk'), icon: AlertTriangle, value: c.uncertainty_and_risk_score },
  ]

  async function handleDelete() {
    setDeleting(true)
    try {
      await fetch(`${API}/admin/candidates/${c.candidate_id}`, { method: 'DELETE' })
      onDelete?.(c.candidate_id)
    } finally {
      setDeleting(false)
      setConfirm(false)
    }
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* Header */}
      <div className="flex items-start justify-between px-6 pt-6 pb-4 border-b border-white/[0.06] shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-11 h-11 rounded-full border border-white/10 bg-zinc-900/90">
            <User size={20} className="text-zinc-300" aria-hidden="true" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-white">{c.candidate_name}</h2>
            <p className="text-xs text-zinc-400">{c.role} · {c.field}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-[10px] font-semibold px-2 py-1 rounded-full border ${LEVEL_STYLE[c.candidate_level] ?? 'bg-zinc-900 text-zinc-500 border-zinc-800'}`}>
            {t(`admin.levels.${c.candidate_level}`, c.candidate_level)}
          </span>
          {!confirm ? (
            <button onClick={() => setConfirm(true)} aria-label="Discard candidate"
              className="flex items-center justify-center w-8 h-8 rounded-lg text-zinc-600 hover:text-red-400 hover:bg-red-950/40 transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500/40">
              <X size={16} aria-hidden="true" />
            </button>
          ) : (
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] text-zinc-400">Discard?</span>
              <button onClick={handleDelete} disabled={deleting}
                className="px-2 py-1 text-[10px] font-semibold rounded-md bg-red-600 hover:bg-red-500 text-white disabled:opacity-50 transition-colors cursor-pointer">
                {deleting ? '…' : 'Yes'}
              </button>
              <button onClick={() => setConfirm(false)}
                className="px-2 py-1 text-[10px] font-semibold rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors cursor-pointer">
                No
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 px-6 py-5 space-y-6 overflow-y-auto">

        {/* Recommendation banner */}
        <div className="flex items-center gap-3 px-4 py-3 rounded-xl border border-white/10 bg-zinc-900/90">
          <RecIcon size={18} className={recColor} aria-hidden="true" />
          <div>
            <p className="text-[10px] uppercase tracking-widest text-zinc-400 mb-0.5">{t('admin.sections.recommendation')}</p>
            <p className="text-sm font-semibold text-white">{t(`admin.recommendations.${c.final_recommendation}`, c.final_recommendation)}</p>
          </div>
        </div>

        {/* Score breakdown */}
        <div className="rounded-xl border border-white/10 bg-zinc-900/90 px-5 py-4 space-y-4">
          <p className="text-[10px] uppercase tracking-widest text-zinc-400">{t('admin.sections.scoreBreakdown')}</p>
          {scores.map(({ label, icon: Icon, value }) => (
            <div key={label}>
              <div className="flex items-center gap-2 mb-1.5">
                <Icon size={12} className="text-zinc-500 shrink-0" aria-hidden="true" />
                <span className="text-xs text-zinc-300">{label}</span>
              </div>
              <ScoreBar value={value} />
            </div>
          ))}
        </div>

        {/* Strengths */}
        <div className="rounded-xl border border-white/10 bg-zinc-900/90 px-5 py-4">
          <p className="text-[10px] uppercase tracking-widest text-zinc-400 mb-3">{t('admin.sections.strengths')}</p>
          <p className="text-sm text-white leading-relaxed">{c.strengths}</p>
        </div>

        {/* Weaknesses */}
        <div className="rounded-xl border border-white/10 bg-zinc-900/90 px-5 py-4">
          <p className="text-[10px] uppercase tracking-widest text-zinc-400 mb-3">{t('admin.sections.weaknesses')}</p>
          <p className="text-sm text-white leading-relaxed">{c.weaknesses}</p>
        </div>

        {/* CV Profile */}
        <div className="rounded-xl border border-white/10 bg-zinc-900/90 px-5 py-4 space-y-3">
          <p className="text-[10px] uppercase tracking-widest text-zinc-400">{t('admin.sections.cvProfile')}</p>

          {[
            { label: t('admin.fields.yearsExperience'), value: t('admin.yearsExp', { count: c.years_experience }) },
            { label: t('admin.fields.education'),       value: c.education },
            { label: t('admin.fields.certification'),   value: c.certification },
            { label: t('admin.fields.coreSkills'),      value: c.core_skills },
            { label: t('admin.fields.tools'),           value: c.tools },
          ].map(({ label, value }) => value && (
            <div key={label} className="flex flex-col gap-0.5">
              <span className="text-[10px] text-zinc-400 uppercase tracking-wide">{label}</span>
              <span className="text-xs text-white leading-relaxed">{value}</span>
            </div>
          ))}
        </div>

        {/* Experience summary */}
        <div className="rounded-xl border border-white/10 bg-zinc-900/90 px-5 py-4">
          <p className="text-[10px] uppercase tracking-widest text-zinc-400 mb-3">{t('admin.sections.experienceSummary')}</p>
          <p className="text-sm text-white leading-relaxed">{c.experience_summary}</p>
        </div>

        {/* Edge case — only if present */}
        {c.surprise_edge_case && (
          <div className="rounded-xl border border-white/10 bg-zinc-900/90 px-5 py-4">
            <p className="text-[10px] uppercase tracking-widest text-zinc-400 mb-3">{t('admin.sections.edgeCase')}</p>
            <p className="text-sm text-white leading-relaxed">{c.surprise_edge_case}</p>
          </div>
        )}

        {/* Interview Q&A log */}
        {c.interview_qa && c.interview_qa.length > 0 && (
          <div className="rounded-xl border border-white/10 bg-zinc-900/90 px-5 py-4 space-y-5">
            <p className="text-[10px] uppercase tracking-widest text-zinc-400">{t('admin.sections.interviewLog')}</p>
            {c.interview_qa.map((qa, i) => (
              <div key={i} className="flex flex-col gap-2">
                {/* Question */}
                <div className="flex items-start gap-2">
                  <span className="text-[10px] font-mono text-zinc-600 shrink-0 mt-0.5">Q{i + 1}</span>
                  <p className="text-xs text-zinc-400 leading-relaxed">{qa.question}</p>
                </div>
                {/* Answer */}
                <div className="flex items-start gap-2 pl-4">
                  <span className="text-[10px] font-mono text-zinc-600 shrink-0 mt-0.5">A</span>
                  <p className="text-xs text-white leading-relaxed">{qa.answer || '—'}</p>
                </div>
                {/* Scores */}
                <div className="flex items-center gap-3 pl-4">
                  <span className="text-[10px] text-zinc-600">Score</span>
                  <span className="text-[10px] font-mono text-white tabular-nums">{qa.answer_score ?? qa.content_score ?? '—'}</span>
                  {qa.delivery_score != null && (
                    <>
                      <span className="text-[10px] text-zinc-600">Delivery</span>
                      <span className="text-[10px] font-mono text-white tabular-nums">{qa.delivery_score}</span>
                    </>
                  )}
                  <span className="text-[10px] text-zinc-600 ml-auto">{qa.dimension?.replace(/_/g, ' ')}</span>
                </div>
                {i < c.interview_qa.length - 1 && (
                  <div className="border-t border-white/[0.05] pt-1" aria-hidden="true" />
                )}
              </div>
            ))}
          </div>
        )}

        {/* Candidate ID */}
        <p className="text-[10px] text-zinc-600 text-center pb-4">{c.candidate_id}</p>
      </div>
    </div>
  )
}

// ── page ──────────────────────────────────────────────────────────────────────
export default function AdminPage() {
  const { t } = useTranslation()
  const [candidates, setCandidates] = useState([])
  const [loading,    setLoading]    = useState(true)
  const [fetchError, setFetchError] = useState('')
  const [selected,   setSelected]   = useState(null)
  const [panelOpen,  setPanelOpen]  = useState(false)

  useEffect(() => {
    fetch(`${API}/admin/candidates`)
      .then(r => { if (!r.ok) throw new Error(`Server error: ${r.status}`); return r.json() })
      .then(data => {
        setCandidates(data)
        if (data.length) setSelected(data[0])
        setLoading(false)   // batched with above — single render
      })
      .catch(err => {
        setFetchError(err.message)
        setLoading(false)
      })
  }, [])

  function select(c) { setSelected(c); setPanelOpen(true) }

  return (
    <div className="min-h-dvh bg-black text-white flex flex-col overflow-hidden">
      <div className="fixed z-0 pointer-events-none opacity-30"
        style={{ inset: '-20%', transform: 'rotate(-18deg) scaleX(1.4)', transformOrigin: 'center center' }}>
        <Threads amplitude={1.2} distance={0.4} enableMouseInteraction={false} color={[1, 1, 1]} />
      </div>

      <header className="fixed top-0 inset-x-0 z-50 border-b border-white/[0.06] bg-black/80 backdrop-blur-md shrink-0">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="font-semibold text-white text-base" dir="rtl">مرصاد</span>
            <span className="text-[10px] font-medium px-2 py-0.5 rounded-full border border-white/10 text-zinc-500 uppercase tracking-wider">{t('admin.badge')}</span>
          </div>
          <div className="flex items-center gap-4">
            {!loading && <span className="text-xs text-zinc-600">{t('admin.applicantsCount', { count: candidates.length })}</span>}
            <LangToggle />
          </div>
        </div>
      </header>

      {/* Body — split layout */}
      <div className="flex flex-1 pt-16 relative z-10 overflow-hidden" style={{ height: '100dvh' }}>

        {/* Left: candidate list */}
        <aside className={[
          'flex flex-col border-r border-white/[0.06] bg-black/60 backdrop-blur-sm overflow-hidden',
          'w-full lg:w-80 xl:w-96 shrink-0',
          // On mobile, hide list when panel is open
          panelOpen ? 'hidden lg:flex' : 'flex',
        ].join(' ')}>
          <div className="px-5 py-4 border-b border-white/[0.06] shrink-0">
            <h1 className="text-sm font-semibold text-white">{t('admin.listHeading')}</h1>
            <p className="text-xs text-zinc-600 mt-0.5">{t('admin.listSubheading')}</p>
          </div>
          <div
            className="flex-1 overflow-y-auto transition-opacity duration-300"
            style={{ opacity: loading ? 0 : 1 }}
          >
            {loading && (
              <div className="flex items-center justify-center gap-2 py-16 text-zinc-600 text-sm">
                <span className="w-4 h-4 border-2 border-zinc-700 border-t-zinc-400 rounded-full animate-spin" aria-hidden="true" />
                Loading…
              </div>
            )}
            {fetchError && (
              <p className="px-5 py-8 text-xs text-zinc-600 text-center">{fetchError}</p>
            )}
            {!loading && !fetchError && candidates.length === 0 && (
              <p className="px-5 py-8 text-xs text-zinc-600 text-center">No candidates yet.</p>
            )}
            {candidates.map(c => (
              <CandidateRow
                key={c.candidate_id}
                c={c}
                selected={selected?.candidate_id === c.candidate_id}
                onClick={() => select(c)}
              />
            ))}
          </div>
        </aside>

        {/* Right: detail panel */}
        <main className={[
          'flex-1 overflow-hidden bg-black/40',
          panelOpen ? 'flex flex-col' : 'hidden lg:flex lg:flex-col',
        ].join(' ')}>
          {selected ? (
            <CandidateDetail
              c={selected}
              onDelete={(id) => {
                setCandidates(prev => prev.filter(c => c.candidate_id !== id))
                setSelected(null)
                setPanelOpen(false)
              }}
            />
          ) : (
            <div className="flex-1 flex items-center justify-center text-zinc-700 text-sm">
              {t('admin.empty')}
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
