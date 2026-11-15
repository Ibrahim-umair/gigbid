import type { ReactNode } from 'react'
import { ApiError } from '../lib/api/client'

export function Loading({ label = 'Loading' }: { label?: string }) {
  return (
    <p className="muted" role="status">
      <span className="spinner" aria-hidden="true" /> {label}...
    </p>
  )
}

export function ErrorBox({ error, retry }: { error: Error; retry?: () => void }) {
  const unavailable = error instanceof ApiError && error.status === 503
  return (
    <div className="error" role="alert">
      <strong>{unavailable ? 'Marketplace unavailable.' : 'Something went wrong.'}</strong> {error.message}
      {retry && (
        <button className="btn small" onClick={retry}>
          Retry
        </button>
      )}
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>
}

export function Badge({ tone = 'neutral', children }: { tone?: 'neutral' | 'good' | 'warn' | 'bad' | 'info'; children: ReactNode }) {
  return <span className={`badge ${tone}`}>{children}</span>
}

export function ActionBadge({ action }: { action?: string | null }) {
  if (!action) return null
  const tone = action === 'bid' ? 'good' : action === 'watch' ? 'warn' : 'neutral'
  return <Badge tone={tone}>{action.toUpperCase()}</Badge>
}

export function StrengthBadge({ s }: { s: string }) {
  return <Badge tone={s === 'strong' ? 'good' : s === 'partial' ? 'warn' : 'bad'}>{s}</Badge>
}

export function Section({ title, children, id }: { title: string; children: ReactNode; id?: string }) {
  return (
    <section className="card" aria-labelledby={id}>
      <h2 id={id}>{title}</h2>
      {children}
    </section>
  )
}

export function List({ items }: { items?: string[] }) {
  if (!items?.length) return <p className="muted">None.</p>
  return (
    <ul>
      {items.map((x, i) => (
        <li key={i}>{x}</li>
      ))}
    </ul>
  )
}

export function KeyValue({ data }: { data: unknown }) {
  if (data === null || data === undefined) return <span className="muted">-</span>
  if (typeof data !== 'object') return <>{String(data)}</>
  const entries = Object.entries(data as Record<string, unknown>)
  if (!entries.length) return <span className="muted">empty</span>
  return (
    <dl className="kv">
      {entries.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>
            <KeyValue data={v} />
          </dd>
        </div>
      ))}
    </dl>
  )
}

export const fmtMoney = (n?: number | null) => (n == null ? '-' : `$${Number(n).toLocaleString()}`)
export const pct = (n?: number | null) => (n == null ? '-' : `${Math.round(n * (n <= 1 ? 100 : 1))}%`)
