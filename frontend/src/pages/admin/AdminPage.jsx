import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { User, ChevronRight, X, TrendingUp, Brain, Mic2, AlertTriangle, CheckCircle, XCircle, MinusCircle, Shield } from 'lucide-react'
import Threads from '../../components/Threads'
import LangToggle from '../../components/LangToggle'

const API = 'http://localhost:8000'


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
  const color = pct >= 80 ? 'bg-white' : pct >= 60 ? 'bg-zinc-400' : 'bg-zinc-600'
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-1 bg-white/10 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all duration-500`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-mono tabular-nums text-zinc-400 w-8 text-right">{value}</span>
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
        <p className="text-sm font-medium text-white truncate">{c.candidate_name}</p>
        <p className="text-xs text-zinc-500 truncate">
          {c.role} · {t('admin.yearsExp', { count: c.years_experience })}
        </p>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <span className="text-sm font-bold tabular-nums text-white">{c.fit_score}</span>
        <RecIcon size={14} className={color} aria-hidden="true" />
        <ChevronRight size={14} className="text-zinc-700" aria-hidden="true" />
      </div>
    </button>
  )
}

// ── candidate detail panel ────────────────────────────────────────────────────
function CandidateDetail({ c, onClose }) {
  const { t } = useTranslation()
  const { icon: RecIcon, color: recColor } = REC_ICON[c.final_recommendation] ?? { icon: MinusCircle, color: 'text-zinc-500' }

  const scores = [
    { label: t('admin.fields.fitScore'),        icon: TrendingUp,    value: c.fit_score },
    { label: t('admin.fields.knowledgeSkills'), icon: Brain,         value: c.knowledge_and_skills_score },
    { label: t('admin.fields.communication'),   icon: Mic2,          value: c.communication_score },
    { label: t('admin.fields.uncertaintyRisk'), icon: AlertTriangle, value: c.uncertainty_and_risk_score },
  ]

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* Header */}
      <div className="flex items-start justify-between px-6 pt-6 pb-4 border-b border-white/[0.06] shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-11 h-11 rounded-full border border-white/10 bg-zinc-900/90">
            <User size={20} className="text-zinc-400" aria-hidden="true" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-white">{c.candidate_name}</h2>
            <p className="text-xs text-zinc-500">{c.role} · {c.field}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-[10px] font-semibold px-2 py-1 rounded-full border ${LEVEL_STYLE[c.candidate_level] ?? 'bg-zinc-900 text-zinc-500 border-zinc-800'}`}>
            {t(`admin.levels.${c.candidate_level}`, c.candidate_level)}
          </span>
          {onClose && (
            <button onClick={onClose} aria-label={t('admin.sections.close', 'Close')}
              className="flex items-center justify-center w-8 h-8 rounded-lg text-zinc-500 hover:text-white hover:bg-white/10 transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/30">
              <X size={16} aria-hidden="true" />
            </button>
          )}
        </div>
      </div>

      <div className="flex-1 px-6 py-5 space-y-6 overflow-y-auto">

        {/* Recommendation banner */}
        <div className="flex items-center gap-3 px-4 py-3 rounded-xl border border-white/10 bg-zinc-900/90">
          <RecIcon size={18} className={recColor} aria-hidden="true" />
          <div>
            <p className="text-[10px] uppercase tracking-widest text-zinc-600 mb-0.5">{t('admin.sections.recommendation')}</p>
            <p className="text-sm font-semibold text-white">{t(`admin.recommendations.${c.final_recommendation}`, c.final_recommendation)}</p>
          </div>
        </div>

        {/* Score breakdown */}
        <div className="rounded-xl border border-white/10 bg-zinc-900/90 px-5 py-4 space-y-4">
          <p className="text-[10px] uppercase tracking-widest text-zinc-600">{t('admin.sections.scoreBreakdown')}</p>
          {scores.map(({ label, icon: Icon, value }) => (
            <div key={label}>
              <div className="flex items-center gap-2 mb-1.5">
                <Icon size={12} className="text-zinc-500 shrink-0" aria-hidden="true" />
                <span className="text-xs text-zinc-400">{label}</span>
              </div>
              <ScoreBar value={value} />
            </div>
          ))}
        </div>

        {/* Strengths */}
        <div className="rounded-xl border border-white/10 bg-zinc-900/90 px-5 py-4">
          <p className="text-[10px] uppercase tracking-widest text-zinc-600 mb-3">{t('admin.sections.strengths')}</p>
          <p className="text-sm text-zinc-300 leading-relaxed">{c.strengths}</p>
        </div>

        {/* Weaknesses */}
        <div className="rounded-xl border border-white/10 bg-zinc-900/90 px-5 py-4">
          <p className="text-[10px] uppercase tracking-widest text-zinc-600 mb-3">{t('admin.sections.weaknesses')}</p>
          <p className="text-sm text-zinc-300 leading-relaxed">{c.weaknesses}</p>
        </div>

        {/* CV Profile */}
        <div className="rounded-xl border border-white/10 bg-zinc-900/90 px-5 py-4 space-y-3">
          <p className="text-[10px] uppercase tracking-widest text-zinc-600">{t('admin.sections.cvProfile')}</p>

          {[
            { label: t('admin.fields.yearsExperience'), value: t('admin.yearsExp', { count: c.years_experience }) },
            { label: t('admin.fields.education'),       value: c.education },
            { label: t('admin.fields.certification'),   value: c.certification },
            { label: t('admin.fields.coreSkills'),      value: c.core_skills },
            { label: t('admin.fields.tools'),           value: c.tools },
          ].map(({ label, value }) => value && (
            <div key={label} className="flex flex-col gap-0.5">
              <span className="text-[10px] text-zinc-600">{label}</span>
              <span className="text-xs text-zinc-300 leading-relaxed">{value}</span>
            </div>
          ))}
        </div>

        {/* Experience summary */}
        <div className="rounded-xl border border-white/10 bg-zinc-900/90 px-5 py-4">
          <p className="text-[10px] uppercase tracking-widest text-zinc-600 mb-3">{t('admin.sections.experienceSummary')}</p>
          <p className="text-sm text-zinc-300 leading-relaxed">{c.experience_summary}</p>
        </div>

        {/* Edge case — only if present */}
        {c.surprise_edge_case && (
          <div className="rounded-xl border border-white/10 bg-zinc-900/90 px-5 py-4">
            <p className="text-[10px] uppercase tracking-widest text-zinc-600 mb-3">{t('admin.sections.edgeCase')}</p>
            <p className="text-sm text-zinc-300 leading-relaxed">{c.surprise_edge_case}</p>
          </div>
        )}

        {/* Candidate ID */}
        <p className="text-[10px] text-zinc-700 text-center pb-2">{c.candidate_id}</p>
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
      .then(data => { setCandidates(data); if (data.length) setSelected(data[0]) })
      .catch(err => setFetchError(err.message))
      .finally(() => setLoading(false))
  }, [])

  function select(c) { setSelected(c); setPanelOpen(true) }

  return (
    <div className="min-h-dvh bg-black text-white flex flex-col overflow-hidden">
      <div className="fixed z-0 pointer-events-none opacity-20"
        style={{ inset: '-20%', transform: 'rotate(-18deg) scaleX(1.4)', transformOrigin: 'center center' }}>
        <Threads amplitude={1.2} distance={0.4} enableMouseInteraction={false} color={[1, 1, 1]} />
      </div>

      <header className="fixed top-0 inset-x-0 z-50 border-b border-white/[0.06] bg-black/80 backdrop-blur-md shrink-0">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="font-semibold text-white text-base tracking-tight">mir9ad</span>
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
          <div className="flex-1 overflow-y-auto">
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
              onClose={() => setPanelOpen(false)}
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
