import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { client, errMsg, unwrap } from '../lib/api/client'
import { useAsync } from '../lib/hooks'
import type { Check, Claim, Evidence, ProposalPending, ThreadValues } from '../lib/types'
import ApprovalPanel, { decisionBody, type Decision } from '../components/ApprovalPanel'
import EvidenceHover from '../components/EvidenceHover'
import { APPROVALS_CHANGED } from '../components/Layout'
import { Badge, ErrorBox, Loading, Section } from '../components/ui'

type Seg = { text: string; claim?: Claim; verdict?: string }

function segment(text: string, claims: Claim[], checks: Check[]): Seg[] {
  const hits: { start: number; end: number; claim: Claim; verdict?: string }[] = []
  for (const c of claims) {
    const t = c.text.trim()
    if (!t) continue
    const start = text.indexOf(t)
    if (start < 0) continue
    const end = start + t.length
    if (hits.some((h) => start < h.end && end > h.start)) continue
    hits.push({ start, end, claim: c, verdict: checks.find((k) => k.claim.trim() === t)?.verdict })
  }
  hits.sort((a, b) => a.start - b.start)
  const out: Seg[] = []
  let pos = 0
  for (const h of hits) {
    if (h.start > pos) out.push({ text: text.slice(pos, h.start) })
    out.push({ text: text.slice(h.start, h.end), claim: h.claim, verdict: h.verdict })
    pos = h.end
  }
  if (pos < text.length) out.push({ text: text.slice(pos) })
  return out
}

const weak = (v?: string) => !!v && !/^(supported|ok|pass|verified)$/i.test(v)

