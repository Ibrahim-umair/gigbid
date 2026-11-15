import { useState, type ReactNode } from 'react'

export type Decision = { action: 'approve' } | { action: 'edit' } | { action: 'reject'; reason: string }

export function decisionBody(d: Decision, text: string): { action: 'approve' | 'edit' | 'reject'; text?: string; reason?: string } {
  if (d.action === 'approve') return { action: 'approve' }
  if (d.action === 'edit') return { action: 'edit', text }
  return { action: 'reject', reason: d.reason }
}

/** Human-in-the-loop controls. Nothing is sent until one of these buttons is pressed. */
export default function ApprovalPanel({
  dirty,
  blockedReason,
  busy,
  error,
  preview,
  onDecide,
  noun = 'proposal',
}: {
  dirty: boolean
  blockedReason?: string
  busy: boolean
  error?: string
  preview?: ReactNode
  onDecide: (d: Decision) => void
  noun?: string
}) {
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const blocked = !!blockedReason || busy
  return (
    <section className="card approval" aria-labelledby="approval-h">
      <h2 id="approval-h">Your decision</h2>
      <p className="muted">
        Nothing is sent to the client until you approve. Review the evidence, the critic and the compliance verdict first.
      </p>
      {preview}
      {blockedReason && (
        <p className="error" role="alert">
          {blockedReason}
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="row">
        <button className="btn primary" disabled={blocked || dirty} onClick={() => onDecide({ action: 'approve' })}>
          Approve &amp; send {noun}
        </button>
        <button className="btn" disabled={blocked || !dirty} onClick={() => onDecide({ action: 'edit' })}>
          Save edit &amp; approve
        </button>
        <button className="btn danger" disabled={busy} aria-expanded={rejecting} onClick={() => setRejecting((r) => !r)}>
          Reject
        </button>
        <button className="btn" disabled title="coming soon" aria-label="Regenerate paragraph (coming soon)">
          Regenerate paragraph
        </button>
      </div>
      {dirty && <p className="muted">You edited the text, so use &quot;Save edit &amp; approve&quot; to send your version.</p>}
      {rejecting && (
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault()
            if (reason.trim()) onDecide({ action: 'reject', reason: reason.trim() })
          }}
        >
          <label htmlFor="reject-reason">Reason for rejecting (required, used to improve future drafts)</label>
          <textarea
            id="reject-reason"
            required
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <button className="btn danger" type="submit" disabled={busy || !reason.trim()}>
            Confirm reject
          </button>
        </form>
      )}
    </section>
  )
}
