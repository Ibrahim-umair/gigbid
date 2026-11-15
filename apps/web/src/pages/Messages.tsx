import { useState } from 'react'
import { Link } from 'react-router-dom'
import { client, errMsg, unwrap } from '../lib/api/client'
import { useAsync, useInterval } from '../lib/hooks'
import type { MessagePending, MsgThread } from '../lib/types'
import ApprovalPanel, { decisionBody, type Decision } from '../components/ApprovalPanel'
import { APPROVALS_CHANGED } from '../components/Layout'
import { Badge, Empty, ErrorBox, Loading } from '../components/ui'

const fmt = (s: string) => {
  const d = new Date(s)
  return isNaN(d.getTime()) ? s : d.toLocaleString()
}

export default function Messages() {
  const threads = useAsync(async () => (await unwrap(client.GET('/api/messages'))) as unknown as MsgThread[], [])
  const approvals = useAsync(() => unwrap(client.GET('/api/approvals')), [])
  const [drafting, setDrafting] = useState<Record<string, string>>({}) // marketplace thread -> run thread
  const [err, setErr] = useState('')

  // While a draft is being written, poll the server for the pending approval.
  useInterval(() => void approvals.reload(true), Object.keys(drafting).length ? 2000 : null)

  const pend = (approvals.data ?? []).filter((a) => (a.payload as { kind?: string }).kind === 'message_approval')
  const pendBy = (tid: string) => pend.find((p) => (p.payload as unknown as MessagePending).thread_id === tid)

  async function draft(tid: string) {
    setErr('')
    try {
      const r = await unwrap(client.POST('/api/messages/{thread_id}/draft', { params: { path: { thread_id: tid } } }))
      setDrafting((d) => ({ ...d, [tid]: r.thread_id }))
    } catch (e) {
      setErr(errMsg(e))
    }
  }

  return (
    <>
      <h1>Messages</h1>
      <p className="muted">The agent drafts replies and proposes interview slots. You approve every message before it is sent.</p>
      {err && <p className="error" role="alert">{err}</p>}
      {threads.loading && <Loading label="Loading conversations" />}
      {threads.error && <ErrorBox error={threads.error} retry={() => threads.reload()} />}
      {threads.data?.length === 0 && <Empty>No conversations yet.</Empty>}
      <ul className="cards">
        {(threads.data ?? []).map((t) => {
          const p = pendBy(t.thread_id)
          const runId = drafting[t.thread_id] ?? t.run?.thread_id
          return (
            <li key={t.thread_id} className="card">
              <h2>Client {t.client_id ?? t.thread_id}</h2>
              <ol className="chat" aria-label="Conversation">
                {t.messages.map((m, i) => (
                  <li key={i} className={m.from === 'client' ? 'them' : 'me'}>
                    <span className="muted">{m.from}{m.ts ? `, ${fmt(m.ts)}` : ''}</span>
                    <p>{m.text}</p>
                  </li>
                ))}
              </ol>
              {p ? (
                <ReplyApproval approval={p.payload as unknown as MessagePending} runThread={p.thread_id} onDone={() => { setDrafting((d) => { const n = { ...d }; delete n[t.thread_id]; return n }); void approvals.reload(true); void threads.reload(true) }} />
              ) : (
                <div className="row">
                  <button className="btn primary" disabled={t.thread_id in drafting} onClick={() => draft(t.thread_id)}>
                    {t.thread_id in drafting ? 'Drafting reply...' : 'Draft reply'}
                  </button>
                  {runId && <Link className="btn" to={`/runs/${encodeURIComponent(runId)}`}>View agent run</Link>}
                  {t.run && !(t.thread_id in drafting) && <Badge>{t.run.status.replace(/_/g, ' ')}</Badge>}
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </>
  )
}

function ReplyApproval({ approval, runThread, onDone }: { approval: MessagePending; runThread: string; onDone: () => void }) {
  const [text, setText] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const current = text ?? approval.reply
  const dirty = current !== approval.reply

  async function decide(d: Decision) {
    setBusy(true)
    setErr('')
    const body = decisionBody(d, current)
    try {
      await unwrap(client.POST('/api/approvals/{thread_id}', { params: { path: { thread_id: runThread } }, body }))
      window.dispatchEvent(new Event(APPROVALS_CHANGED))
      onDone()
    } catch (e) {
      setErr(errMsg(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack">
      <h3>Suggested reply {approval.intent && <Badge tone="info">{approval.intent}</Badge>}</h3>
      <label htmlFor={`reply-${runThread}`}>Reply text (editable)</label>
      <textarea id={`reply-${runThread}`} rows={6} value={current} onChange={(e) => setText(e.target.value)} />
      {approval.slots?.length > 0 && (
        <div>
          <h3>Proposed interview slots</h3>
          <ul>{approval.slots.map((s, i) => <li key={i}>{fmt(s.start)} to {fmt(s.end)}</li>)}</ul>
        </div>
      )}
      {approval.compliance && (
        <p>
          <Badge tone={approval.compliance.allowed ? 'good' : 'bad'}>Compliance: {approval.compliance.allowed ? 'allowed' : 'blocked'}</Badge>
          {approval.compliance.violations?.map((v, i) => <span key={i} className="warn-text"> {v}</span>)}
        </p>
      )}
      <ApprovalPanel
        noun="reply"
        dirty={dirty}
        busy={busy}
        error={err}
        blockedReason={approval.compliance && !approval.compliance.allowed ? 'Compliance blocked this reply. Edit it or reject.' : undefined}
        onDecide={decide}
      />
    </div>
  )
}
