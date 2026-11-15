import { Link, useParams } from 'react-router-dom'
import { client, unwrap } from '../lib/api/client'
import { useAsync } from '../lib/hooks'
import type { Evidence, ThreadValues } from '../lib/types'
import EvidenceHover from '../components/EvidenceHover'
import { ActionBadge, Badge, ErrorBox, fmtMoney, List, Loading, Section, StrengthBadge, pct } from '../components/ui'

export default function JobDetail() {
  const { threadId = '' } = useParams()
  const { data, error, loading, reload } = useAsync(
    () => unwrap(client.GET('/api/threads/{thread_id}', { params: { path: { thread_id: threadId } } })),
    [threadId],
  )
  if (loading) return <Loading label="Loading job analysis" />
  if (error) return <ErrorBox error={error} retry={() => reload()} />
  const v = (data?.values ?? {}) as ThreadValues
  const ev: Record<string, Evidence> = v.evidence ?? {}
  const pending = data?.pending as { kind?: string } | null | undefined
  const spec = v.job_spec
  const risk = v.risk
  const fit = v.fit
  const price = v.price
  const reasons = fit?.reasons == null ? [] : Array.isArray(fit.reasons) ? fit.reasons : [fit.reasons]

  return (
    <>
      <div className="job-head">
        <h1>{v.job?.title ?? 'Job'}</h1>
        <ActionBadge action={v.decision?.action} />
      </div>
      <div className="row">
        <Badge>Status: {(v.status ?? 'unknown').replace(/_/g, ' ')}</Badge>
        {fit?.score != null && <Badge>Fit {pct(fit.score)}</Badge>}
        {pending?.kind === 'proposal_approval' && (
          <Link className="btn primary" to={`/studio/${encodeURIComponent(threadId)}`}>Review proposal</Link>
        )}
        <Link className="btn" to={`/runs/${encodeURIComponent(threadId)}`}>View agent run</Link>
      </div>

      <Section title="Decision" id="h-decision">
        <p>
          Recommended action: <strong>{v.decision?.action ?? 'pending'}</strong>
        </p>
        <List items={v.decision?.reasons} />
      </Section>

      <Section title="Job description" id="h-desc">
        <p className="prewrap">{v.job?.description ?? 'No description.'}</p>
        {v.job?.budget != null && <p className="muted">Budget: {fmtMoney(v.job.budget)}</p>}
      </Section>

      <Section title="What the client needs (JobSpec)" id="h-spec">
        <div className="grid2">
          <div><h3>Requirements</h3><List items={spec?.requirements} /></div>
          <div><h3>Deliverables</h3><List items={spec?.deliverables} /></div>
          <div><h3>Screening questions</h3><List items={spec?.screening_questions} /></div>
          <div><h3>Hidden needs</h3><List items={spec?.hidden_needs} /></div>
        </div>
      </Section>

      <Section title="Risk report" id="h-risk">
        {!risk ? <p className="muted">Not assessed yet.</p> : (
          <>
            <div className="row">
              <Badge tone={risk.is_scam ? 'bad' : 'good'}>{risk.is_scam ? 'Likely scam' : 'No scam signal'}</Badge>
              {risk.score != null && <Badge tone={risk.score >= 0.5 ? 'bad' : 'neutral'}>Risk score {pct(risk.score)}</Badge>}
              {risk.client_quality != null && <Badge>Client quality {String(risk.client_quality)}</Badge>}
              {risk.injection_detected && <Badge tone="bad">Prompt injection detected and neutralised</Badge>}
              {(risk.flags ?? []).map((f) => <Badge key={f} tone="warn">{f}</Badge>)}
            </div>
            {risk.explanation && <p>{risk.explanation}</p>}
          </>
        )}
      </Section>

      <Section title="Requirement to evidence" id="h-matrix">
        {!fit?.matches?.length ? <p className="muted">No requirement matches yet.</p> : (
          <div className="table-wrap">
            <table>
              <caption className="sr-only">Each requirement with the portfolio evidence that proves it</caption>
              <thead><tr><th scope="col">Requirement</th><th scope="col">Strength</th><th scope="col">Evidence</th></tr></thead>
              <tbody>
                {fit.matches.map((m, i) => (
                  <tr key={i}>
                    <th scope="row">{m.requirement}</th>
                    <td><StrengthBadge s={m.strength} /></td>
                    <td>
                      {m.evidence_ids.length === 0 ? <span className="muted">No evidence</span> : (
                        <ul className="chips">
                          {m.evidence_ids.map((id) => (
                            <li key={id}>
                              <EvidenceHover evidence={ev} ids={[id]} className="chip">{ev[id]?.title ?? id}</EvidenceHover>
                            </li>
                          ))}
                        </ul>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {!!fit?.missing?.length && (<><h3>Not covered by your portfolio</h3><List items={fit.missing} /></>)}
        {reasons.length > 0 && (<><h3>Fit reasoning</h3><List items={reasons} /></>)}
      </Section>

      <Section title="Price and Connects" id="h-price">
        {!price ? <p className="muted">No price suggestion yet.</p> : (
          <>
            <p>
              <strong>{fmtMoney(price.amount)}</strong> {price.type && `(${price.type})`}. Connects cost: {price.connects_cost ?? '-'}.{' '}
              {price.connects_worth_it != null && (
                <Badge tone={price.connects_worth_it ? 'good' : 'warn'}>{price.connects_worth_it ? 'Connects worth it' : 'Connects probably not worth it'}</Badge>
              )}
            </p>
            {price.rationale && <p>{price.rationale}</p>}
          </>
        )}
      </Section>
    </>
  )
}
