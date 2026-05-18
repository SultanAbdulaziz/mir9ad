import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { User, ChevronRight, X, TrendingUp, Brain, Mic2, AlertTriangle, CheckCircle, XCircle, MinusCircle, Shield } from 'lucide-react'
import Threads from '../../components/Threads'
import LangToggle from '../../components/LangToggle'

// ── Mock data — mirrors the DB tables (candidates + cv_profiles) ──────────────
const MOCK_CANDIDATES = [
  {
    // candidates table
    candidate_id:               'CV-001',
    fit_score:                  89,
    knowledge_and_skills_score: 88,
    uncertainty_and_risk_score: 85,
    communication_score:        91,
    final_recommendation:       'Recommend',
    strengths:                  'Clear evidence of role-specific results; structured problem-solving and strong ownership; confident delivery',
    weaknesses:                 'May need onboarding on company-specific processes; limited enterprise-scale experience',
    // cv_profiles table
    candidate_name:      'Ibrahim Alharbi',
    role:                'Project Manager',
    field:               'Management',
    candidate_level:     'Strong',
    years_experience:    9,
    education:           'BSc Industrial Engineering',
    certification:       'PMP',
    core_skills:         'Project planning, Risk management, Stakeholder communication, Agile/Scrum, Budget tracking',
    tools:               'Asana, PowerPoint, MS Project',
    experience_summary:  'Led agile ceremonies in 3+ projects with measurable impact; independently handled complex situations and explained decisions clearly.',
    expected_strengths:  'Clear evidence of role-specific results; structured problem-solving',
    expected_weaknesses: 'May need onboarding on company-specific processes',
    surprise_edge_case:  '',
    expected_fit_score:  89,
    expected_recommendation: 'Recommend',
  },
  {
    candidate_id:               'CV-002',
    fit_score:                  72,
    knowledge_and_skills_score: 70,
    uncertainty_and_risk_score: 68,
    communication_score:        75,
    final_recommendation:       'Maybe / needs further assessment',
    strengths:                  'Adequate exposure to key areas; growing practical experience; good communicator',
    weaknesses:                 'Could improve cross-domain exposure; needs more ownership of end-to-end delivery',
    candidate_name:      'Dina Alghamdi',
    role:                'Project Manager',
    field:               'Management',
    candidate_level:     'Average',
    years_experience:    6,
    education:           'BSc Industrial Engineering',
    certification:       'AWS Developer Associate',
    core_skills:         'Project planning, Risk management, Stakeholder communication, Agile/Scrum, Confluence',
    tools:               'MS Project, Asana, PowerPoint',
    experience_summary:  'Managed stakeholder alignment in 3+ projects; handled complex situations with moderate ownership.',
    expected_strengths:  'Adequate exposure; growing experience',
    expected_weaknesses: 'Limited cross-domain depth; needs more ownership',
    surprise_edge_case:  '',
    expected_fit_score:  82,
    expected_recommendation: 'Recommend',
  },
  {
    candidate_id:               'CV-003',
    fit_score:                  38,
    knowledge_and_skills_score: 35,
    uncertainty_and_risk_score: 42,
    communication_score:        40,
    final_recommendation:       'Do not recommend',
    strengths:                  'Foundational skills present; shows motivation and willingness to learn',
    weaknesses:                 'Limited hands-on experience; requires significant mentoring; skill claims weakly supported',
    candidate_name:      'Mona Alqahtani',
    role:                'Project Manager',
    field:               'Management',
    candidate_level:     'Weak',
    years_experience:    0,
    education:           'BSc Information Systems',
    certification:       'University project certificate',
    core_skills:         'Project planning, Problem solving, PowerPoint, Basic communication',
    tools:               'Asana, MS Project, Confluence',
    experience_summary:  'Basic exposure through coursework and one short-term coordinator role; limited real ownership.',
    expected_strengths:  'Foundational skills; shows potential',
    expected_weaknesses: 'Limited professional experience; requires significant mentoring',
    surprise_edge_case:  '',
    expected_fit_score:  25,
    expected_recommendation: 'Do not recommend',
  },
  {
    candidate_id:               'CV-004',
    fit_score:                  61,
    knowledge_and_skills_score: 58,
    uncertainty_and_risk_score: 55,
    communication_score:        66,
    final_recommendation:       'Conditional / requires follow-up interview',
    strengths:                  'Transferable skills from prior background; unique perspective; strong communication',
    weaknesses:                 'Limited technical depth in target role; may face credibility gap without PM track record',
    candidate_name:      'Fatimah Alsaud',
    role:                'Project Manager',
    field:               'Management',
    candidate_level:     'Unusual/Surprise',
    years_experience:    11,
    education:           'MBA',
    certification:       'Bootcamp certificate',
    core_skills:         'Problem solving, Project planning, Risk management, Excel, Confluence, Transferable skills',
    tools:               'PowerPoint, Asana, Confluence',
    experience_summary:  'Career switcher from education sector with strong communication skills; handled ambiguous situations but limited technical PM depth.',
    expected_strengths:  'Transferable skills; strong communication; unique perspective',
    expected_weaknesses: 'Limited technical PM depth; credibility gap requires probing',
    surprise_edge_case:  'Career switcher from education with strong communication but limited technical depth',
    expected_fit_score:  55,
    expected_recommendation: 'Conditional / requires follow-up interview',
  },
  {
    candidate_id:               'CV-005',
    fit_score:                  95,
    knowledge_and_skills_score: 94,
    uncertainty_and_risk_score: 92,
    communication_score:        96,
    final_recommendation:       'Recommend',
    strengths:                  'Exceptional clarity and structured thinking; measurable impact across all projects; outstanding stakeholder management',
    weaknesses:                 'May be overqualified for junior PM roles; could benefit from broader industry exposure',
    candidate_name:      'Mariam Alotaibi',
    role:                'Project Manager',
    field:               'Management',
    candidate_level:     'Strong',
    years_experience:    8,
    education:           'BSc Management',
    certification:       'Microsoft PL-300',
    core_skills:         'Project planning, Risk management, Stakeholder communication, Agile/Scrum, Budget tracking, Jira, Confluence',
    tools:               'Excel, Confluence, Asana',
    experience_summary:  'Handled project risks and budgets across 3+ projects with consistent measurable impact; strong stakeholder response record.',
    expected_strengths:  'Solid tool knowledge; clear practical examples; strong ownership',
    expected_weaknesses: 'May need onboarding on company-specific processes',
    surprise_edge_case:  '',
    expected_fit_score:  95,
    expected_recommendation: 'Recommend',
  },
]

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
  const [selected, setSelected] = useState(MOCK_CANDIDATES[0])
  const [panelOpen, setPanelOpen] = useState(false)

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
            <span className="text-xs text-zinc-600">{t('admin.applicantsCount', { count: MOCK_CANDIDATES.length })}</span>
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
            {MOCK_CANDIDATES.map(c => (
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