export default function Studio() {
  const { threadId = '' } = useParams()
  const nav = useNavigate()
  const { data, error, loading, reload } = useAsync(
    () => unwrap(client.GET('/api/threads/{thread_id}', { params: { path: { thread_id: threadId } } })),
    [threadId],
  )
  const [text, setText] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const v = (data?.values ?? {}) as ThreadValues
  const pending = (data?.pending as ProposalPending | null | undefined)?.kind === 'proposal_approval'
    ? (data!.pending as unknown as ProposalPending)
    : null
  const original = pending?.draft.cover_letter ?? v.draft?.cover_letter ?? ''
  const current = text ?? original
  const dirty = pending != null && current !== original
  const claims = pending?.claims ?? pending?.draft.claims ?? v.draft?.claims ?? []
  const checks = pending?.verification?.checks ?? v.verification?.checks ?? []
  const evidence: Record<string, Evidence> = pending?.evidence ?? v.evidence ?? {}
  const critiques = pending?.critiques ?? v.critiques ?? []
  const compliance = pending?.compliance ?? v.compliance
  const risk = pending?.risk ?? v.risk
  const price = pending?.price ?? v.price
  const segs = useMemo(() => segment(current, claims, checks), [current, claims, checks])
  const orphaned = claims.length - segs.filter((s) => s.claim).length

  if (loading) return <Loading label="Loading proposal" />
  if (error) return <ErrorBox error={error} retry={() => reload()} />

  async function decide(d: Decision) {
    setBusy(true)
    setErr('')
    const body = decisionBody(d, current)
    try {
      const r = await unwrap(client.POST('/api/approvals/{thread_id}', { params: { path: { thread_id: threadId } }, body }))
      window.dispatchEvent(new Event(APPROVALS_CHANGED))
      nav(`/runs/${encodeURIComponent(r.thread_id)}`)
    } catch (e) {
      setErr(errMsg(e))
      setBusy(false)
    }
  }

  const dry = pending?.dry_run_preview
  const blocked = compliance && !compliance.allowed ? 'Compliance blocked this proposal. Edit the draft to resolve the violations below, or reject it.' : undefined

  return (
    <>
      <h1>Proposal studio</h1>
      <p className="muted">
        {v.job?.title} <Link to={`/jobs/${encodeURIComponent(threadId)}`}>View job analysis</Link>
      </p>
      {!pending && (
        <p className="empty" role="status">
          {v.draft ? `No approval is pending for this proposal (status: ${v.status ?? 'unknown'}). It is shown read-only.` : 'No draft exists for this job yet.'}
        </p>
      )}

      <div className="studio">
        <div className="stack">
          <Section title="Cover letter" id="h-letter">
            <p className="muted">
              Highlighted sentences are factual claims. Hover or focus one to see the portfolio evidence behind it.
            </p>
            {!editing ? (
              <div className="letter prewrap" data-testid="letter">
                {segs.map((s, i) =>
                  s.claim ? (
                    <EvidenceHover key={i} evidence={evidence} ids={s.claim.evidence_ids} className={`claim ${weak(s.verdict) ? 'weak' : ''} ${s.claim.evidence_ids.length === 0 ? 'noev' : ''}`}>
                      {s.text}
                    </EvidenceHover>
                  ) : (
                    <span key={i}>{s.text}</span>
                  ),
                )}
              </div>
            ) : (
              <>
                <label htmlFor="letter-text">Edit cover letter</label>
                <textarea id="letter-text" rows={14} value={current} onChange={(e) => setText(e.target.value)} />
              </>
            )}
            {orphaned > 0 && dirty && <p className="warn-text">{orphaned} claim(s) no longer match the text and are not highlighted.</p>}
            {pending && (
              <div className="row">
                <button className="btn" onClick={() => setEditing((e) => !e)}>{editing ? 'Preview with evidence' : 'Edit text'}</button>
                {dirty && <button className="btn" onClick={() => setText(null)}>Discard edits</button>}
              </div>
            )}
          </Section>

          <Section title="Claim verification" id="h-verify">
            {checks.length === 0 ? <p className="muted">No verification results.</p> : (
              <ul className="plain">
                {checks.map((c, i) => (
                  <li key={i} className={weak(c.verdict) ? 'check weak' : 'check'}>
                    <Badge tone={weak(c.verdict) ? 'bad' : 'good'}>{c.verdict}</Badge> {c.claim}
                    {c.fix && <div className="muted">Suggested fix: {c.fix}</div>}
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title="Critic and compliance" id="h-critic">
            <div className="row">
              <Badge tone={compliance?.allowed === false ? 'bad' : 'good'}>
                Compliance: {compliance ? (compliance.allowed ? 'allowed' : 'blocked') : 'unknown'}
              </Badge>
              {risk?.is_scam && <Badge tone="bad">Scam risk</Badge>}
            </div>
            {!!compliance?.violations?.length && (
              <ul>{compliance.violations.map((x, i) => <li key={i} className="warn-text">{x}</li>)}</ul>
            )}
            {critiques.length === 0 && <p className="muted">No critic feedback.</p>}
            {critiques.map((c, i) => (
              <div key={i} className="critique">
                <strong>Critic round {i + 1}</strong>{' '}
                <Badge tone={c.approve ? 'good' : 'warn'}>{c.approve ? 'approved' : 'changes suggested'}</Badge>
                {c.personalisation != null && <span className="muted"> personalisation {c.personalisation}</span>}
                {c.grounding != null && <span className="muted"> grounding {c.grounding}</span>}
                {!!c.issues?.length && <ul>{c.issues.map((x, j) => <li key={j}>{x}</li>)}</ul>}
              </div>
            ))}
          </Section>
        </div>

        <div className="stack">
          {price && (
            <Section title="Price" id="h-price">
              <p>
                <strong>{price.amount != null ? `$${price.amount}` : '-'}</strong> {price.type && `(${price.type})`}; Connects {price.connects_cost ?? '-'}
              </p>
              {price.rationale && <p className="muted">{price.rationale}</p>}
            </Section>
          )}
          {pending && (
            <ApprovalPanel
              dirty={dirty}
              busy={busy}
              error={err}
              blockedReason={blocked}
              onDecide={decide}
              preview={
                dry && (
                  <div className="preview" aria-label="Dry-run preview">
                    <h3>Dry-run preview</h3>
                    <p>
                      Connects cost <strong>{dry.connects_cost ?? '-'}</strong>; balance {dry.balance_before ?? '-'} then{' '}
                      <strong>{dry.balance_after ?? '-'}</strong> after sending.
                    </p>
                    <p className="muted">Exact payload that will be submitted:</p>
                    <pre tabIndex={0}>{JSON.stringify(dry.payload, null, 2)}</pre>
                  </div>
                )
              }
            />
          )}
        </div>
      </div>
    </>
  )
}
