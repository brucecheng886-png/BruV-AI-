// @ts-check
/**
 * Setup Wizard Step 6 – Embedding Model 測試
 *
 * 驗證 bge-m3 下載邏輯已改用 Docker Ollama API（而非主機 CLI）：
 *   - checkDockerOllamaModel  (非 listOllamaModels)
 *   - pullDockerOllamaModel   (非 pullOllamaModel)
 */
const { test, expect } = require('@playwright/test')
const path = require('path')

// 直接以 file:// 載入 setup-wizard.html（不需要跑 Docker）
const WIZARD_URL =
  'file:///' +
  path.resolve(__dirname, '../../electron/setup-wizard.html').replace(/\\/g, '/')

// ── 共用 Bridge mock 基底（startServices / waitForBackend 立即成功）──
const BASE_BRIDGE_SCRIPT = `
  window.__testLog = []
  // 舊版 CLI methods：若被呼叫就記錄（供斷言用）
  window.__LEGACY_listOllamaModels_CALLED = false
  window.__LEGACY_pullOllamaModel_CALLED  = false

  window.setupBridge = {
    startServices:     async () => ({ success: true }),
    waitForBackend:    async () => ({ success: true }),
    saveEnvSettings:   async () => ({}),
    initAdmin:         async () => ({ success: true }),
    completeSetup:     async () => {},
    onOllamaProgress:  (cb)   => {},
    // 舊 CLI 方法（應不再被呼叫）
    listOllamaModels:  async () => {
      window.__testLog.push('LEGACY:listOllamaModels')
      window.__LEGACY_listOllamaModels_CALLED = true
      return { success: true, models: ['bge-m3:latest'] }
    },
    pullOllamaModel:   async () => {
      window.__testLog.push('LEGACY:pullOllamaModel')
      window.__LEGACY_pullOllamaModel_CALLED = true
      return { success: true }
    },
    // ★ 新 Docker 方法（預設值，各 case 會 override）
    checkDockerOllamaModel: async (model) => {
      window.__testLog.push('checkDockerOllamaModel:' + model)
      return { success: true, installed: true }
    },
    pullDockerOllamaModel: async (model) => {
      window.__testLog.push('pullDockerOllamaModel:' + model)
      return { success: true }
    }
  }
`

// 切換到 Step 6 並等待 embedding cstep 出現最終狀態
async function runStep6(page, bridgeOverride = '') {
  await page.addInitScript(BASE_BRIDGE_SCRIPT + bridgeOverride)
  await page.goto(WIZARD_URL)
  // showStep 是頁面全域函式
  await page.evaluate(() => window.showStep(6))
}

// ─────────────────────────────────────────────────────────────────────────────

test.describe('Setup Wizard Step 6 – Embedding Model 路由正確性', () => {

  test('Case A：Docker 容器已有 bge-m3 → 跳過下載，顯示「模型已安裝，跳過下載」', async ({ page }) => {
    await runStep6(page, `
      window.setupBridge.checkDockerOllamaModel = async (model) => {
        window.__testLog.push('checkDockerOllamaModel:' + model)
        return { success: true, installed: true }
      }
    `)

    const cstep = page.locator('#cstep-embedding')
    await expect(cstep).toHaveClass(/cstep-done/, { timeout: 15_000 })

    const sub = await page.locator('#cstep-embedding-sub').textContent()
    expect(sub).toBe('模型已安裝，跳過下載')

    const log = await page.evaluate(() => window.__testLog)
    expect(log).toContain('checkDockerOllamaModel:bge-m3:latest')
    // pullDockerOllamaModel 不應被呼叫（已安裝跳過）
    expect(log.some(e => e.startsWith('pullDockerOllamaModel'))).toBe(false)
    // 舊 CLI 方法不應被呼叫
    expect(await page.evaluate(() => window.__LEGACY_listOllamaModels_CALLED)).toBe(false)
    expect(await page.evaluate(() => window.__LEGACY_pullOllamaModel_CALLED)).toBe(false)
  })

  test('Case B：Docker 容器沒有 bge-m3 → 呼叫 pullDockerOllamaModel，成功後顯示「bge-m3 下載完成」', async ({ page }) => {
    await runStep6(page, `
      window.setupBridge.checkDockerOllamaModel = async (model) => {
        window.__testLog.push('checkDockerOllamaModel:' + model)
        return { success: true, installed: false }
      }
      window.setupBridge.pullDockerOllamaModel = async (model) => {
        window.__testLog.push('pullDockerOllamaModel:' + model)
        return { success: true }
      }
    `)

    const cstep = page.locator('#cstep-embedding')
    await expect(cstep).toHaveClass(/cstep-done/, { timeout: 15_000 })

    const sub = await page.locator('#cstep-embedding-sub').textContent()
    expect(sub).toBe('bge-m3 下載完成')

    const log = await page.evaluate(() => window.__testLog)
    expect(log).toContain('checkDockerOllamaModel:bge-m3:latest')
    expect(log).toContain('pullDockerOllamaModel:bge-m3:latest')
    // 舊 CLI 方法不應被呼叫
    expect(await page.evaluate(() => window.__LEGACY_listOllamaModels_CALLED)).toBe(false)
    expect(await page.evaluate(() => window.__LEGACY_pullOllamaModel_CALLED)).toBe(false)
  })

  test('Case C：checkDockerOllamaModel 丟出例外 → fallback 到 pullDockerOllamaModel', async ({ page }) => {
    await runStep6(page, `
      window.setupBridge.checkDockerOllamaModel = async (model) => {
        window.__testLog.push('checkDockerOllamaModel:threw')
        throw new Error('Docker not available')
      }
      window.setupBridge.pullDockerOllamaModel = async (model) => {
        window.__testLog.push('pullDockerOllamaModel:' + model)
        return { success: true }
      }
    `)

    const cstep = page.locator('#cstep-embedding')
    await expect(cstep).toHaveClass(/cstep-done/, { timeout: 15_000 })

    const log = await page.evaluate(() => window.__testLog)
    expect(log).toContain('checkDockerOllamaModel:threw')
    expect(log).toContain('pullDockerOllamaModel:bge-m3:latest')
    // 舊 CLI 方法不應被呼叫
    expect(await page.evaluate(() => window.__LEGACY_listOllamaModels_CALLED)).toBe(false)
    expect(await page.evaluate(() => window.__LEGACY_pullOllamaModel_CALLED)).toBe(false)
  })

  test('Case D：pullDockerOllamaModel 回傳失敗 → 顯示 cstep-error 含「下載失敗」', async ({ page }) => {
    await runStep6(page, `
      window.setupBridge.checkDockerOllamaModel = async (model) => {
        window.__testLog.push('checkDockerOllamaModel:' + model)
        return { success: true, installed: false }
      }
      window.setupBridge.pullDockerOllamaModel = async (model) => {
        window.__testLog.push('pullDockerOllamaModel:failed')
        return { success: false, error: '網路逾時' }
      }
    `)

    const cstep = page.locator('#cstep-embedding')
    await expect(cstep).toHaveClass(/cstep-error/, { timeout: 15_000 })

    const sub = await page.locator('#cstep-embedding-sub').textContent()
    expect(sub).toContain('下載失敗')
    expect(sub).toContain('網路逾時')

    const log = await page.evaluate(() => window.__testLog)
    expect(log).toContain('pullDockerOllamaModel:failed')
    expect(await page.evaluate(() => window.__LEGACY_pullOllamaModel_CALLED)).toBe(false)
  })

})
