import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { client, errMsg, unwrap } from '../lib/api/client'
import { useAsync, useDebounced } from '../lib/hooks'
import { ActionBadge, Badge, Empty, ErrorBox, fmtMoney, Loading, pct } from '../components/ui'

const SKIP_KEY = 'gigbid.skipped'
function loadSkipped(): string[] {
  try { return JSON.parse(localStorage.getItem(SKIP_KEY) ?? '[]') } catch { return [] }
}

export default function Inbox() {
  const nav = useNavigate()
  const [q, setQ] = useState('')
  const dq = useDebounced(q)
  const [skipped, setSkipped] = useState<string[]>(loadSkipped)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [actionErr, setActionErr] = useState('')
  const { data, error, loading, reload } = useAsync(
    () => unwrap(client.GET('/api/jobs', { params: { query: { q: dq, limit: 50 } } })),
    [dq],
  )

  function skip(id: string) {
    const next = [...skipped, id]
    setSkipped(next)
    try { localStorage.setItem(SKIP_KEY, JSON.stringify(next)) } catch { /* ignore */ }
  }

  async function analyze(jobId: string) {
    setBusyId(jobId)
    setActionErr('')
    try {
      const r = await unwrap(client.POST('/api/jobs/{job_id}/analyze', { params: { path: { job_id: jobId } } }))
      nav(`/runs/${encodeURIComponent(r.thread_id)}`)
    } catch (e) {
      setActionErr(errMsg(e))
      setBusyId(null)
    }
  }

  const jobs = (data ?? []).filter((j) => !skipped.includes(j.job_id))
  const needle = q.trim().toLowerCase()
  const shown = needle ? jobs.filter((j) => `${j.title} ${j.category ?? ''}`.toLowerCase().includes(needle)) : jobs

  return (
    <>
      <h1>Job inbox</h1>
      <p className="muted">Ranked by how well your portfolio fits. Analyse a job to get a risk report and a grounded draft.</p>
      <div className="toolbar">
        <label htmlFor="filter">Filter jobs</label>
        <input id="filter" type="search" placeholder="Title, category or search query" value={q} onChange={(e) => setQ(e.target.value)} />
        {skipped.length > 0 && (
          <button className="btn small" onClick={() => { setSkipped([]); try { localStorage.removeItem(SKIP_KEY) } catch { /* ignore */ } }}>
            Show {skipped.length} skipped
          </button>
        )}
      </div>
      {actionErr && <p className="error" role="alert">{actionErr}</p>}
      {loading && <Loading label="Loading jobs" />}
      {error && <ErrorBox error={error} retry={() => reload()} />}
      {!loading && !error && shown.length === 0 && <Empty>No jobs match. Try clearing the filter or check the marketplace connection in Settings.</Empty>}
      <ul className="cards" aria-label="Jobs">
        {shown.map((j) => {
          const flags = j.risk_flags ?? []
          const price = j.price as { type?: string; amount?: number; connects_cost?: number } | null | undefined
          const connects = price?.connects_cost ?? j.connects_cost
          return (
            <li key={j.job_id} className="card job">
              <div className="job-head">
                <h2>{j.title}</h2>
                <ActionBadge action={j.action} />
              </div>
              <div className="meta">
                {j.category && <Badge>{j.category}</Badge>}
                <span>
                  {j.is_hourly && j.hourly_low != null ? `$${j.hourly_low}-${j.hourly_high ?? '?'}/hr` : fmtMoney(j.budget)}
                </span>
                {j.fit != null && <Badge tone={j.fit >= 0.6 ? 'good' : j.fit >= 0.35 ? 'warn' : 'bad'}>Fit {pct(j.fit)}</Badge>}
                {j.risk_score != null && <Badge tone={j.risk_score >= 0.5 ? 'bad' : 'neutral'}>Risk {pct(j.risk_score)}</Badge>}
                {flags.map((f) => <Badge key={f} tone={/scam/i.test(f) ? 'bad' : 'warn'}>{f}</Badge>)}
              </div>
              <p className="muted">
                {price?.amount != null && <>Suggested price {fmtMoney(price.amount)}{price.type ? ` (${price.type})` : ''}. </>}
                {connects != null && <>Connects cost: {connects}.</>}
                {j.status && <> Status: {j.status.replace(/_/g, ' ')}.</>}
              </p>
              <div className="row">
                {!j.thread_id ? (
                  <button className="btn primary" disabled={busyId === j.job_id} onClick={() => analyze(j.job_id)}>
                    {busyId === j.job_id ? 'Starting...' : 'Analyze'}
                  </button>
                ) : (
                  <>
                    <Link className="btn primary" to={`/jobs/${encodeURIComponent(j.thread_id)}`}>Open detail</Link>
                    {j.status === 'awaiting_approval' && (
                      <Link className="btn" to={`/studio/${encodeURIComponent(j.thread_id)}`}>Review proposal</Link>
                    )}
                  </>
                )}
                <button className="btn" onClick={() => skip(j.job_id)} aria-label={`Skip ${j.title}`}>Skip</button>
              </div>
            </li>
          )
        })}
      </ul>
    </>
  )
}
