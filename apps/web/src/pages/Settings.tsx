import { useEffect, useState } from 'react'
import { client, errMsg, unwrap } from '../lib/api/client'
import { useAsync } from '../lib/hooks'
import type { MemoryDump, Settings } from '../lib/types'
import { Empty, ErrorBox, KeyValue, Loading, Section } from '../components/ui'

export default function SettingsPage() {
  const s = useAsync(async () => (await unwrap(client.GET('/api/settings'))) as Settings, [])
  const [form, setForm] = useState<Settings | null>(null)
  const [msg, setMsg] = useState<{ ok: boolean; text: string }>()
  const [busy, setBusy] = useState(false)
  const [tok, setTok] = useState('')
  const [connMsg, setConnMsg] = useState<{ ok: boolean; text: string }>()
  useEffect(() => { if (s.data) setForm(s.data) }, [s.data])

  if (s.loading) return <Loading label="Loading settings" />
  if (s.error) return <ErrorBox error={s.error} retry={() => s.reload()} />
  if (!form) return null
  const searches = form.saved_searches ?? []
  const set = (p: Partial<Settings>) => setForm({ ...form, ...p })

  async function save(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setMsg(undefined)
    try {
      await unwrap(client.PUT('/api/settings', { body: form as Record<string, unknown> }))
      setMsg({ ok: true, text: 'Settings saved.' })
    } catch (x) {
      setMsg({ ok: false, text: errMsg(x) })
    } finally {
      setBusy(false)
    }
  }

  async function connect() {
    setConnMsg(undefined)
    try {
      await unwrap(client.POST('/api/connect/{provider}', { params: { path: { provider: 'upwork' } }, body: { access_token: tok } }))
      setConnMsg({ ok: true, text: 'Upwork connected (live mode).' })
      setTok('')
    } catch (x) {
      setConnMsg({ ok: false, text: errMsg(x) })
    }
  }

  return (
    <>
      <h1>Settings</h1>
      <form className="stack" onSubmit={save}>
        <fieldset className="card">
          <legend>Autonomy</legend>
          <label className="choice">
            <input type="radio" name="autonomy" checked={form.autonomy === 'manual'} onChange={() => set({ autonomy: 'manual' })} />
            Manual: I decide on every job
          </label>
          <label className="choice">
            <input type="radio" name="autonomy" checked={form.autonomy === 'auto_skip_low_fit'} onChange={() => set({ autonomy: 'auto_skip_low_fit' })} />
            Auto-skip low fit: the agent may skip jobs that clearly do not fit
          </label>
          <p className="muted">
            GigBid never auto-sends. Every proposal and message waits for your explicit approval, whichever mode you pick.
          </p>
        </fieldset>

        <fieldset className="card">
          <legend>Budgets and rates</legend>
          <div className="grid2">
            <div className="stack">
              <label htmlFor="s-budget">Weekly Connects budget</label>
              <input id="s-budget" type="number" min={0} value={form.weekly_connects_budget ?? 0} onChange={(e) => set({ weekly_connects_budget: Number(e.target.value) })} />
            </div>
            <div className="stack">
              <label htmlFor="s-hourly">Hourly floor (USD)</label>
              <input id="s-hourly" type="number" min={0} value={form.hourly_floor ?? 0} onChange={(e) => set({ hourly_floor: Number(e.target.value) })} />
            </div>
            <div className="stack">
              <label htmlFor="s-fixed">Fixed-price floor (USD)</label>
              <input id="s-fixed" type="number" min={0} value={form.fixed_floor ?? 0} onChange={(e) => set({ fixed_floor: Number(e.target.value) })} />
            </div>
          </div>
        </fieldset>

        <fieldset className="card">
          <legend>Saved searches</legend>
          {searches.length === 0 && <p className="muted">No saved searches.</p>}
          {searches.map((q, i) => (
            <div key={i} className="row">
              <label htmlFor={`q-${i}`} className="sr-only">Search query {i + 1}</label>
              <input id={`q-${i}`} placeholder="Search query" value={q.query} onChange={(e) => set({ saved_searches: searches.map((x, j) => (j === i ? { ...x, query: e.target.value } : x)) })} />
              <label htmlFor={`h-${i}`}>every</label>
              <input id={`h-${i}`} type="number" min={1} className="narrow" value={q.every_hours ?? 4} onChange={(e) => set({ saved_searches: searches.map((x, j) => (j === i ? { ...x, every_hours: Number(e.target.value) } : x)) })} />
              <span>hours</span>
              <button type="button" className="btn small" onClick={() => set({ saved_searches: searches.filter((_, j) => j !== i) })} aria-label={`Remove search ${i + 1}`}>Remove</button>
            </div>
          ))}
          <button type="button" className="btn small" onClick={() => set({ saved_searches: [...searches, { query: '', every_hours: 4 }] })}>Add search</button>
        </fieldset>

        <div className="row">
          <button className="btn primary" disabled={busy}>{busy ? 'Saving...' : 'Save settings'}</button>
          {msg && <span className={msg.ok ? 'ok' : 'error'} role="status">{msg.text}</span>}
        </div>
      </form>

      <Section title="Connected accounts" id="h-conn">
        <p>Marketplace: <strong>{String(form.marketplace ?? 'gigsim')}</strong> | Persona: <strong>{String(form.persona ?? 'ml_engineer')}</strong></p>
        <div className="stack">
          <label htmlFor="s-tok">Upwork OAuth access token (live mode)</label>
          <input id="s-tok" type="password" value={tok} onChange={(e) => setTok(e.target.value)} />
          <button className="btn" disabled={!tok} onClick={connect}>Connect Upwork (OAuth)</button>
          {connMsg && <p className={connMsg.ok ? 'ok' : 'error'} role="status">{connMsg.text}</p>}
        </div>
      </Section>

      <MemoryViewer />
    </>
  )
}

function MemoryViewer() {
  const m = useAsync(async () => (await unwrap(client.GET('/api/memory'))) as unknown as MemoryDump, [])
  const [err, setErr] = useState('')
  async function forget(ns: string, key: string) {
    setErr('')
    try {
      await unwrap(client.DELETE('/api/memory/{namespace}/{key}', { params: { path: { namespace: ns, key } } }))
      await m.reload(true)
    } catch (e) {
      setErr(errMsg(e))
    }
  }
  const entries = Object.entries(m.data ?? {})
  const total = entries.reduce((n, [, v]) => n + v.length, 0)
  return (
    <Section title="What the agent remembers" id="h-mem">
      <p className="muted">Style preferences and outcomes learned from your decisions. You can delete anything.</p>
      {m.loading && <Loading />}
      {m.error && <ErrorBox error={m.error} retry={() => m.reload()} />}
      {err && <p className="error" role="alert">{err}</p>}
      {m.data && total === 0 && <Empty>Nothing remembered yet. Reject or edit a draft and the agent will learn from it.</Empty>}
      {entries.map(([ns, items]) => items.length > 0 && (
        <div key={ns}>
          <h3>{ns}</h3>
          <ul className="plain">
            {items.map((it) => {
              const { key, ...rest } = it
              return (
                <li key={key} className="card mini">
                  <div className="row between">
                    <code>{key}</code>
                    <button className="btn small danger" onClick={() => forget(ns, key)} aria-label={`Delete memory ${ns} ${key}`}>Delete</button>
                  </div>
                  <KeyValue data={rest} />
                </li>
              )
            })}
          </ul>
        </div>
      ))}
    </Section>
  )
}
