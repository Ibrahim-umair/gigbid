import { expect, test } from '@playwright/test'
import { LETTER, THREAD, mockApi } from './mock'

const studioUrl = `/studio/${encodeURIComponent(THREAD)}`

test('1. onboarding: sign in, set up profile, save settings', async ({ page }) => {
  const m = await mockApi(page, { loggedIn: false, portfolio404: true })
  await page.goto('/login')
  await page.getByLabel('Username').fill('alice')
  await page.getByLabel('Password').fill('secret')
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page.getByRole('heading', { name: 'Set up your copilot' })).toBeVisible()
  await expect(page.getByLabel(/ml_engineer: AI\/ML engineer \(synthetic\)/)).toBeChecked()
  await expect(page.getByLabel(/GigSim/)).toBeChecked()

  await page.getByLabel(/Upwork \(live mode\)/).check()
  await expect(page.getByRole('button', { name: 'Connect Upwork (OAuth)' })).toBeVisible()
  await page.getByLabel(/GigSim/).check()

  // Friendly message when the portfolio endpoint 404s
  await page.getByLabel(/Upload a case study/).setInputFiles({ name: 'case.md', mimeType: 'text/markdown', buffer: Buffer.from('# My case') })
  await page.getByRole('button', { name: 'Upload', exact: true }).click()
  await expect(page.getByText(/not available on this server yet/)).toBeVisible()

  await page.getByLabel('Hourly floor (USD)').fill('50')
  await page.getByLabel('Fixed-price floor (USD)').fill('300')
  await page.getByLabel('Saved search query').fill('python rag')
  await page.getByLabel('Weekly Connects budget').fill('60')
  await page.getByRole('button', { name: 'Save and continue' }).click()

  await expect(page).toHaveURL(/\/inbox$/)
  await expect(page.getByRole('heading', { name: 'Build a RAG chatbot' })).toBeVisible()
  const put = m.calls.find((c) => c.method === 'PUT' && c.path === '/api/settings')!
  expect(put.body).toMatchObject({ hourly_floor: 50, fixed_floor: 300, weekly_connects_budget: 60, marketplace: 'gigsim', saved_searches: [{ query: 'python rag' }] })
})

test('2. approving a proposal shows evidence + dry-run, then sends approve', async ({ page }) => {
  const m = await mockApi(page)
  await page.goto(studioUrl)
  await expect(page.getByRole('heading', { name: 'Proposal studio' })).toBeVisible()

  // Claim evidence on keyboard focus
  const claim = page.locator('.claim', { hasText: 'I build production RAG systems.' })
  await claim.focus()
  await expect(page.getByRole('tooltip')).toContainText('Legal search RAG')
  await expect(page.getByRole('tooltip')).toContainText('540ms')

  // Verification + critic + compliance visible
  await expect(page.getByText('partially_supported')).toBeVisible()
  await expect(page.getByText('Mention the client name in the opening.')).toBeVisible()
  await expect(page.getByText('Compliance: allowed')).toBeVisible()
  // Dry run preview
  const preview = page.getByLabel('Dry-run preview')
  await expect(preview).toContainText('Connects cost 12')
  await expect(preview).toContainText('68')
  await expect(preview).toContainText('"job_id": "job-1"')
  await expect(page.getByTestId('approvals-badge')).toHaveText('1')

  await page.getByRole('button', { name: /Approve & send proposal/ }).click()
  await expect(page).toHaveURL(/\/runs\//)
  await expect(page.getByText('Run finished.')).toBeVisible()
  const post = m.calls.find((c) => c.method === 'POST' && c.path === `/api/approvals/${THREAD}`)!
  expect(post.body).toEqual({ action: 'approve' })
})

test('3. rejecting requires a reason', async ({ page }) => {
  const m = await mockApi(page)
  await page.goto(studioUrl)
  await page.getByRole('button', { name: 'Reject', exact: true }).click()
  const confirm = page.getByRole('button', { name: 'Confirm reject' })
  await expect(confirm).toBeDisabled()
  await page.getByLabel(/Reason for rejecting/).fill('Budget too low for the scope')
  await expect(confirm).toBeEnabled()
  await confirm.click()
  await expect(page).toHaveURL(/\/runs\//)
  const post = m.calls.find((c) => c.method === 'POST' && c.path === `/api/approvals/${THREAD}`)!
  expect(post.body).toEqual({ action: 'reject', reason: 'Budget too low for the scope' })
})

test('4. editing a draft sends action=edit with the new text', async ({ page }) => {
  const m = await mockApi(page)
  await page.goto(studioUrl)
  const approve = page.getByRole('button', { name: /Approve & send proposal/ })
  const saveEdit = page.getByRole('button', { name: /Save edit & approve/ })
  await expect(saveEdit).toBeDisabled()

  await page.getByRole('button', { name: 'Edit text' }).click()
  const edited = LETTER + ' Happy to share a demo.'
  await page.getByLabel('Edit cover letter').fill(edited)
  await expect(approve).toBeDisabled()
  await expect(saveEdit).toBeEnabled()
  await saveEdit.click()

  await expect(page).toHaveURL(/\/runs\//)
  const post = m.calls.find((c) => c.method === 'POST' && c.path === `/api/approvals/${THREAD}`)!
  expect(post.body).toEqual({ action: 'edit', text: edited })
})

test('5. degraded mode: marketplace unavailable banner and 503 error state', async ({ page }) => {
  await mockApi(page, { marketplace: 'unavailable' })
  await page.goto('/inbox')
  const banner = page.getByTestId('degraded-banner')
  await expect(banner).toBeVisible()
  await expect(banner).toContainText('Marketplace unavailable')
  await expect(page.getByRole('alert').filter({ hasText: 'marketplace unavailable' }).first()).toBeVisible()
})

test('6. pending approvals survive a refresh (read from server)', async ({ page }) => {
  await mockApi(page)
  await page.goto('/approvals')
  await expect(page.getByRole('link', { name: 'Review proposal' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('link', { name: 'Review proposal' })).toBeVisible()
  await expect(page.getByTestId('approvals-badge')).toHaveText('1')
})
