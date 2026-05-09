// @ts-check
const { test, expect } = require('@playwright/test')

// 整合測試專用帳密（已將 DB 'admin' 帳號更新為合法 email 格式）
const ADMIN_EMAIL = 'admin@local'
const ADMIN_PASSWORD = 'admin123456'

/**
 * 共用：執行登入流程並等待跳轉到 /chat
 * @param {import('@playwright/test').Page} page
 * @param {{ email?: string, password?: string, remember?: boolean }} [opts]
 */
async function doLogin (page, opts = {}) {
  const email = opts.email ?? ADMIN_EMAIL
  const password = opts.password ?? ADMIN_PASSWORD
  await page.goto('/login')
  await page.locator('#login-email').fill(email)
  await page.locator('#login-password').fill(password)
  if (opts.remember) {
    await page.locator('.remember-row input[type="checkbox"]').check()
  }
  await page.locator('button.submit-btn').click()
  await page.waitForURL('**/chat', { timeout: 30_000 })
}

// ─── 測試一：登入 API 整合 ────────────────────────────────────────────
test.describe('整合測試一：登入 API', () => {
  test('1-1 登入頁載入（深色分割版面）', async ({ page }) => {
    await page.goto('/login')
    // 深色 brand-pane 與右側表單同時存在
    await expect(page.locator('.brand-pane')).toBeVisible()
    await expect(page.locator('.form-pane')).toBeVisible()
    await expect(page.locator('#login-email')).toBeVisible()
    await expect(page.locator('#login-password')).toBeVisible()
    await expect(page.locator('button.submit-btn')).toBeVisible()
    // 深色背景驗證
    const bg = await page.locator('.brand-pane').evaluate(el => getComputedStyle(el).backgroundColor)
    expect(bg).toMatch(/rgb\(15, 15, 26\)/) // #0f0f1a
  })

  test('1-2 正確帳密登入跳轉 /chat 並寫入 token', async ({ page }) => {
    await doLogin(page)
    await expect(page).toHaveURL(/\/chat/)
    // sessionStorage 應有 token（未勾選記住我）
    const sToken = await page.evaluate(() => sessionStorage.getItem('token'))
    const lToken = await page.evaluate(() => localStorage.getItem('token'))
    expect(sToken || lToken).toBeTruthy()
  })

  test('1-3 登出後 token 清除並跳回登入頁', async ({ page }) => {
    await doLogin(page)
    await page.locator('.footer-logout').click()
    await page.waitForURL('**/login', { timeout: 10_000 })
    await page.waitForLoadState('domcontentloaded')
    // 等登入頁元素就位後再讀 storage（避免 navigation 造成 context destroyed）
    await expect(page.locator('#login-email')).toBeVisible({ timeout: 10_000 })
    const sToken = await page.evaluate(() => sessionStorage.getItem('token'))
    const lToken = await page.evaluate(() => localStorage.getItem('token'))
    expect(sToken).toBeFalsy()
    expect(lToken).toBeFalsy()
  })
})

// ─── 測試二：記住密碼功能 ─────────────────────────────────────────────
test.describe('整合測試二：記住密碼', () => {
  test('2-1 勾選記住我 → 重新整理仍維持登入', async ({ page, context }) => {
    await doLogin(page, { remember: true })
    // localStorage 應有 token
    const lToken = await page.evaluate(() => localStorage.getItem('token'))
    expect(lToken).toBeTruthy()
    // 重新整理
    await page.reload()
    // 仍應在 /chat（不被導回 /login）
    await page.waitForLoadState('networkidle')
    await expect(page).toHaveURL(/\/chat/)
  })

  test('2-2 不勾選記住我 → 重新整理後（清除 sessionStorage）需重新登入', async ({ page }) => {
    await doLogin(page) // 不勾選
    const sToken = await page.evaluate(() => sessionStorage.getItem('token'))
    expect(sToken).toBeTruthy()
    // 模擬「關閉瀏覽器」：清除 sessionStorage
    await page.evaluate(() => sessionStorage.clear())
    await page.goto('/chat')
    await page.waitForURL('**/login', { timeout: 10_000 })
    await expect(page).toHaveURL(/\/login/)
  })
})

