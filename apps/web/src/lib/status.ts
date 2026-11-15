import { useSyncExternalStore } from 'react'

let degraded = false
const subs = new Set<() => void>()
export function setDegraded(v: boolean) {
  if (v !== degraded) {
    degraded = v
    subs.forEach((f) => f())
  }
}
export function useDegraded() {
  return useSyncExternalStore(
    (f) => {
      subs.add(f)
      return () => { subs.delete(f) }
    },
    () => degraded,
  )
}
