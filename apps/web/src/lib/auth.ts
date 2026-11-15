const KEY = 'gigbid.token'
// Fallback when localStorage is blocked: keep the token for this page session.
let memToken: string | null = null

function getStored(): string | null {
  try { return localStorage.getItem(KEY) } catch { return null }
}
export function setToken(t: string) {
  memToken = t
  try { localStorage.setItem(KEY, t) } catch { /* storage unavailable */ }
}
export function clearToken() {
  memToken = null
  try { localStorage.removeItem(KEY) } catch { /* storage unavailable */ }
}
export function currentToken(): string | null {
  return getStored() ?? memToken
}
