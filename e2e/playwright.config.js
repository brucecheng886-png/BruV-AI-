// @ts-check
const { defineConfig, devices } = require('@playwright/test')

module.exports = defineConfig({
  testDir: './tests',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: 0,
  workers: 1,

  reporter: [
    ['list'],
    ['html', { outputFolder: '../playwright-report', open: 'never' }],
  ],

  use: {
    baseURL: 'http://localhost',
    headless: true,
    screenshot: 'only-on-failure',
    video: 'off',
    trace: 'off',
    locale: 'zh-TW',
    timezoneId: 'Asia/Taipei',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  outputDir: '../test-results',
})
