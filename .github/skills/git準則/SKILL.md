---
name: git準則
description: "Git commit、branch 命名、PR 規範。使用時機：每次 commit 前、建立新 branch 前、發 PR 前。"
---

# Git 版本控制準則 v1.0

---

## 一、Branch 命名規則

```
feat/[功能描述]        → feat/chat-message-streaming
fix/[問題描述]         → fix/canvas-overlay-position
refactor/[模組名稱]    → refactor/knowledge-graph-store
chore/[雜項描述]       → chore/update-dependencies
```

---

## 二、Commit Message 規範（Conventional Commits）

格式：`<type>(<scope>): <description>`

**type 類型：**

| type | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | 修 bug |
| `refactor` | 重構（不改行為） |
| `style` | 格式調整（不影響邏輯） |
| `docs` | 文件 |
| `chore` | 雜項（依賴更新、設定檔） |
| `test` | 測試 |

**範例：**
```
feat(chat): 新增 SSE 串流訊息顯示
fix(canvas): 修正 overlay 定位基準點錯誤
refactor(store): 將 API 呼叫移至 Pinia action
```

**禁止的 commit message：**
- `"fix bug"`（太模糊）
- `"update"`（不知道改了什麼）
- `"WIP"`（不應 commit 未完成的東西到 main）

---

## 三、禁止行為

| 禁止 | 原因 |
|------|------|
| 直接 commit 到 main | 無法 review，出錯無法快速回滾 |
| 一個 commit 改超過一件事 | diff 難以閱讀，bisect 無效 |
| commit 含 `console.log` / debug code | 污染 production |
| force push 到共享 branch | 破壞他人的 commit 歷史 |
