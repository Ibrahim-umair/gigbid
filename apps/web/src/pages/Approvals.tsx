import { Link } from 'react-router-dom'
import { client, unwrap } from '../lib/api/client'
import { useAsync } from '../lib/hooks'
import { Empty, ErrorBox, Loading, Badge } from '../components/ui'

export default function Approvals() {
  const { data, error, loading, reload } = useAsync(() => unwrap(client.GET('/api/approvals')), [])
  return (
    <>
      <h1>Pending approvals</h1>
      <p className="muted">Read from the server, so they survive a refresh. Nothing is sent until you approve.</p>
      {loading && <Loading />}
      {error && <ErrorBox error={error} retry={() => reload()} />}
      {data && data.length === 0 && <Empty>Nothing waiting for you.</Empty>}
      <ul className="cards">
        {(data ?? []).map((a) => {
          const kind = (a.payload as { kind?: string }).kind
          return (
            <li key={a.thread_id} className="card">
              <Badge tone="info">{kind === 'message_approval' ? 'Message reply' : 'Proposal'}</Badge>{' '}
              <span>{a.ref_id}</span>
              <div className="row">
                {kind === 'message_approval' ? (
                  <Link className="btn primary" to="/messages">Review reply</Link>
                ) : (
                  <Link className="btn primary" to={`/studio/${encodeURIComponent(a.thread_id)}`}>Review proposal</Link>
                )}
              </div>
            </li>
          )
        })}
      </ul>
    </>
  )
}
