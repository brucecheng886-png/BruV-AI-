---
name: debug準則
description: "系統性 debug 方法論。禁止無腦簡化、強制分層診斷、Canary Test 優先。使用時機：遇到任何 bug、畫面不如預期、數值錯誤、元件不渲染、API 回傳異常時。"
argument-hint: "描述 bug 現象，例如：canvas 座標錯位、API 回傳 null、元件不渲染"
---

# Debug 準則 v1.0

> 核心原則：先診斷根因，再動手修改。禁止用簡化或繞過來消滅症狀。

> **與 `debug問題確認` skill 搭配使用**：
> - `debug問題確認` 負責「列清單 → 使用者確認」
> - 本 skill 負責「確認後的診斷與修復」
> - 順序：收到 bug → `debug問題確認` → 使用者確認 → 本 skill 執行修復

---

## 一、強制流程（每次 debug 必須依序執行）

### Step 1 — 重述現象
用一句話說清楚：「觀察到什麼」vs「預期什麼」
禁止在這步驟之前動任何 code。

### Step 2 — 提出分層假說
列出 2-3 個可能問題層次，排列優先順序：

| 層次 | 問題類型 | 驗證方式 |
|------|---------|---------|
| Layer 1：掛載層 | 元素 / 物件是否存在？ | console.log / assert not None |
| Layer 2：數值層 | 座標、尺寸、回傳值正確嗎？ | log 中間值，對照預期範圍 |
| Layer 3：邏輯層 | 計算、轉換、條件判斷正確嗎？ | 單元測試 / 手算對照 |
| Layer 4：時序層 | 非同步、lifecycle、事件順序正確嗎？ | 加時間戳 log |

**不可跳層診斷。**

### Step 3 — 執行 Canary Test
每次 debug 前加一個最簡單的測試，確認「基礎設施本身是否正常」。

| 場景 | Canary Test 範例 |
|------|----------------|
| Canvas 繪圖問題 | 用寫死座標畫一條紅線，確認 canvas 可以畫圖 |
| API 呼叫問題 | curl health endpoint，確認服務存活 |
| DOM 元素問題 | `console.log(document.getElementById('xxx'))`，確認不是 null |
| 資料庫查詢問題 | 執行 SELECT 1，確認連線正常 |

Canary Test 失敗 → 先解底層，不要繼續往上除錯。

### Step 4 — 縮小範圍
根據 Canary Test 結果，確認問題層次後才進行修改。

### Step 5 — 精確修改（最小改動原則）
- 每次只改一件事
- 改動前寫下：「預期這個改動會讓 [具體現象] 變成 [具體結果]」
- 改完驗證，確認有效後再改下一件

### Step 6 — 記錄根因
確認修復後，在 code 旁加一行 comment 說明根因：
```js
// FIX: token 從 localStorage 直取在 Pinia 初始化前可能為空，改用 auth store
const token = useAuthStore().token
```

---

## 二、禁止行為（Anti-Patterns）

| 禁止行為 | 原因 |
|---------|------|
| ❌ 看到 bug 就重寫整個函式 | 無法確認是否真正修到問題，且引入新 bug 風險高 |
| ❌「可能是 X 也可能是 Y，我都改一下」 | 同時改多處無法判斷哪個有效，且可能製造新問題 |
| ❌ 用 hardcode 值繞過計算邏輯 | 治標不治本，換參數後又壞 |
| ❌ 移除 feature 來讓 bug 消失 | 這不是修 bug，是刪功能 |
| ❌ 不解釋原因直接給新 code | 用戶不理解根因，下次遇到相同問題還是不會 |
| ❌ 未確認 DOM 結構就改定位邏輯 | 元素不存在時改定位毫無意義 |
| ❌ 假設 library internal 結構不會變 | Library 升版即壞，`_privateField` 不在合約內 |
| ❌ 跳過 L1/L2 直接猜 L3/L4 | 常因此修錯層，白費時間 |

---

## 三、各類型 Bug 的 Canary Test 模板

### 3.1 前端元件不渲染
```js
// Canary：確認元件掛載
onMounted(() => {
  console.log('[Canary] mounted, ref:', myRef.value)
  console.log('[Canary] data:', JSON.stringify(myData.value))
})
```

### 3.2 API 回傳異常（401 / 500 / null）
```bash
# Canary：直打後端確認服務正常
curl -H "Authorization: Bearer <token>" http://localhost/api/documents/
```
```js
// Canary：確認 token 非空
const auth = useAuthStore()
console.log('[Canary] token:', auth.token ? auth.token.slice(0, 20) + '...' : 'EMPTY')
```

