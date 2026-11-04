/** A titled surface used by the non-chart dashboard sections. */
export default function Panel({ id, title, subtitle, children, footer, className = '' }) {
  return (
    <section className={`card ${className}`.trim()} aria-labelledby={id}>
      <header className="card__header">
        <div>
          <h2 id={id}>{title}</h2>
          {subtitle ? <p className="card__subtitle">{subtitle}</p> : null}
        </div>
      </header>
      <div className="card__body">{children}</div>
      {footer ? <div className="card__footer">{footer}</div> : null}
    </section>
  )
}
