import { useId, useState, type ReactNode } from 'react'
import type { Evidence } from '../lib/types'

/** Focusable wrapper that reveals evidence (title + snippet) on hover or keyboard focus. */
export default function EvidenceHover({
  evidence,
  ids,
  children,
  className = '',
}: {
  evidence: Record<string, Evidence>
  ids: string[]
  children: ReactNode
  className?: string
}) {
  const [show, setShow] = useState(false)
  const tipId = useId()
  const items = ids.map((id) => evidence[id] ?? { id, title: id, snippet: 'Evidence item not found in this run.' })
  return (
    <span
      className={`evhover ${className}`}
      tabIndex={0}
      aria-describedby={show ? tipId : undefined}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      onFocus={() => setShow(true)}
      onBlur={() => setShow(false)}
      onKeyDown={(e) => e.key === 'Escape' && setShow(false)}
    >
      {children}
      {show && (
        <span role="tooltip" id={tipId} className="evtip">
          {items.length === 0 && <strong className="warn-text">No evidence cited for this claim.</strong>}
          {items.map((e) => (
            <span key={e.id} className="evitem">
              <strong>{e.title ?? e.id}</strong>
              {e.type && <em> ({e.type})</em>}
              <span className="evsnip">{e.snippet}</span>
            </span>
          ))}
        </span>
      )}
    </span>
  )
}
