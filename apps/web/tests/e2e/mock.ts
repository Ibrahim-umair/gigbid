import type { Page, Route } from '@playwright/test'

export const THREAD = 'alice:bid:job-1'
export const LETTER =
  'Hi Dana, I build production RAG systems. I cut retrieval latency by 40% for a legal-search client. I can start this week.'

export const evidence = {
  'ev-1': { id: 'ev-1', type: 'case_study', title: 'Legal search RAG', snippet: 'Reduced p95 retrieval latency from 900ms to 540ms.', score: 0.9, source: 'portfolio' },
  'ev-2': { id: 'ev-2', type: 'case_study', title: 'Churn model', snippet: 'Gradient boosting churn model, AUC 0.87.', score: 0.7, source: 'portfolio' },
}

export const proposalPending = {
  kind: 'proposal_approval',
  thread_id: THREAD,
  draft: { cover_letter: LETTER, claims: [], screening_answers: [] },
  evidence,
  claims: [
    { text: 'I build production RAG systems.', evidence_ids: ['ev-1'] },
    { text: 'I cut retrieval latency by 40% for a legal-search client.', evidence_ids: ['ev-1'] },
  ],
  verification: {
    checks: [
      { claim: 'I build production RAG systems.', verdict: 'supported', evidence_ids: ['ev-1'] },
      { claim: 'I cut retrieval latency by 40% for a legal-search client.', verdict: 'partially_supported', evidence_ids: ['ev-1'], fix: 'Say 40% p95 latency, as in the case study.' },
    ],
  },
  risk: { score: 0.1, is_scam: false, flags: [] },
  price: { type: 'fixed', amount: 900, connects_cost: 12, rationale: 'Mid-range for scope.' },
  critiques: [{ approve: false, personalisation: 3, grounding: 4, issues: ['Mention the client name in the opening.'], send_back: false }],
  compliance: { allowed: true, violations: [] },
  dry_run_preview: { connects_cost: 12, balance_before: 80, balance_after: 68, payload: { job_id: 'job-1', cover_letter: LETTER, amount: 900 } },
}

const threadState = (pending: unknown) => ({
  thread_id: THREAD,
  next: ['approval'],
  pending,
  values: {
    job: { title: 'Build a RAG chatbot', description: 'We need a RAG chatbot.', budget: 1000 },
    job_spec: { requirements: ['RAG', 'Python'], deliverables: ['Chatbot'], screening_questions: ['Experience?'], hidden_needs: ['Latency'] },
    risk: { score: 0.1, client_quality: 0.8, is_scam: false, flags: [], injection_detected: false, explanation: 'Verified payment.' },
    fit: { score: 0.82, matches: [{ requirement: 'RAG', evidence_ids: ['ev-1'], strength: 'strong' }, { requirement: 'Python', evidence_ids: ['ev-2'], strength: 'partial' }], missing: [], reasons: 'Strong RAG match.' },
    evidence,
    decision: { action: 'bid', reasons: ['High fit', 'Low risk'] },
    price: proposalPending.price,
    draft: proposalPending.draft,
    status: 'awaiting_approval',
    trace: [{ node: 'scout', ts: 1 }],
  },
})

export interface Mock {
  calls: { method: string; path: string; body: any }[]
  health: { marketplace: string }
  pending: unknown
}

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

/** Install a fake backend. No Python server or paid API is involved. */
export async function mockApi(page: Page, opts: { loggedIn?: boolean; marketplace?: string; portfolio404?: boolean } = {}) {
  const m: Mock = { calls: [], health: { marketplace: opts.marketplace ?? 'ok' }, pending: proposalPending }
  if (opts.loggedIn !== false) {
    await page.addInitScript(() => localStorage.setItem('gigbid.token', 'test-token'))
  }
  await page.route('**/api/**', async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const path = decodeURIComponent(url.pathname)
    const method = req.method()
    let body: any = null
    try { body = req.postDataJSON() } catch { body = req.postData() }
    m.calls.push({ method, path, body })

    if (path === '/api/auth/login') return json(route, { token: 'test-token', user: 'alice' })
    if (path === '/api/health') return json(route, { api: 'ok', marketplace: m.health.marketplace, queued_jobs: 0 })
    if (path === '/api/jobs') {
      if (m.health.marketplace === 'unavailable') return json(route, { detail: 'marketplace unavailable' }, 503)
      return json(route, [
        { job_id: 'job-1', title: 'Build a RAG chatbot', category: 'ai', budget: 1000, is_hourly: false, connects_cost: 12, thread_id: THREAD, status: 'awaiting_approval', action: 'bid', fit: 0.82, risk_score: 0.1, risk_flags: [], price: proposalPending.price },
        { job_id: 'job-2', title: 'Quick scam gig', category: 'other', budget: 50, connects_cost: 8, thread_id: null, status: null, action: null, fit: null, risk_score: null, risk_flags: [], price: null },
      ])
    }
    if (path === '/api/approvals' && method === 'GET') {
      return json(route, m.pending ? [{ thread_id: THREAD, kind: 'bid', ref_id: 'job-1', payload: m.pending }] : [])
    }
    if (path === `/api/approvals/${THREAD}`) {
      m.pending = null
      return json(route, { thread_id: THREAD })
    }
    if (path === `/api/threads/${THREAD}`) return json(route, threadState(m.pending))
    if (path === `/api/runs/${THREAD}/stream`) {
      return route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: 'event: node\ndata: {"node":"scout","info":{"node":"scout","ts":1}}\n\nevent: node\ndata: {"node":"send","info":{"node":"send","ts":2}}\n\nevent: done\ndata: {"status":"submitted"}\n\n',
      })
    }
    if (path === '/api/settings') return json(route, { persona: 'ml_engineer', autonomy: 'manual', weekly_connects_budget: 80, hourly_floor: 35, fixed_floor: 150, saved_searches: [], marketplace: 'gigsim' })
    if (path === '/api/portfolio/upload') return opts.portfolio404 ? json(route, { detail: 'Not Found' }, 404) : json(route, { id: 'up-1', title: 'My case', items_indexed: 9 })
    return json(route, { detail: `unmocked ${method} ${path}` }, 404)
  })
  return m
}
