import { defineConfig, devices } from '@playwright/test'

// Browser suites create academic records. Never default to a user's running stack.
const isolatedURL = process.env.E2E_BASE_URL
if (isolatedURL !== 'http://127.0.0.1:18086' || process.env.E2E_DATABASE !== 'rag_today_dev_20261028') {
  throw new Error('E2E requires the explicitly named isolated web/database copy (18086).')
}

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: 'list',
  outputDir: './test-results',
  use: {
    actionTimeout: 7000,
    baseURL: isolatedURL,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'chrome-desktop', use: { ...devices['Desktop Chrome'], channel: process.env.CI ? undefined : 'chrome' } },
    { name: 'edge-desktop', use: { ...devices['Desktop Edge'], channel: 'msedge' } },
    { name: 'chrome-mobile', use: { ...devices['Pixel 5'], channel: 'chrome' } },
  ],
})
