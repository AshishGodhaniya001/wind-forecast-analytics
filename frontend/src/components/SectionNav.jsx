import { useEffect, useState } from 'react'

const SECTIONS = [
  { id: 'summary', label: 'Summary' },
  { id: 'accuracy', label: 'Accuracy' },
  { id: 'charts', label: 'Charts' },
  { id: 'breakdowns', label: 'Breakdowns' },
  { id: 'lead-time-heading', label: 'Lead time' },
  { id: 'methodology-heading', label: 'Method' },
]

export default function SectionNav({ view = 'simple' }) {
  const [activeId, setActiveId] = useState('summary')
  const sections = view === 'detailed' ? SECTIONS : SECTIONS.slice(0, 4)

  useEffect(() => {
    const updateActiveSection = () => {
      const marker = window.scrollY + 150
      let active = SECTIONS[0].id
      sections.forEach(({ id }) => {
        const element = document.getElementById(id)
        if (element && window.scrollY + element.getBoundingClientRect().top <= marker) active = id
      })
      setActiveId(active)
    }
    updateActiveSection()
    window.addEventListener('scroll', updateActiveSection, { passive: true })
    window.addEventListener('resize', updateActiveSection)
    return () => {
      window.removeEventListener('scroll', updateActiveSection)
      window.removeEventListener('resize', updateActiveSection)
    }
  }, [view])

  return (
    <nav className="section-nav" aria-label="Page sections">
      <div className="section-nav__links">
        {sections.map(({ id, label }) => (
          <a
            href={`#${id}`}
            key={id}
            className={activeId === id ? 'section-nav__link section-nav__link--active' : 'section-nav__link'}
            aria-current={activeId === id ? 'location' : undefined}
          >
            {label}
          </a>
        ))}
      </div>
    </nav>
  )
}
