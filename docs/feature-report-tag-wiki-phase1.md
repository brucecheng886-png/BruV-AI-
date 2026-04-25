# Feature Report — Tag Wiki Phase 1

**日期**：2026-04-21  
**執行者**：GitHub Copilot  
**狀態**：✅ Build 通過，已部署

---

## 1. 功能摘要

為文件管理系統新增完整的 **標籤（Tag）** 子系統：後端建立 `tags` / `document_tags` 資料表與 REST API，前端在文件列表側欄加入標籤篩選，Grid card 支援標籤 chips + popover 貼標，Table mode 顯示標籤欄位，為後續 Tag Wiki 獨立頁面與 LLM 自動貼標提供基礎架構。

---

## 2. 完成功能清單

| # | 功能 | 說明 | 狀態 |
|---|------|------|------|
| 1 | DB Migration | 建立 `tags`、`document_tags` 兩張表 + 2 個 index | ✅ |
| 2 | ORM Models | 新增 `Tag`、`DocumentTag` model，`Document.tags_assoc` relationship | ✅ |
| 3 | Tags REST API | `GET /api/tags/`、`POST`、`PATCH /{id}`、`DELETE /{id}`、`POST /{id}/documents/{doc_id}`、`DELETE /{id}/documents/{doc_id}` 共 6 個 endpoints | ✅ |
| 4 | DocumentOut tags 欄位 | `list_documents` 回傳 `tags: list[str]`，batch load 無 N+1，支援 `tag_id` query filter | ✅ |
| 5 | `tagsApi` 前端封裝 | `api/index.js` 新增 `tagsApi`（list / create / update / delete / addToDoc / removeFromDoc） | ✅ |
| 6 | 側欄標籤篩選 | 有標籤時顯示「標籤篩選」區塊，點擊 toggle 篩選，切換 KB 時自動清除 | ✅ |
| 7 | Grid card 標籤 chips | 顯示 colored chips 可關閉；hover 後出現「＋ 標籤」popover 貼標 | ✅ |
| 8 | Table mode 標籤欄 | 120px，顯示最多 2 個 tag，超出顯示 `+N` | ✅ |

---

## 3. 檔案異動清單

| 檔案 | 異動類型 | 說明 |
|------|---------|------|
| `backend/routers/tags.py` | **新增** | Tags CRUD + 文件關聯 6 個 endpoints |
| `backend/models.py` | 更新 | 新增 `Tag`、`DocumentTag` model；`Document.tags_assoc` relationship |
| `backend/routers/documents.py` | 更新 | `DocumentOut` 補 `tags: list[str]`；`list_documents` 加 `tag_id` filter 與 batch tag load |
| `backend/main.py` | 更新 | 註冊 `tags.router`（prefix `/api/tags`） |
| `frontend/src/api/index.js` | 更新 | 新增 `tagsApi` 物件 |
| `frontend/src/views/DocsView.vue` | 更新 | 新增 `Check` icon import、`tagsApi` import、`tags`/`selectedTagId` state、`loadTags`/`selectTag`/`getTagStyle`/`toggleTagOnDoc`/`removeTagFromDocByName` 函數、側欄 tag filter UI、grid card tag chips + popover、table 標籤欄、對應 CSS |
| `scripts/init_db.sql`（或手動 migration） | 更新 | 新增 `tags` / `document_tags` DDL + index |

---

## 4. 關鍵技術決策

### 4.1 Batch load tags 避免 N+1
`list_documents` 先取出所有 doc_id，再用一次 JOIN 查詢取得全部標籤，組成 `dict[doc_id → list[str]]`，最後填入 `DocumentOut`，確保不論返回幾筆文件都只打兩次 SQL。

```python
tag_rows = await db.execute(
    select(DocumentTag.doc_id, Tag.name)
    .join(Tag, Tag.id == DocumentTag.tag_id)
    .where(DocumentTag.doc_id.in_(doc_ids))
)
tags_map = defaultdict(list)
for doc_id, name in tag_rows:
    tags_map[str(doc_id)].append(name)
```

### 4.2 Idempotent 貼標 API
`POST /api/tags/{tag_id}/documents/{doc_id}` 使用 `INSERT … ON CONFLICT DO NOTHING`，前端可安全地重複呼叫而不報錯，簡化 toggle 邏輯。

### 4.3 Tag color 以 hex 儲存，前端衍生半透明背景
tag 的 `color` 欄位存純 hex（如 `#3b82f6`），前端 `getTagStyle()` 直接 `color + '22'` 產生半透明背景，不需後端額外欄位。

### 4.4 selectTag 為純 toggle + 與 selectKb 互斥清除
`selectTag(id)` 邏輯：若已選取同一個 tag 則清除（`selectedTagId = null`），否則設新值；`selectKb()` 切換時同步清除 `selectedTagId`，避免跨 KB 的殘留篩選造成空結果。

---

## 5. 踩坑記錄

### 5.1 nginx.conf 有兩份——改到錯的那份設定一直沒生效

專案根目錄存在 `nginx/nginx.conf`，同時 `frontend/nginx.conf` 才是被 `frontend/Dockerfile` 複製進 image 的設定。  
`docker-compose.yml` 的 nginx service 以 `./frontend` build context，因此實際生效的永遠是 `frontend/nginx.conf`。  
**症狀**：每次改完 rate limit（`rate=30r/m → 60r/s`）重 build，503 依舊出現；`docker exec ai_kb_nginx nginx -T` 確認後才發現 container 內仍是舊設定。  
**解法**：修改 `frontend/nginx.conf`，並固定用 `docker exec … nginx -T` 驗收 container 內實際設定。

### 5.2 6 個 view 的 onMounted + onActivated 雙重打 API

使用 `<keep-alive>` 後，`onMounted` 只在首次掛載觸發，之後切換 tab 會觸發 `onActivated`。如果兩者都呼叫 `loadDocs()` 而首次載入尚未完成，會產生重複請求。  
**錯誤方向**：用 `debounce(loadDocs, 300)` 試圖去抖，但時機不固定仍會重複。  
**正確解法**：`let _mounting = false`，`onMounted` 設 `true` → finally 設 `false`，`onActivated` 開頭 `if (_mounting) return`，完全避免重疊。

### 5.3 apiFetch 並發限制器的必要性

6 個 view 同時 `onMounted`（頁面首次載入），每個 view 各自呼叫 `loadKbs()`、`loadDocs()`、`loadTags()` 等，瞬間累積超過 10 個請求。  
nginx rate limit（`burst=20`）在短時間內被打爆，出現 503。  
**解法**：在 `apiFetch` 前加入並發限制器（`MAX_CONCURRENT=6`），使用 Promise queue 確保同時在途請求不超過上限，從根本解決 burst 超標問題，而非單純放大 nginx 的 burst 值。

---

## 6. 後續待辦（Phase 2）

- [ ] **tag_relations 表**：標籤橫向關聯（同義詞、上下位詞），支援 ontology 式的知識組織
- [ ] **LLM 自動貼標籤**：文件上傳/處理完成後，由 LLM 根據內容推薦標籤（`DocumentTag.source = 'llm_auto'`，`confidence` 欄位存信心分數）
- [ ] **Tag Wiki 獨立頁面**：`/wiki` 路由，顯示所有 tag 的定義、說明、關聯文件列表，可編輯 tag 描述
- [ ] **RAG 搜尋支援 tag filter**：`POST /api/search` 加入 `tag_ids` 參數，檢索時先以 tag 縮小候選文件範圍再做向量搜尋
