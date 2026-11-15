import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { authFetch, client, errMsg, unwrap } from '../lib/api/client'
import { currentToken, setToken } from '../lib/auth'

export default function Login() {
  const nav = useNavigate()
  const [step, setStep] = useState<'login' | 'onboarding'>('login')
  const [user, setUser] = useState('')
  const [pw, setPw] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  if (step === 'login' && currentToken()) return <Navigate to="/inbox" replace />

  async function login(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setErr('')
    try {
      const r = await unwrap(client.POST('/api/auth/login', { body: { username: user, password: pw } }))
      setToken(r.token)
      setStep('onboarding')
    } catch (x) {
      setErr(errMsg(x))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="auth-wrap">
      <h1>GigBid</h1>
      <p className="muted">Your freelancer copilot. Agents analyse jobs and draft proposals; you approve everything.</p>
      {step === 'login' ? (
        <form className="card stack" onSubmit={login} aria-labelledby="signin-h">
          <h2 id="signin-h">Sign in</h2>
          <label htmlFor="username">Username</label>
          <input id="username" autoComplete="username" required value={user} onChange={(e) => setUser(e.target.value)} />
          <label htmlFor="password">Password</label>
          <input id="password" type="password" autoComplete="current-password" required value={pw} onChange={(e) => setPw(e.target.value)} />
          {err && <p className="error" role="alert">{err}</p>}
          <button className="btn primary" disabled={busy}>{busy ? 'Signing in...' : 'Sign in'}</button>
        </form>
      ) : (
        <Onboarding onDone={() => nav('/inbox')} />
      )}
    </main>
  )
}

function Onboarding({ onDone }: { onDone: () => void }) {
  const [persona, setPersona] = useState('ml_engineer')
  const [market, setMarket] = useState<'gigsim' | 'upwork'>('gigsim')
  const [upToken, setUpToken] = useState('')
  const [upMsg, setUpMsg] = useState<{ ok: boolean; text: string }>()
  const [file, setFile] = useState<File | null>(null)
  const [upload, setUpload] = useState<{ ok: boolean; text: string }>()
  const [hourly, setHourly] = useState(35)
  const [fixed, setFixed] = useState(150)
  const [query, setQuery] = useState('')
  const [budget, setBudget] = useState(80)
  const [saveErr, setSaveErr] = useState('')
  const [busy, setBusy] = useState(false)

  async function connectUpwork() {
    setUpMsg(undefined)
    try {
      await unwrap(client.POST('/api/connect/{provider}', { params: { path: { provider: 'upwork' } }, body: { access_token: upToken } }))
      setUpMsg({ ok: true, text: 'Upwork connected (live mode). Your token is stored encrypted.' })
    } catch (x) {
      setUpMsg({ ok: false, text: errMsg(x) })
    }
  }

  async function doUpload() {
    if (!file) return
    setUpload(undefined)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await authFetch('/api/portfolio/upload', { method: 'POST', body: fd })
      if (res.status === 404) {
        setUpload({ ok: false, text: 'Portfolio upload is not available on this server yet. You can still use the built-in synthetic persona.' })
      } else if (res.status === 415) {
        setUpload({ ok: false, text: 'Please upload a Markdown (.md) or text (.txt) case study.' })
      } else if (!res.ok) {
        setUpload({ ok: false, text: `Upload failed (${res.status}).` })
      } else {
        const j = await res.json().catch(() => ({}))
        setUpload({ ok: true, text: `Uploaded${j.title ? `: ${j.title}` : ''}. ${j.items_indexed ?? ''} portfolio items indexed.` })
      }
    } catch {
      setUpload({ ok: false, text: 'Could not reach the server to upload.' })
    }
  }

  async function save(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setSaveErr('')
    try {
      await unwrap(
        client.PUT('/api/settings', {
          body: {
            persona: persona === 'own' ? 'own' : 'ml_engineer',
            marketplace: market === 'upwork' ? 'upwork_live' : 'gigsim',
            hourly_floor: hourly,
            fixed_floor: fixed,
            weekly_connects_budget: budget,
            saved_searches: [{ query, every_hours: 4 }],
          },
        }),
      )
      onDone()
    } catch (x) {
      setSaveErr(errMsg(x))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="stack" onSubmit={save} aria-labelledby="onb-h">
      <h2 id="onb-h">Set up your copilot</h2>

      <fieldset className="card">
        <legend>1. Profile</legend>
        <label className="choice">
          <input type="radio" name="persona" checked={persona === 'ml_engineer'} onChange={() => setPersona('ml_engineer')} />
          ml_engineer: AI/ML engineer (synthetic)
        </label>
        <label className="choice">
          <input type="radio" name="persona" checked={persona === 'own'} onChange={() => setPersona('own')} />
          Use my own profile (upload your case studies below)
        </label>
      </fieldset>

      <fieldset className="card">
        <legend>2. Marketplace</legend>
        <label className="choice">
          <input type="radio" name="market" checked={market === 'gigsim'} onChange={() => setMarket('gigsim')} />
          GigSim (simulated marketplace, safe default)
        </label>
        <label className="choice">
          <input type="radio" name="market" checked={market === 'upwork'} onChange={() => setMarket('upwork')} />
          Upwork (live mode)
        </label>
        {market === 'upwork' && (
          <div className="stack">
            <label htmlFor="up-token">Upwork OAuth access token</label>
            <input id="up-token" type="password" value={upToken} onChange={(e) => setUpToken(e.target.value)} />
            <button type="button" className="btn" disabled={!upToken} onClick={connectUpwork}>
              Connect Upwork (OAuth)
            </button>
            {upMsg && <p className={upMsg.ok ? 'ok' : 'error'} role="status">{upMsg.text}</p>}
          </div>
        )}
      </fieldset>

      <fieldset className="card">
        <legend>3. Portfolio</legend>
        <label htmlFor="portfolio">Upload a case study (.md or .txt)</label>
        <input id="portfolio" type="file" accept=".md,.txt,text/markdown,text/plain" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <button type="button" className="btn" disabled={!file} onClick={doUpload}>Upload</button>
        {upload && <p className={upload.ok ? 'ok' : 'error'} role="status">{upload.text}</p>}
      </fieldset>

      <fieldset className="card">
        <legend>4. Rates, filters and budget</legend>
        <div className="grid2">
          <div className="stack">
            <label htmlFor="hourly">Hourly floor (USD)</label>
            <input id="hourly" type="number" min={0} value={hourly} onChange={(e) => setHourly(Number(e.target.value))} />
          </div>
          <div className="stack">
            <label htmlFor="fixed">Fixed-price floor (USD)</label>
            <input id="fixed" type="number" min={0} value={fixed} onChange={(e) => setFixed(Number(e.target.value))} />
          </div>
          <div className="stack">
            <label htmlFor="query">Saved search query</label>
            <input id="query" placeholder="e.g. python machine learning" value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
          <div className="stack">
            <label htmlFor="budget">Weekly Connects budget</label>
            <input id="budget" type="number" min={0} value={budget} onChange={(e) => setBudget(Number(e.target.value))} />
          </div>
        </div>
      </fieldset>

      {saveErr && <p className="error" role="alert">{saveErr}</p>}
      <div className="row">
        <button className="btn primary" disabled={busy}>{busy ? 'Saving...' : 'Save and continue'}</button>
        <button type="button" className="btn" onClick={onDone}>Skip for now</button>
      </div>
    </form>
  )
}
