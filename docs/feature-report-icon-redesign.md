# Feature Report — 全局圖示系統重設計（Lucide Icons）

**日期**：2026-04-23  
**執行者**：GitHub Copilot  
**狀態**：✅ Build 通過，已部署

---

## 1. 功能摘要

將全站圖示從 **Element Plus icons-vue（字串 icon name）+ emoji** 全面替換為 **Lucide Icons 極簡線條風格**，同時將模型供應商卡片從 emoji 改為官方 logo 圖片，提升整體視覺一致性與辨識度。

---

## 2. 完成功能清單

| 項目 | 說明 | 狀態 |
|------|------|------|
| 安裝 `lucide-vue-next` | `^1.0.0`，寫入 `frontend/package.json` | ✅ |
| NavBar.vue 導航圖示替換 | 6 個導航項目全數改用 lucide component 物件 | ✅ |
| ChatView.vue 功能按鈕圖示替換 | 發送 / 停止 / Plus / 快速提示 / hover 操作列等 | ✅ |
| DocsView.vue 功能按鈕圖示替換 | 上傳 / 匯入 / 切換檢視 / 批次操作 / Panel 等 25+ 處 | ✅ |
| AgentPanel.vue 圖示替換 | Tab 圖示 / 關閉 / 發送 / 停止 / Empty 狀態 | ✅ |
| SettingsView.vue 模型供應商官方 logo | 卡片改用 `<img>` 載入官方圖片，失敗顯示首字母 | ✅ |

---

## 3. 各元件替換對照表

### 3.1 NavBar.vue

| 導航項目 | 舊（Element Plus） | 新（Lucide） |
|----------|-------------------|-------------|
| 對話 | `el-icon` 字串 icon | `MessageSquare` |
| 文件管理 | 同上 | `FolderOpen` |
| 知識圖譜 | 同上 | `Network` |
| 插件管理 | 同上 | `Puzzle` |
| 蛋白質圖譜 | 同上 | `Dna` |
| 設定 / Wiki | 同上 | `Settings` |

---

### 3.2 ChatView.vue

| 位置 | 舊圖示 | 新圖示 |
|------|--------|--------|
| 發送按鈕（圓形） | el-button 文字 | `ArrowUp` |
| 停止串流（圓形） | el-button 文字 | `Square` |
| 附件 + 號 | el-icon Plus | `Plus` |
| 複製訊息 | DocumentCopy | `Copy` |
| 重試訊息 | RefreshRight | `RotateCcw` |
| 捲到底部 FAB | 文字箭頭 | `ChevronDown` |
| 對話模式 radio | emoji | `MessageCircle` |
| Agent 模式 radio | emoji | `Bot` |
| 模型選取 ✓ | el-icon Check | `Check` |
| 快速提示：程式碼 | emoji | `Code` |
| 快速提示：解釋概念 | emoji | `BookOpen` |
| 快速提示：文字創作 | emoji | `PenLine` |
| 快速提示：搜尋知識庫 | emoji | `Search` |
| 快速提示：資料分析 | emoji | `BarChart2` |

---

### 3.3 DocsView.vue

| 位置 | 舊圖示 | 新圖示 |
|------|--------|--------|
| KB 側欄 + 圓形鈕 | `:icon="Plus"` | `Plus` component |
| 新建知識庫按鈕 | `:icon="Plus"` | `Plus` |
| KB 項目 `···` | `MoreFilled` | `MoreHorizontal` |
| 標籤 `···` | `MoreFilled` | `MoreHorizontal` |
| 「管理」按鈕 | 文字 | `Settings2` |
| 「完成」按鈕 | 文字 | `Check` |
| 「新增標籤」按鈕 | `+` 文字 | `Tag` |
| 搜尋框 prefix | `el-icon Search` | `Search` |
| 批次刪除 | 文字 | `Trash2` |
| 取消選取 | 文字 | `X` |
| 全部選取 | 文字 | `CheckSquare` |
| 取消全選 | 文字 | `X` |
| 上傳文件 | `:icon="Upload"` | `Upload` |
| 匯入連結 | `:icon="Files"` | `Link` |
| Grid 切換 | `'Grid'` 字串 | `LayoutGrid` |
| Table 切換 | `'List'` 字串 | `List` |
| Node 切換 | `'Share'` 字串 | `Share2` |
| 清除搜尋 | `:icon="Close"` | `X` |
| 文件縮圖（pdf/docx/txt/md） | `Memo` / `Document` | `FileText` |
| 文件縮圖（xlsx/csv） | `Files` | `FileSpreadsheet` |
| 文件縮圖（html） | `Memo` | `Globe` |
| 文件卡片 `···` | `:icon="MoreFilled"` | `MoreHorizontal` |
| Tag picker ✓ | `el-icon Check` | `Check` |
| Panel 關閉 | `:icon="Close"` | `X` |
| Panel 移動到 KB | 文字 | `FolderInput` |
| Panel 刪除文件 | `:icon="Delete"` | `Trash2` |
| 重新 AI 分析 | 🔄 emoji | `RefreshCw` |
| Table 詳情 | `:icon="View"` | `Eye` |
| Table 刪除 | `:icon="Delete"` | `Trash2` |
| Loading spinner（5 處） | `el-icon Loading` | `Loader2` + CSS 動畫 |

