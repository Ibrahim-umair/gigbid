import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { client, unwrap } from '../lib/api/client'
import { currentToken } from '../lib/auth'
import type { ThreadValues, TraceItem } from '../lib/types'
import { Badge, Section } from '../components/ui'

type NodeEv = { key: string; node: string; info: Record<string, unknown> }

export function RunTimeline({ threadId, onDone }: { threadId: string; onDone: (summary: Record<string, unknown>) => void }) {
  const [events, setEvents] = useState<NodeEv[]>([])
  const [state, setState] = useState<'connecting' | 'running' | 'done' | 'lost'>('connecting')
  const doneRef = useRef(onDone)
  doneRef.current = onDone

  useEffect(() => {
    const es = new EventSource(`/api/runs/${encodeURIComponent(threadId)}/stream?token=${encodeURIComponent(currentToken() ?? '')}`)
    es.onopen = () => setState((s) => (s === 'done' ? s : 'running'))
    es.addEventListener('node', (e) => {
      setState('running')
      try {
        const d = JSON.parse((e as MessageEvent).data) as { node: string; info?: Record<string, unknown> }
        const info = d.info ?? {}
        const key = `${d.node}|${String(info.ts ?? '')}`
        setEvents((prev) => (prev.some((p) => p.key === key) ? prev : [...prev, { key, node: d.node, info }]))
      } catch { /* ignore malformed event */ }
    })
    es.addEventListener('done', (e) => {
      let summary: Record<string, unknown> = {}
      try { summary = JSON.parse((e as MessageEvent).data) } catch { /* ignore */ }
      setState('done')
      es.close()
      doneRef.current(summary)
    })
    es.onerror = () => setState((s) => (s === 'done' ? s : 'lost'))
    return () => es.close()
  }, [threadId])

  return (
    <div>
      <p role="status" aria-live="polite" className="muted">
        {state === 'connecting' && 'Connecting to the agent run...'}
        {state === 'running' && 'Agents are working. Each step appears below as it completes.'}
        {state === 'done' && 'Run finished.'}
        {state === 'lost' && 'Connection lost. Reconnecting automatically...'}
      </p>
      <ol className="timeline" aria-label="Agent steps">
        {events.map((e) => {
          const { ts, node: _n, ...rest } = e.info
          void _n
          return (
            <li key={e.key} className="done">
              <span className="dot" aria-hidden="true" />
              <div>
                <strong>{e.node.replace(/_/g, ' ')}</strong>
                {ts != null && <span className="muted"> {String(ts)}</span>}
                {Object.keys(rest).length > 0 && <div className="muted small">{Object.entries(rest).map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : String(v)}`).join(' | ')}</div>}
              </div>
            </li>
          )
        })}
        {state !== 'done' && (
          <li className="active">
            <span className="dot pulse" aria-hidden="true" />
            <div className="muted">{state === 'lost' ? 'Waiting for connection' : 'Working on the next step'}...</div>
          </li>
        )}
      </ol>
    </div>
  )
}

export default function Run() {
  const { threadId = '' } = useParams()
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null)
  const [trace, setTrace] = useState<TraceItem[]>([])
  const [kind, setKind] = useState<string>('')
  const [status, setStatus] = useState('')

  async function onDone(s: Record<string, unknown>) {
    setSummary(s)
    try {
      const st = await unwrap(client.GET('/api/threads/{thread_id}', { params: { path: { thread_id: threadId } } }))
      const v = (st.values ?? {}) as ThreadValues
      setTrace(v.trace ?? [])
      setStatus(v.status ?? String(s.status ?? ''))
      setKind((st.pending as { kind?: string } | null | undefined)?.kind ?? '')
    } catch {
      setStatus(String(s.status ?? ''))
    }
  }

  const enc = encodeURIComponent(threadId)
  return (
    <>
      <h1>Agent run</h1>
      <p className="muted">Live progress for <code>{threadId}</code></p>
      <Section title="Progress" id="h-progress">
        <RunTimeline threadId={threadId} onDone={onDone} />
      </Section>
      {summary && (
        <Section title="Result" id="h-result">
          <p>Status: <Badge tone={/reject|fail|error/i.test(status) ? 'bad' : 'good'}>{(status || 'done').replace(/_/g, ' ')}</Badge></p>
          <div className="row">
            {kind === 'proposal_approval' && <Link className="btn primary" to={`/studio/${enc}`}>Open proposal studio</Link>}
            {kind === 'message_approval' && <Link className="btn primary" to="/messages">Review reply</Link>}
            <Link className="btn" to={`/jobs/${enc}`}>Job detail</Link>
            <Link className="btn" to="/pipeline">Pipeline</Link>
          </div>
          {trace.length > 0 && (
            <>
              <h3>Trace</h3>
              <div className="table-wrap">
                <table>
                  <thead><tr><th scope="col">#</th><th scope="col">Node</th><th scope="col">Details</th></tr></thead>
                  <tbody>
                    {trace.map((t, i) => {
                      const { node, ts, ...rest } = t
                      return (
                        <tr key={i}>
                          <td>{i + 1}</td>
                          <th scope="row">{node}</th>
                          <td className="small">{ts != null && <span className="muted">{String(ts)} </span>}{JSON.stringify(rest)}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </Section>
      )}
    </>
  )
}
