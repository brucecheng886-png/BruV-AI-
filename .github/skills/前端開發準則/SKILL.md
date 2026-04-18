---
name: 前端開發準則
description: "Vue 3 Composition API + Element Plus 開發規範。包含元件結構、狀態管理、命名規範、樣式規則、效能注意事項。使用時機：新增任何 Vue 元件前、PR 自檢前、樣式出現問題時。"
---

# 前端開發準則 v1.1（Vue 3 + Element Plus）

> 本專案使用**純 JavaScript**（非 TypeScript）、**Element Plus** UI 框架（非 Tailwind CSS）、原生 `fetch`（非 axios）。

---

## 一、元件結構規範

### 標準 SFC 結構順序（嚴格遵守）
```vue
<script setup>
// 1. import（外部套件 → 內部模組）
//    注意：import 路徑需帶副檔名 → '../stores/auth.js'
// 2. props / emits 定義
// 3. composables / stores
// 4. refs / reactive state
// 5. computed
// 6. methods（普通函式 + async 函式）
// 7. lifecycle hooks（onMounted 最後）
</script>

<template>
  <!-- 根元素只能有一個 -->
</template>

<style scoped>
/* 主要樣式寫在這裡 */
/* 覆蓋 Element Plus 元件樣式時使用 :deep() */
</style>
```

### 元件命名規則
- 檔名：PascalCase（`ChatMessage.vue`、`KnowledgeGraphPanel.vue`）
- 在 template 中使用：PascalCase（`<ChatMessage />`）
- 禁止單字元件名（`<Card>` → `<KnowledgeCard>`）

---

## 二、Props / Emits 規範

```javascript
// ✅ 正確：Runtime 宣告 + type + default
const props = defineProps({
  nodeId: { type: String, required: true },
  label: { type: String, required: true },
  isActive: { type: Boolean, default: false },
  size: { type: String, default: 'md', validator: v => ['sm', 'md', 'lg'].includes(v) }
})

// ✅ 正確：陣列式 emits 宣告
const emit = defineEmits(['nodeClick', 'labelChange'])

// ❌ 禁止：無宣告直接 $emit
// ❌ 禁止：TypeScript 泛型寫法（專案不用 TS）
```

---

## 三、狀態管理規範（Pinia）

```javascript
// store 命名：use[Feature]Store
// 檔名：stores/[feature].js
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useChatStore = defineStore('chat', () => {
  // state
  const messages = ref([])
  const isLoading = ref(false)

  // getters（computed）
  const messageCount = computed(() => messages.value.length)

  // actions
  async function sendMessage(content) {
    isLoading.value = true
    try {
      // ...
    } finally {
      isLoading.value = false  // 必須在 finally 重設 loading
    }
  }

  return { messages, isLoading, messageCount, sendMessage }
})
```

**規則：**
- 跨元件共享的狀態 → Pinia store
- 單一元件內部狀態 → `ref` / `reactive`
- 禁止在 store 中直接操作 DOM
- Store 統一使用 Composition API setup 函式風格（非 Options 風格）
- `localStorage` 同步：需要持久化的值在 store 初始化時從 `localStorage` 讀取，變更時同步寫入

---

## 四、Element Plus 使用規範

### 4.1 全域註冊
```javascript
// main.js — 已全域註冊，元件中不需再 import
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
```

### 4.2 常用元件對照
| 場景 | 使用 Element Plus 元件 |
|------|----------------------|
| 表單 | `el-form` + `el-form-item` + `el-input` |
| 表格 | `el-table` + `el-table-column` |
| 按鈕 | `el-button`（含 `type`、`size`、`icon` 屬性）|
| 上傳 | `el-upload`（`:http-request` 自定義上傳邏輯）|
| 對話框 | `el-dialog` |
| 訊息提示 | `ElMessage.success()` / `ElMessage.error()` |
| 分頁 | `el-tabs` + `el-tab-pane` |
| 下拉選單 | `el-dropdown` + `el-dropdown-menu` |