// ─── 測試三：帳號管理 API ─────────────────────────────────────────────
// 此測試會修改 display_name 與密碼，最後將密碼改回原值
test.describe('整合測試三：帳號管理', () => {
  const NEW_PASSWORD = 'NewTestPwd987654'
  const TEST_DISPLAY_NAME = `TestUser-${Date.now()}`

  // 安全閥：無論測試成功或失敗，最後都嘗試還原密碼為 ADMIN_PASSWORD
  test.afterAll(async ({ request }) => {
    for (const candidate of [NEW_PASSWORD, ADMIN_PASSWORD]) {
      const r = await request.post('/api/auth/login', {
        data: { email: ADMIN_EMAIL, password: candidate },
      })
      if (!r.ok()) continue
      const { access_token } = await r.json()
      if (candidate === ADMIN_PASSWORD) return // 已是正確密碼
      await request.post('/api/auth/change-password', {
        headers: { Authorization: `Bearer ${access_token}` },
        data: { current_password: candidate, new_password: ADMIN_PASSWORD },
      })
      return
    }
  })

  test('3-1 設定頁顯示當前 email 並可修改顯示名稱', async ({ page }) => {
    await doLogin(page)
    await page.goto('/settings?group=user')
    // 鎖定「個人資料」card
    const profileCard = page.locator('.el-card', { hasText: '個人資料' })
    await expect(profileCard).toBeVisible({ timeout: 10_000 })
    // email input 在 el-form-item label="帳號" 內，type=text（非 email）
    const emailInput = profileCard.locator('.el-form-item').filter({ hasText: '帳號' }).locator('input').first()
    await expect(emailInput).toHaveValue(ADMIN_EMAIL, { timeout: 10_000 })
    const displayInput = profileCard.locator('input[placeholder="（選填）"]')
    await displayInput.fill(TEST_DISPLAY_NAME)
    await profileCard.locator('button:has-text("儲存個人資料")').click()
    await expect(page.locator('.el-message--success')).toBeVisible({ timeout: 10_000 })
  })

  test('3-2 修改密碼 → 用新密碼重新登入 → 還原密碼', async ({ page }) => {
    await doLogin(page)
    await page.goto('/settings?group=user')
    // 等待頁面載入
    await page.waitForSelector('button:has-text("更新密碼")', { timeout: 10_000 })

    // 填寫修改密碼表單
    const pwdInputs = page.locator('.el-card', { hasText: '修改密碼' }).locator('input[type="password"]')
    await pwdInputs.nth(0).fill(ADMIN_PASSWORD)
    await pwdInputs.nth(1).fill(NEW_PASSWORD)
    await pwdInputs.nth(2).fill(NEW_PASSWORD)
    await page.locator('button:has-text("更新密碼")').click()
    await expect(page.locator('.el-message--success')).toBeVisible({ timeout: 10_000 })

    // 用新密碼重登（不再 goto /login，因為登出已導向 /login）
    await page.locator('.footer-logout').click()
    await page.waitForURL('**/login', { timeout: 10_000 })
    await expect(page.locator('#login-email')).toBeVisible({ timeout: 10_000 })
    await page.locator('#login-email').fill(ADMIN_EMAIL)
    await page.locator('#login-password').fill(NEW_PASSWORD)
    await page.locator('button.submit-btn').click()
    await page.waitForURL('**/chat', { timeout: 30_000 })
    await expect(page).toHaveURL(/\/chat/)

    // 還原密碼避免影響後續測試 / 系統使用
    await page.goto('/settings?group=user')
    await page.waitForSelector('button:has-text("更新密碼")', { timeout: 10_000 })
    const pwdInputs2 = page.locator('.el-card', { hasText: '修改密碼' }).locator('input[type="password"]')
    await pwdInputs2.nth(0).fill(NEW_PASSWORD)
    await pwdInputs2.nth(1).fill(ADMIN_PASSWORD)
    await pwdInputs2.nth(2).fill(ADMIN_PASSWORD)
    await page.locator('button:has-text("更新密碼")').click()
    await expect(page.locator('.el-message--success')).toBeVisible({ timeout: 10_000 })
  })
})

// ─── 測試四：未登入保護 ───────────────────────────────────────────────
test.describe('整合測試四：路由守衛', () => {
  test('4-1 未登入存取 /chat 被導回 /login', async ({ page }) => {
    // 確保無 token
    await page.goto('/login')
    await page.evaluate(() => { localStorage.clear(); sessionStorage.clear() })
    await page.goto('/chat')
    await page.waitForURL('**/login', { timeout: 10_000 })
    await expect(page).toHaveURL(/\/login/)
  })

  test('4-2 未登入存取 /docs 被導回 /login', async ({ page }) => {
    await page.goto('/login')
    await page.evaluate(() => { localStorage.clear(); sessionStorage.clear() })
    await page.goto('/docs')
    await page.waitForURL('**/login', { timeout: 10_000 })
    await expect(page).toHaveURL(/\/login/)
  })
})
