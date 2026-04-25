# BruV AI 圖示規格

## 圖示套件
- 主要套件：lucide-vue-next
- 例外：模型供應商官方 logo（Ollama、OpenAI、Groq、Gemini、OpenRouter）

## 使用規格
- size: 16（小按鈕）/ 18（導航列）/ 24（空白狀態）/ 48（大型空白狀態）
- stroke-width: 1.5（統一）
- color: 繼承父元素（不寫死顏色）

## 禁止事項
- 禁止使用 emoji 作為圖示（❌ 📎 📊 等）
- 禁止使用 Element Plus 的 @element-plus/icons-vue
- 禁止使用非 lucide 的第三方圖示套件
- 禁止使用 png/jpg 圖示（模型 logo 除外）
- 禁止寫死顏色在圖示上

## 模式圖示對照
- Agent 模式 → Bot
- Ask 模式 → MessageCircle
- Plan 模式 → ListChecks
- 頁面 Agent → Monitor
- 全域 Agent → Globe
- 知識庫 Agent → BookOpen

## 導航圖示對照
- 對話 → MessageSquare
- 文件管理 → FolderOpen
- 知識圖譜 → Network
- 插件管理 → Puzzle
- 蛋白質圖譜 → Dna
- 設定/Wiki → Settings

## 功能圖示對照
- 上傳 → Upload
- 附件 → Paperclip
- 匯入連結 → FileSpreadsheet
- 刪除 → Trash2
- 搜尋 → Search
- 新增 → Plus
- 關閉/移除 → X
- 確認 → Check
- 發送 → ArrowUp
- 停止 → Square
- 複製 → Copy
- 重試 → RotateCcw
- 設定 → Settings2
- 管理 → Settings2
- 移動 → FolderInput
- 重新分析 → RefreshCw
- 展開詳情 → Eye
- 分享 → Share2
- 更多選單 → MoreHorizontal
- Grid 檢視 → LayoutGrid
- List 檢視 → List
- 下拉箭頭 → ChevronDown
- Loading → Loader2（加 .lucide-spin CSS 動畫）
