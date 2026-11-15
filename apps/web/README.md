# GigBid web

React + Vite + TypeScript frontend for GigBid. Human-in-the-loop: nothing is sent until you approve it.

## Run

```bash
cd apps/web
npm install
npm run dev        # http://localhost:5173, proxies /api to http://localhost:8000
```

Start the FastAPI backend separately (port 8000). Production build: `npm run build`, then `npm run preview` (port 4173, same proxy).

## Typed API client

`openapi.json` is the exported FastAPI schema. Regenerate the types after the API changes:

```bash
npm run gen:api    # openapi-typescript openapi.json -> src/lib/api/schema.d.ts (do not edit by hand)
```

Calls go through `openapi-fetch` in `src/lib/api/client.ts`, which adds `Authorization: Bearer <token>`
(token kept in localStorage) and flips the degraded-mode banner on any 503. Payloads the schema leaves
as plain dicts are typed by hand in `src/lib/types.ts`. Note: `typescript` is pinned to 5.x because
`openapi-typescript` does not work with TypeScript 7.

## Tests

```bash
npx playwright install chromium
npm run build
npx playwright test          # starts vite preview; backend is mocked with page.route
npx playwright show-report   # playwright-report/
```

Specs live in `tests/e2e/` (onboarding, approve, reject with reason, edit draft, degraded banner,
approvals survive refresh). No Python server or paid API is used.

## Screens

`/login` (sign-in + onboarding), `/inbox`, `/jobs/:threadId`, `/studio/:threadId`, `/pipeline`,
`/messages`, `/approvals`, `/runs/:threadId` (live SSE timeline), `/analytics`, `/settings`.
Thread ids contain colons and are URL-encoded in routes.

## Known gaps

- "Skip" in the inbox is local only (no skip endpoint in the API); skipped ids are kept in localStorage.
- `POST /api/portfolio/upload` is not in `openapi.json`, so it uses a plain authenticated `fetch`.
- "Regenerate paragraph" is a disabled placeholder.
