# Double Check — 第一性原理驗證框架 v2

## 核心原則
引用 first-principles-api-key skill 的精神：
「不要假設中間層是對的，永遠回到最基本的事實去驗證。」

**如果你不確定某個假設是否成立，就假設它是錯的，然後實際執行來證明它是對的。**

---

## 嚴重度分級

完成實作後，依嚴重度由高到低依序驗證：

### 🔴 P0 — 會導致系統完全無法運作（必須驗證，不可跳過）

1. **語法正確性**
   - 後端：py_compile 所有修改的 .py 檔，exit code 必須是 0
   - 前端：確認每個 <script> 都有對應的 </script>
   - Electron：node --check main.js
   - 驗證方式：執行指令，看到 exit 0 才繼續

2. **依賴存在性**
   - 所有 require() / import 的模組必須實際存在
   - 後端：確認新 import 在 requirements.txt 或標準庫
   - 前端：確認新 import 在 package.json dependencies
   - Electron：確認 require() 的模組在 electron/package.json dependencies（不是 devDependencies）
   - 驗證方式：npm ls {模組名} 或 pip show {套件名}

3. **路徑正確性**
   - packaged 和 dev 模式的路徑必須分別驗證
   - .env 路徑必須指向 app.getPath('userData')，不是 resources
   - docker-compose.yml 路徑必須指向 process.resourcesPath
   - 驗證方式：在程式碼中加 console.log 或 logger.info 印出實際路徑

### 🟠 P1 — 會導致功能錯誤但系統仍可啟動

4. **資料流完整性**
   追蹤每個改動的完整資料流：使用者輸入 → 前端 → API → 後端 → DB → 回傳
   - 每個節點的格式是否一致？
   - 有沒有哪個節點假設資料一定存在而沒有 null 檢查？
   - 驗證方式：用 API 實際呼叫，檢查 request 和 response 格式

5. **同步更新完整性**
   改動往往有連帶效應，必須主動找出所有需要同步的地方：
   - 改了後端 API 格式 → 前端呼叫是否同步？
   - 改了 DB 欄位 → models.py 和 ALTER TABLE migration 是否同步？
   - 改了容器名稱 → 用 grep 確認所有引用都同步（grep -r "ai_kb_" 確認無殘留）
   - 改了 .env 變數 → .env.example 是否同步？
   - 驗證方式：grep 搜尋相關關鍵字，確認無遺漏

### 🟡 P2 — 會影響品質但功能仍可使用

6. **Vue import 順序**
   讀取每個修改的 Vue 檔案的前 20 行，確認全部是 import 語句，沒有任何 const / ref / reactive 插入其中
   - 驗證方式：實際讀取前 20 行並逐行確認

7. **API Key 路徑（引用 first-principles-api-key skill）**
   所有 LLM 呼叫必須走 model-level key 查詢，不可直接讀 system_settings
   - 驗證方式：grep 確認新增的 LLM 呼叫有走 resolve_model_runtime

8. **健康檢查**
   執行 api_health_check.py 確認 10/10 PASS
   - 驗證方式：docker compose exec -T backend python scripts/api_health_check.py

---

## 已知踩坑快速確認表

每次實作完成後，對照以下清單，若有相關改動必須確認：

| 改動類型 | 必須確認的踩坑 |
|---------|--------------|
| 新增 Vue 元件或修改 script setup | Import 順序（前 20 行全是 import） |
| 新增 HTML 檔案 | 每個 \<script\> 都有 \</script\> |
| 新增 Electron require() | 模組在 dependencies，已 npm install |
| 修改 Electron 路徑邏輯 | packaged 和 dev 模式路徑分別正確 |
| 修改資料庫 schema | models.py + ALTER TABLE + 前端 API 三者同步 |
| 修改容器名稱 | grep -r 確認所有引用同步 |
| 新增 LLM 呼叫 | 走 resolve_model_runtime，不直接讀 system_settings |
| 修改 M2M 關聯資料 | document_knowledge_bases 同步寫入 |
| 使用 Qdrant | 使用 query_points()，不使用 search() |
| Celery Task | 不使用 async，LLM 呼叫用 httpx.Client 同步版本 |

---

## 新踩坑記錄機制

當發現新的踩坑（不在上表中），必須：
1. 立即修復問題
2. 在上表新增一行記錄
3. 在 commit message 中標注「chore: 更新 double-check skill 新增踩坑 {描述}」

這樣踩坑表格會隨著專案成長自動更新，不會過時。

---

## 執行流程

```
完成實作
    ↓
P0 驗證（語法、依賴、路徑）
    ↓ 發現問題 → 立即修復 → 重新從 P0 開始
    ↓ 通過
P1 驗證（資料流、同步更新）
    ↓ 發現問題 → 立即修復
    ↓ 通過
P2 驗證（import 順序、API Key、健康檢查）
    ↓ 發現問題 → 立即修復
    ↓ 通過
對照踩坑快速確認表
    ↓ 發現相關改動 → 確認對應踩坑
    ↓ 全部通過
回報完成（說明執行了哪些驗證）
```

---

## 回報格式

完成實作後，回報必須包含：

**已驗證：**
- P0：py_compile EXIT 0 / node --check EXIT 0 / script 標籤完整
- P1：資料流追蹤完整 / grep 確認同步更新無遺漏
- P2：健康檢查 10/10 PASS
- 踩坑確認：[列出本次相關的踩坑項目]

**若有跳過的驗證，必須說明原因。**
