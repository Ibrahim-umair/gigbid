import { useState } from 'react'
import { Link } from 'react-router-dom'
import { client, errMsg, unwrap } from '../lib/api/client'
import { useAsync } from '../lib/hooks'
import { Empty, ErrorBox, fmtMoney, Loading } from '../components/ui'

const COLS = ['drafted', 'submitted', 'viewed', 'replied', 'interview', 'hired', 'lost'] as const

export default function Pipeline() {
  const { data, error, loading, reload } = useAsync(() => unwrap(client.GET('/api/pipeline')), [])
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string }>()

  async function refresh() {
    setBusy(true)
    setMsg(undefined)
    try {
      await unwrap(client.POST('/api/pipeline/refresh'))
      setMsg({ ok: true, text: 'Pulled the latest marketplace events.' })
      await reload(true)
    } catch (e) {
      setMsg({ ok: false, text: errMsg(e) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <h1>Pipeline</h1>
      <div className="row">
        <button className="btn primary" onClick={refresh} disabled={busy}>
          {busy ? 'Refreshing...' : 'Refresh from marketplace'}
        </button>
        {msg && <span className={msg.ok ? 'ok' : 'error'} role="status">{msg.text}</span>}
      </div>
      {loading && <Loading label="Loading pipeline" />}
      {error && <ErrorBox error={error} retry={() => reload()} />}
      {data && data.length === 0 && <Empty>No proposals yet. Analyse a job from the inbox to start your pipeline.</Empty>}
      {data && data.length > 0 && (
        <div className="kanban">
          {COLS.map((c) => {
            const cards = data.filter((x) => x.column === c)
            return (
              <section key={c} className="col" aria-labelledby={`col-${c}`}>
                <h2 id={`col-${c}`}>
                  {c} <span className="badge-count neutral">{cards.length}</span>
                </h2>
                {cards.length === 0 && <p className="muted">Nothing here.</p>}
                <ul className="plain">
                  {cards.map((k) => (
                    <li key={k.thread_id} className="card mini">
                      <Link to={c === 'drafted' ? `/studio/${encodeURIComponent(k.thread_id)}` : `/jobs/${encodeURIComponent(k.thread_id)}`}>
                        {k.title ?? k.job_id}
                      </Link>
                      <div className="muted">{fmtMoney(k.amount)}</div>
                    </li>
                  ))}
                </ul>
              </section>
            )
          })}
        </div>
      )}
    </>
  )
}
