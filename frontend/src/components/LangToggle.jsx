import { useTranslation } from 'react-i18next'
import { Languages } from 'lucide-react'

export default function LangToggle() {
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