### 3.3 Canvas / 繪圖問題
```js
// Canary：用寫死座標確認 canvas 可繪圖
const ctx = canvas.getContext('2d')
ctx.strokeStyle = 'red'
ctx.beginPath()
ctx.moveTo(10, 10)
ctx.lineTo(100, 100)
ctx.stroke()
console.log('[Canary] canvas size:', canvas.width, 'x', canvas.height, 'DPR:', window.devicePixelRatio)
```

### 3.4 非同步時序問題（Vue lifecycle）
```js
// Canary：加時間戳確認執行順序
console.log('[1] setup', Date.now())
onMounted(() => console.log('[2] mounted', Date.now()))
watch(myRef, (v) => console.log('[3] watch triggered', v, Date.now()))
nextTick(() => console.log('[4] nextTick', Date.now()))
```

### 3.5 資料庫 / 後端服務
```bash
# Canary：確認各服務連線
curl -s http://localhost:6333/health          # Qdrant
curl -s http://localhost:8000/api/health      # FastAPI
redis-cli ping                                # Redis → PONG
docker compose ps                             # 所有容器狀態
```

---

## 四、DPR（devicePixelRatio）意識

任何涉及 canvas 或 DOM 尺寸的計算，預設必須考慮 DPR：

```
CSS px（邏輯像素）≠ buffer px（實體像素）

正確設定方式：
  const dpr = window.devicePixelRatio || 1
  canvas.width = cssWidth * dpr      ← buffer 尺寸
  canvas.height = cssHeight * dpr
  canvas.style.width = cssWidth + 'px'   ← CSS 尺寸
  canvas.style.height = cssHeight + 'px'
  ctx.scale(dpr, dpr)                ← 之後所有座標用 CSS px 為單位
```

驗證 log：
```js
console.log('DPR:', window.devicePixelRatio)
console.log('canvas buffer:', canvas.width, 'x', canvas.height)
console.log('canvas CSS:', canvas.style.width, 'x', canvas.style.height)
```

---

## 五、脆弱依賴標記規範

若發現程式碼依賴 library 的 internal / undocumented API，必須標記：

```js
// ⚠️ 脆弱依賴：依賴 Plotly internal _fullLayout，升版可能失效
// TODO: 改用官方 camera params 重建投影矩陣
const scene = plotlyDiv._fullLayout.scene._scene
```

修 bug 時，同步將脆弱依賴改為官方 API，不得留存。

---

## 六、已知問題庫

### 2026-04-18 試算表 tab 顯示「無效或過期的 Token」
- **現象：** 文件管理頁右側面板切換到「試算表」tab 時，顯示「無效或過期的 Token」錯誤。但文件列表正常載入、Chunks tab 正常顯示。
- **根因：** JWT token 已過期（>24 小時），但 `GET /api/documents/`（列表端點）**完全不需認證**，所以頁面看起來正常；而 `GET /api/documents/{id}/download` 使用 `CurrentUser` **強制認證**，過期 token 觸發 401。前端路由守衛只檢查 `auth.token !== ''`（是否存在），不驗證 token 是否**有效/過期**。加上 `handleResponse` 收到 401 時只 throw Error，沒有清除 token 或導向登入頁，導致使用者停留在一個「半登入」狀態。
- **解法：**
  ```js
  // 1. api/index.js handleResponse — 401 自動登出
  if (resp.status === 401) {
    const auth = useAuthStore()
    auth.logout()
    window.location.href = '/login'
    throw new Error('登入已過期，請重新登入')
  }

  // 2. router/index.js — 路由守衛首次進入時呼叫 /api/auth/me 驗證 token
  router.beforeEach(async (to) => {
    if (to.meta.requiresAuth && !router._tokenVerified) {
      const resp = await fetch('/api/auth/me', { headers: { 'Authorization': `Bearer ${auth.token}` } })
      if (!resp.ok) { auth.logout(); return '/login' }
      router._tokenVerified = true
    }
  })
  ```
- **預防：** 所有需要認證的 API 回應 401 時，前端必須統一攔截並導向登入頁。不可只 throw Error 讓呼叫方自行處理。
- **Canary Test：**
  ```bash
  # 用 PowerShell 模擬過期 token 呼叫 download 端點
  $r = Invoke-WebRequest -Uri "http://localhost/api/documents/$id/download" \
    -Headers @{"Authorization"="Bearer expired.fake.token"} -UseBasicParsing
  # 預期：401 Unauthorized
  ```
- **影響範圍：** 所有使用 `CurrentUser` 依賴注入的後端端點都有相同風險。特別是 `docsApi.download` 有獨立的錯誤處理路徑（不走 `handleResponse`），需要單獨加入 401 攔截。檢查清單：
  - `upload`（有認證）
  - `delete`（有認證）
  - `updateMeta`（有認證）
  - `reanalyze`（有認證）
  - 以上都走 `handleResponse`，已被統一攔截覆蓋