---

### 3.4 AgentPanel.vue

| 位置 | 舊圖示 | 新圖示 |
|------|--------|--------|
| 頁面 Tab | `🖥️` emoji | `Monitor` |
| 全域 Tab | `🌐` emoji | `Globe` |
| 知識庫 Tab | `📚` emoji | `BookOpen` |
| 標題列關閉 | `×` 字元 | `X` |
| Empty 狀態圖示 | emoji | `Monitor` / `Globe` / `BookOpen` |
| 發送按鈕 | 文字「發送」 | `ArrowUp`（橘色圓形，與 ChatView 一致） |
| 停止按鈕 | `■ 停止` 文字 | `Square`（紅邊框淡紅底圓形） |

---

### 3.5 SettingsView.vue 模型供應商 logo

| 供應商 | 舊（emoji） | 新（官方 logo） |
|--------|------------|----------------|
| 全部（`Layers` icon） | 🗂 emoji | Lucide `Layers` `:size="36"` |
| Ollama | 🏠 | `https://ollama.com/public/ollama.png` |
| OpenAI | 🤖 | `https://upload.wikimedia.org/wikipedia/commons/0/04/ChatGPT_logo.svg` |
| Groq | ⚡ | `https://groq.com/wp-content/uploads/2024/03/groq-logo.png` |
| Gemini | 💎 | `https://www.gstatic.com/lamda/images/gemini_sparkle_v002_d4735304ff6292a690345.svg` |
| OpenRouter | 🌐 | `https://openrouter.ai/favicon.ico` |

Fallback 機制：`failedLogos` ref（Set）追蹤載入失敗的 key，失敗時改顯示供應商名稱首字母（灰底圓角方塊）。

---

## 4. 統一規格

| 規格 | 值 |
|------|----|
| 套件 | `lucide-vue-next ^1.0.0` |
| size（一般按鈕） | `16` |
| size（導覽列） | `18` |
| size（Empty 狀態） | `36` |
| stroke-width | `1.5`（發送鈕為 `2`） |
| color | 繼承父元素（不寫死） |
| 使用方式 | `<Upload :size="16" :stroke-width="1.5" />` |

---

## 5. 踩坑記錄

### 5.1 NavBar — icon 需傳入 component 物件而非字串

**問題**：原寫法 `{ icon: 'MessageSquare' }` 配合 `<component :is="item.icon" />` 無法解析 lucide 元件。

**解法**：import 後直接傳入物件引用：
```js
import { MessageSquare, FolderOpen, ... } from 'lucide-vue-next'
const navItems = [
  { icon: MessageSquare, ... },  // ✅ component 物件
  // { icon: 'MessageSquare', ... }  // ❌ 字串無法解析
]
```

---

### 5.2 DocsView — Loading spinner 需自訂旋轉動畫

**問題**：Element Plus `<el-icon class="is-loading">` 有內建旋轉 CSS；Lucide `<Loader2>` 本身不旋轉。

**解法**：在 `<style scoped>` 加入：
```css
.lucide-spin {
  animation: lucide-rotate 1s linear infinite;
}
@keyframes lucide-rotate {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}
```
使用時：`<Loader2 :size="32" class="lucide-spin" />`

---

## 6. 檔案異動清單

| 檔案 | 異動類型 | 說明 |
|------|---------|------|
| `frontend/package.json` | 新增依賴 | `lucide-vue-next ^1.0.0` |
| `frontend/src/components/NavBar.vue` | 修改 | 全部 icon 改用 lucide |
| `frontend/src/views/ChatView.vue` | 修改 | 所有功能按鈕 icon 替換 |
| `frontend/src/views/DocsView.vue` | 修改 | 25+ 處 icon 替換，加 `.lucide-spin` CSS |
| `frontend/src/components/AgentPanel.vue` | 修改 | Tab / 按鈕 icon 全部替換 |
| `frontend/src/views/SettingsView.vue` | 修改 | 供應商 emoji → 官方 logo，加 `Layers` icon |
