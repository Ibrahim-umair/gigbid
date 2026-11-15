import { client, unwrap } from '../lib/api/client'
import { useAsync } from '../lib/hooks'
import { Empty, ErrorBox, KeyValue, Loading, Section, pct } from '../components/ui'

export default function Analytics() {
  const { data: a, error, loading, reload } = useAsync(() => unwrap(client.GET('/api/analytics')), [])
  if (loading) return <Loading label="Loading analytics" />
  if (error) return <ErrorBox error={error} retry={() => reload()} />
  if (!a) return null
  const cats = Object.entries(a.by_category ?? {}) as [string, { submitted?: number; replied?: number; hired?: number }][]
  const replied = cats.reduce((n, [, c]) => n + (c.replied ?? 0), 0)
  const hired = cats.reduce((n, [, c]) => n + (c.hired ?? 0), 0)
  const reasons = (a.top_rejection_reasons ?? []) as unknown as [string, number][]

  return (
    <>
      <h1>Analytics</h1>
      <ul className="tiles">
        <li><span className="tile-n">{a.proposals}</span> proposals drafted</li>
        <li><span className="tile-n">{a.submitted}</span> submitted</li>
        <li><span className="tile-n">{pct(a.reply_rate)}</span> reply rate</li>
        <li><span className="tile-n">{pct(a.hire_rate)}</span> hire rate</li>
        <li><span className="tile-n">{a.cost_per_proposal_usd != null ? `$${a.cost_per_proposal_usd}` : '-'}</span> LLM cost per proposal</li>
      </ul>

      <Section title="Reply and hire rate by category" id="h-cat">
        {cats.length === 0 ? <Empty>No submitted proposals yet, so there are no outcomes to compare.</Empty> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th scope="col">Category</th><th scope="col">Submitted</th><th scope="col">Reply rate</th><th scope="col">Hire rate</th></tr></thead>
              <tbody>
                {cats.map(([name, c]) => {
                  const s = c.submitted || 0
                  const rr = s ? (c.replied ?? 0) / s : 0
                  const hr = s ? (c.hired ?? 0) / s : 0
                  return (
                    <tr key={name}>
                      <th scope="row">{name}</th>
                      <td>{s}</td>
                      <td><span className="bar" style={{ width: `${rr * 100}%` }} /> {pct(rr)}</td>
                      <td><span className="bar alt" style={{ width: `${hr * 100}%` }} /> {pct(hr)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section title="Connects spent vs outcomes" id="h-conn">
        <p>
          <strong>{a.connects_spent}</strong> Connects spent, producing <strong>{replied}</strong> replies and <strong>{hired}</strong> hires
          {a.connects_spent > 0 && <> ({(a.connects_spent / Math.max(hired, 1)).toFixed(1)} Connects per hire).</>}
        </p>
      </Section>

      <Section title="Top rejection reasons" id="h-rej">
        {reasons.length === 0 ? <Empty>No rejections recorded.</Empty> : (
          <ol>{reasons.map(([r, n]) => <li key={r}>{r} <span className="muted">({n})</span></li>)}</ol>
        )}
      </Section>

      <Section title="LLM ledger" id="h-ledger">
        <KeyValue data={a.llm_ledger} />
        {a.latency_note && <p className="muted">{a.latency_note}</p>}
      </Section>
    </>
  )
}
