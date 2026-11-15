import createClient, { type Middleware } from 'openapi-fetch'
import type { paths } from './schema'
import { clearToken, currentToken } from '../auth'
import { setDegraded } from '../status'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

const middleware: Middleware = {
  onRequest({ request }) {
    const t = currentToken()
    if (t) request.headers.set('Authorization', `Bearer ${t}`)
    return request
  },
  onResponse({ response, request }) {
    if (response.status === 503) setDegraded(true)
    if (response.status === 401 && !request.url.includes('/api/auth/login')) {
      clearToken()
      if (!location.pathname.startsWith('/login')) location.assign('/login')
    }
    return response
  },
}

export const client = createClient<paths>({ baseUrl: '' })
client.use(middleware)

function detailOf(error: unknown, fallback: string): string {
  const d = (error as { detail?: unknown } | undefined)?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d)) {
    return d.map((x) => (x as { msg?: string }).msg).filter(Boolean).join('; ') || fallback
  }
  return fallback
}

/** Unwrap an openapi-fetch result, throwing ApiError for non-2xx. */
export async function unwrap<T>(
  p: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  let r
  try {
    r = await p
  } catch {
    throw new ApiError(0, 'Network error: cannot reach the GigBid API')
  }
  if (r.error !== undefined || !r.response.ok) {
    throw new ApiError(r.response.status, detailOf(r.error, `Request failed (${r.response.status})`))
  }
  return r.data as T
}

/** Raw fetch with auth, for endpoints missing from the OpenAPI schema (portfolio upload). */
export async function authFetch(url: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers)
  const t = currentToken()
  if (t) headers.set('Authorization', `Bearer ${t}`)
  const res = await fetch(url, { ...init, headers })
  if (res.status === 503) setDegraded(true)
  return res
}

export const errMsg = (e: unknown) => (e instanceof Error ? e.message : String(e))
