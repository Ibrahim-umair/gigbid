import { useCallback, useEffect, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { client, unwrap } from '../lib/api/client'
import { clearToken } from '../lib/auth'
import { useInterval } from '../lib/hooks'
import { setDegraded, useDegraded } from '../lib/status'

const links = [
  ['/inbox', 'Inbox'],
  ['/pipeline', 'Pipeline'],
  ['/messages', 'Messages'],
  ['/approvals', 'Approvals'],
  ['/analytics', 'Analytics'],
  ['/settings', 'Settings'],
] as const

export const APPROVALS_CHANGED = 'gigbid:approvals-changed'

export default function Layout() {
  const nav = useNavigate()
  const degraded = useDegraded()
  const [pending, setPending] = useState<number | null>(null)
  const [open, setOpen] = useState(false)

  const checkHealth = useCallback(async () => {
    try {
      const h = await unwrap(client.GET('/api/health'))
      setDegraded(h.marketplace === 'unavailable')
    } catch {
      setDegraded(true)
    }
  }, [])
  const loadApprovals = useCallback(async () => {
    try {
      const a = await unwrap(client.GET('/api/approvals'))
      setPending(a.length)
    } catch { /* badge simply stays stale */ }
  }, [])

  useEffect(() => {
    void checkHealth()
    void loadApprovals()
    window.addEventListener(APPROVALS_CHANGED, loadApprovals)
    return () => window.removeEventListener(APPROVALS_CHANGED, loadApprovals)
  }, [checkHealth, loadApprovals])
  useInterval(checkHealth, 15000)
  useInterval(loadApprovals, 20000)

  return (
    <>
      <a className="skip" href="#main">Skip to content</a>
      <header className="topbar">
        <span className="brand">GigBid</span>
        <button
          className="btn menu-btn"
          aria-expanded={open}
          aria-controls="mainnav"
          onClick={() => setOpen((o) => !o)}
        >
          Menu
        </button>
        <nav id="mainnav" aria-label="Main" className={open ? 'open' : ''}>
          {links.map(([to, label]) => (
            <NavLink key={to} to={to} onClick={() => setOpen(false)}>
              {label}
              {to === '/approvals' && pending ? (
                <span className="badge-count" data-testid="approvals-badge" aria-label={`${pending} pending approvals`}>
                  {pending}
                </span>
              ) : null}
            </NavLink>
          ))}
          <button
            className="btn linklike"
            onClick={() => {
              clearToken()
              nav('/login')
            }}
          >
            Sign out
          </button>
        </nav>
      </header>
      {degraded && (
        <div className="banner" role="alert" data-testid="degraded-banner">
          <strong>Marketplace unavailable.</strong> GigBid is in degraded mode: new analyses are queued
          and will resume automatically when the marketplace recovers. Your drafts and pending approvals
          are safe.
        </div>
      )}
      <main id="main" tabIndex={-1}>
        <Outlet />
      </main>
    </>
  )
}
