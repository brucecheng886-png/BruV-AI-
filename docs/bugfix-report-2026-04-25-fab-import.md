# Bug 報告：AgentPanel FAB 不顯示

**日期：** 2026-04-25
**嚴重程度：** 高（耗時 40+ 分鐘）
**影響範圍：** AgentPanel 元件整體崩潰，FAB 浮動圖示完全不渲染

---

## 問題描述

AgentPanel 的 FAB 浮動圖示在所有非 `/chat`、`/` 的頁面均不顯示，包括文件管理、知識庫等頁面。

---

## 根本原因

在 Step 3 修改 AgentPanel.vue 時，`const chatStore = useChatStore()` 被插入在兩個 `import` 陳述句之間：

```js
import { useChatStore } from '../stores/chat.js'
const chatStore = useChatStore()   // ← 可執行語句夾在 import 之間
import { Monitor, Globe, ... }     // ← ESM 規範不允許這樣
```

JavaScript ESM 規範要求所有 `import` 必須在任何可執行語句之前。這個順序錯誤導致 Vue SFC 編譯器產生異常的 setup 函式，整個 `setup()` 在執行期崩潰，FAB 從未被渲染到 DOM。

---

## 為什麼難以發現

1. **Vite build 沒有報錯** — 編譯器靜默接受，輸出 `built in Xs` 無任何警告
2. **Checked 工具顯示 no problems found** — 靜態分析未捕捉到此問題
3. **症狀誤導方向** — FAB 不顯示容易讓人往 CSS、z-index、位置計算等方向排查
4. **除錯過程走錯方向** — 依序檢查了 v-if 條件、fabPos 初始值、z-index 衝突、localStorage 快取、modelValue 預設值，耗費大量時間才找到真正原因

---

## 修正方式

將所有 `import` 陳述句集中在檔案頂部，`const chatStore = useChatStore()` 移到最後一個 `import` 之後：

```js
// 正確順序
import { useChatStore } from '../stores/chat.js'
import { Monitor, Globe, ... } from 'lucide-vue-next'
// ... 其他所有 import

// import 結束後才可執行語句
const chatStore = useChatStore()
```

---

## 預防措施

1. **每次新增 import 時，確認插入位置在所有現有 import 的上方或下方，不要插入中間**
2. **Copilot 做多段替換時，若涉及 script setup 頂部區塊，必須完整讀取並驗證 import 順序**
3. **症狀為「元件完全不渲染」時，優先檢查 script setup 是否有語法或順序問題，再查 template 條件**
4. **下次遇到元件整體不顯示，第一步應該是讀取元件 script 頂部 1-30 行確認 import 順序**

---

## 時間損失與排查時間軸

總耗時約 40 分鐘，排查順序如下：

| 順序 | 排查方向 | 結果 |
|------|---------|------|
| 1 | v-if vs v-show 條件邏輯 | 無效，條件本身正確 |
| 2 | isHiddenPage computed 定義 | 無效，邏輯正確 |
| 3 | modelValue 預設值 | 無效，預設 false 正確 |
| 4 | App.vue showAgentPanel watch 邏輯 | 無效，不影響 FAB |
| 5 | fabPos 初始值 (0,0) 位置問題 | 無效，onMounted 後會更新 |
| 6 | z-index 衝突 | 無效，無其他高 z-index 元素 |
| 7 | localStorage 快取（建議 Ctrl+Shift+R） | 無效 |
| 8 | console.log 除錯 + 重新部署 | 才發現 setup() 根本沒執行 |
| 9 | 讀取 script setup 頂部 | 發現 import 順序錯誤，問題解決 |

---

## 錯誤發生的源頭（Copilot 操作）

**發生在 Pinia store 架構整合的 Step 3**，Copilot 對 AgentPanel.vue 做多段替換時，將以下內容插入 script setup 頂部：

```js
import { useChatStore } from '../stores/chat.js'
const chatStore = useChatStore()   // ← 錯誤：可執行語句插在 import 中間
import { Monitor, Globe, ... }
```

原因是 Copilot 在做「替換前 N 行」時，只讀取了局部區塊，沒有完整確認整個 script setup 頂部的 import 順序，直接插入導致違反 ESM 規範。

---

## Claude 應改進的規範

**問題：Claude 在整個排查過程中，沒有優先建議讀取元件 script 頂部確認 import 順序。**

改進規則：

1. **症狀為「元件整體不渲染、功能完全消失」時，第一個調查指令必須是讀取該元件 script setup 前 30 行**，確認 import 順序，再查其他方向。

2. **每次給 Copilot 涉及 script setup 頂部的修改指令後，Claude 應主動要求 Copilot 回報修改後的前 20 行內容**，作為驗證步驟。

3. **多段替換任務完成後，Claude 應在給出「完成確認」前，要求 Copilot 搜尋確認沒有 import 語句出現在可執行語句之後。**

4. **排查問題時，Claude 應優先從「元件是否正確載入」往外推，而不是從「template 條件是否正確」往內查。**

---

## 預防措施

1. **每次新增 import 時，確認插入位置在所有現有 import 的上方或下方，不要插入中間**
2. **Copilot 做多段替換時，若涉及 script setup 頂部區塊，必須完整讀取並驗證 import 順序**
3. **症狀為「元件完全不渲染」時，優先檢查 script setup 是否有語法或順序問題，再查 template 條件**
4. **下次遇到元件整體不顯示，第一步應該是讀取元件 script 頂部 1-30 行確認 import 順序**
5. **Copilot 每次完成 script setup 修改後，必須回報修改後的前 20 行給 Claude 確認**