### 4.3 表單驗證
```javascript
const rules = {
  email: [
    { required: true, message: '請輸入信箱', trigger: 'blur' },
    { type: 'email', message: '信箱格式不正確', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '請輸入密碼', trigger: 'blur' },
    { min: 8, message: '密碼至少 8 字元', trigger: 'blur' }
  ]
}
```

### 4.4 圖標使用
```vue
<!-- 已全域註冊，直接使用元件名 -->
<el-icon><Search /></el-icon>
<el-button :icon="Delete">刪除</el-button>
```

---

## 五、CSS 樣式規範

### 5.1 樣式分層
- **Element Plus 元件**：優先使用其內建屬性（`type`、`size`、`plain`）控制外觀
- **佈局與自訂樣式**：寫在 `<style scoped>` 中
- **少量行內樣式**：僅用於真正動態的值（如 `style="height: ${h}px"`）

### 5.2 覆蓋 Element Plus 預設樣式
```css
/* ✅ 正確：使用 :deep() 穿透 scoped */
:deep(.el-table__header th) {
  background-color: #f5f7fa;
}

/* ❌ 禁止：移除 scoped 來覆蓋全域樣式 */
```

### 5.3 色彩規範
- 優先使用 Element Plus CSS 變數（`var(--el-color-primary)` 等）
- 自訂色碼應定義為 CSS 變數，集中管理：
```css
:root {
  --sidebar-bg: #f1f5f9;
  --sidebar-border: #e2e8f0;
}
```
- 禁止在多個元件中重複硬編碼相同色碼

---

## 六、API 呼叫規範

### 6.1 統一使用原生 `fetch`
```javascript
// api/index.js 已定義統一的 getHeaders() 和 handleResponse()
// 元件中直接呼叫 api 物件的方法

import { docsApi } from '../api/index.js'

// ✅ 在元件中呼叫
const docs = await docsApi.list(kbId)

// ❌ 禁止：在元件中直接寫 fetch
// ❌ 禁止：繞過 api 層直接拼 URL
```

### 6.2 認證 Token
- Token 統一從 Pinia `useAuthStore().token` 取得
- `api/index.js` 的 `getHeaders()` 已自動注入 `Authorization: Bearer` header
- **禁止**在元件中直接 `localStorage.getItem('token')`

### 6.3 SSE 串流
```javascript
// SSE 使用 fetch + ReadableStream，不用 EventSource
const response = await chatStream(query, conversationId, model)
const reader = response.body.getReader()
const decoder = new TextDecoder()
// 逐 chunk 讀取 + 解析 SSE data
```

---

## 七、非同步與 Loading 狀態規範

```javascript
// 每個非同步操作必須有三個狀態
const data = ref(null)
const isLoading = ref(false)
const error = ref(null)

async function fetchData() {
  isLoading.value = true
  error.value = null
  try {
    data.value = await api.getData()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '發生未知錯誤'
    console.error('[fetchData] failed:', e)
  } finally {
    isLoading.value = false
  }
}
```

---

## 八、建置注意事項

- **Node 版本**：必須使用 `node:20-alpine`，Node 24 會導致 rollup 崩潰
- **建置指令**：`docker run --rm -v "...frontend:/app" -w /app node:20-alpine sh -c "npm install --quiet && npm run build"`
- **SheetJS**：透過靜態檔 `/xlsx.full.min.js` 載入至 `window.XLSX`，不走 npm import（避免 Node 24 相容性問題）
- **部署**：`docker cp dist → nginx 容器 → nginx -s reload`

---

## 九、前端自檢清單（PR 前必須逐項確認）

- [ ] 所有 props 有 `type` 和 `default`（或 `required: true`）
- [ ] 非同步操作有 loading / error 狀態
- [ ] `onUnmounted` 中清除：event listener、timer、WebSocket 連線
- [ ] 沒有直接操作 DOM（應透過 ref 或 Vue directive）
- [ ] Token 取用走 `useAuthStore().token`，不直接讀 `localStorage`
- [ ] 沒有 `console.log` 留在 production code（debug log 加前綴後統一清除）
- [ ] 新增色碼使用 CSS 變數或 Element Plus 變數，非硬編碼
- [ ] 元件超過 300 行 → 考慮拆分
- [ ] import 路徑帶副檔名（`.js`）
