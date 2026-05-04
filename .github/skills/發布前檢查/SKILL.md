---
name: 發布前檢查
description: "每次發布新版本前的全面系統 APP 檢查。必須對比原始程式碼與更新程式碼，重點驗證所有變更點。使用時機：每次 git tag / gh release create 前，無例外。"
argument-hint: "指定版本號，例如：v1.2.0"
---

# 發布前全面檢查準則 v1.0

> **強制規則**：每次發布新版本前必須完整執行此 Skill，任何一個 ❌ 都不得發布。

---

## 零、準備工作 — 列出本次所有變更

**第一步**：執行以下指令，列出本版本與上一版本的差異清單。
```powershell
# 列出上次 tag 後所有變更的檔案
git diff --name-only $(git describe --tags --abbrev=0 HEAD^) HEAD

# 或：列出本次要 commit 的所有變更
git status --short
git diff --stat HEAD
```

**AI 必須**：
1. 讀取每一個變更的檔案（不得略過）
2. 標記每個檔案的「變更類型」：新增功能 / 修 bug / 重構 / 設定調整
3. 根據變更類型，優先執行對應的檢查區塊

---

## 一、語法完整性檢查（所有變更檔案必做）

### 1-A. Python 後端（.py 檔）
```powershell
# 對所有變更的 .py 檔做語法檢查
docker compose exec -T backend python -m py_compile backend/routers/your_changed_file.py
# exit code 必須 0
```

**自動化批次版本**：
```powershell
# 取得所有變更的 .py 並批次檢查
git diff --name-only HEAD^ HEAD | Where-Object { $_ -match '\.py$' } | ForEach-Object {
  docker compose exec -T backend python -m py_compile $_
}
```

### 1-B. Electron 主程序（main.js / preload.js）
```powershell
node --check electron/main.js
node --check electron/preload.js
# 兩者 exit code 必須都是 0
```

### 1-C. Vue 元件（.vue 檔）— import 順序（血淚教訓 ⚠️）
對**每一個**變更的 .vue 檔，讀取 `<script setup>` 後的前 30 行：
```
規則：所有 import 陳述句必須在任何 const / ref / reactive / store init 之前
違規範例（禁止）：
  import A from '...'
  const store = useStore()   ← 可執行語句夾在 import 之間
  import B from '...'        ← import 出現在可執行語句之後

正確範例：
  import A from '...'
  import B from '...'
  const store = useStore()
```
驗證命令（逐行目視確認）：
```powershell
# 讀取 script setup 前 30 行
Get-Content "frontend/src/components/ChangedFile.vue" | Select-Object -First 40
```

### 1-D. HTML 檔案（loading.html / setup-wizard.html）
```
規則：每個 <script> 都必須有對應的 </script>
驗證方式：grep 計算開頭和結尾 tag 數量是否相等
```
```powershell
(Select-String -Pattern "<script" -Path "electron/loading.html").Count
(Select-String -Pattern "</script>" -Path "electron/loading.html").Count
# 兩數必須相等
```

---

## 二、程式碼對比檢查（針對本次「更新的程式碼」）

### 2-A. 讀取每個變更檔案的 diff
```powershell
# 查看具體 diff（每個變更檔案都要看）
git diff HEAD^ HEAD -- backend/routers/changed_router.py
git diff HEAD^ HEAD -- frontend/src/views/ChangedView.vue
git diff HEAD^ HEAD -- electron/main.js
```

### 2-B. 原始程式碼 vs 更新程式碼 對比檢查清單

對每個有實質邏輯變更的檔案，依序確認：

| 檢查項目 | 原始碼狀態 | 更新碼狀態 | 結果 |
|---------|-----------|-----------|------|
| API 端點路徑是否一致 | `GET /api/old/path` | `GET /api/new/path` | ✅/❌ |
| 函式簽名是否向後相容 | `fn(a, b)` | `fn(a, b, c=None)` | ✅/❌ |
| 回傳格式是否一致 | `{"key": val}` | `{"key": val}` | ✅/❌ |
| 刪除的功能是否有前端仍在呼叫 | — | — | ✅/❌ |
| 新增功能的前後端是否同步完成 | — | — | ✅/❌ |

**具體執行**：AI 必須針對本次 diff 填寫以上表格，不得留空。

---

## 三、連帶影響同步性檢查

### 3-A. API 合約同步（最常遺漏 ⚠️）
若後端 API 有變更：
```powershell
# 確認前端 api/index.js 的對應呼叫已同步
Select-String -Pattern "changed_endpoint" -Path "frontend/src/api/index.js"
```
- [ ] 新增 API endpoint → 前端 `api/index.js` 已新增對應方法
- [ ] 修改 API 回傳格式 → 前端所有引用該 API 的地方已更新
- [ ] 刪除 API endpoint → 前端所有引用已移除或改用新端點

### 3-B. DB Schema 同步
若有新增/修改資料庫欄位：
```powershell
# 確認 models.py 和 migration 腳本一致
Select-String -Pattern "new_column" -Path "backend/models.py"
Select-String -Pattern "new_column" -Path "backend/scripts/*.py"
```
- [ ] `models.py` 欄位定義已更新
- [ ] DB migration 腳本 (`scripts/`) 已建立
- [ ] 若有 default 值，Alembic/SQL 腳本已正確指定

### 3-C. 環境變數同步
若 `.env` 新增變數：
```powershell
# 比較 .env.example 和實際使用的 env 變數
Select-String -Pattern "NEW_VAR" -Path ".env.example"
Select-String -Pattern "NEW_VAR" -Path "backend/config.py"
Select-String -Pattern "NEW_VAR" -Path "docker-compose.yml"
```
- [ ] `.env.example` 已加入說明（含預設值）
- [ ] `backend/config.py` 已加入讀取
- [ ] `docker-compose.yml` 的 environment 區塊已加入

### 3-D. Electron IPC 同步
若 `electron/main.js` 有新增 `ipcMain.handle` / `ipcMain.on`：
```powershell
# 確認 preload.js 有對應暴露
Select-String -Pattern "new:channel" -Path "electron/preload.js"
# 確認前端有實際呼叫
Select-String -Pattern "new:channel\|newChannel" -Path "frontend/src" -Recurse
```
- [ ] `preload.js` 已暴露對應的 `ipcRenderer.invoke` / `ipcRenderer.on`
- [ ] 前端有實際呼叫點
- [ ] 若有 `onXxx` 事件監聽，確認 main.js 有對應的 `webContents.send`

### 3-E. Electron 版本號同步
每次發布都必須確認：
```powershell
# 三個地方的版本號必須一致
Get-Content "electron/package.json" | Select-String '"version"'
Get-Content "package.json" | Select-String '"version"'  # 若有根目錄 package.json
```
- [ ] `electron/package.json` 已更新版本號

---

## 四、前端完整性檢查

### 4-A. Build 無錯誤（必做）
```powershell
# 用 Docker 做 production build（Windows 本機會 OOM）
cd "c:\Users\bruce\PycharmProjects\BruV AI新架構"
docker run --rm -v "${PWD}/frontend:/app" node:20-alpine sh -c "cd /app && npm ci --silent && npm run build" > frontend/build_check.txt 2>&1
$exit = $LASTEXITCODE
Get-Content "frontend/build_check.txt" | Select-Object -Last 20
Write-Host "Exit: $exit"
# 必須 exit=0，且最後看到 "built in"
```

### 4-B. 新增/修改的 Vue 元件功能驗證
對每個改動的 Vue 元件，目視確認：
- [ ] 新增的 `ref()` 是否有在 template 中被正確引用（無 undefined 引用）
- [ ] `v-if` / `v-show` 條件是否合理（不會永遠 false 導致區塊隱形）
- [ ] `@click` / `@change` handler 是否都已在 `<script setup>` 中定義
- [ ] `emit` 的事件名稱是否與父層的 `v-on` 一致

### 4-C. API 方法完整性
```powershell
# 確認前端 api/index.js 的所有新增方法有被實際使用
Select-String -Pattern "newApiMethod" -Path "frontend/src" -Recurse
```

---

## 五、後端 API 功能測試

### 5-A. Health Check（必做）
```powershell
curl http://localhost:80/api/health
# 必須回傳 {"status": "ok"} 且 HTTP 200
```

### 5-B. 本次變更的 API Endpoint 測試
對**每個新增或修改的 API endpoint**，必須實際執行一次測試：

```python
# 測試腳本範本（建立在 scripts/pre_release_test_vX.X.X.py）
import requests

BASE = "http://localhost:80"
HEADERS = {"Content-Type": "application/json"}

# 先取得 token
r = requests.post(f"{BASE}/api/auth/login", json={"email": "admin", "password": "admin123"}, headers=HEADERS)
token = r.json()["access_token"]
AUTH = {**HEADERS, "Authorization": f"Bearer {token}"}

tests = []

# ── 依本次變更逐一新增測試 ──
# 範例：新增的 GET /api/settings/ollama/installed
r = requests.get(f"{BASE}/api/settings/ollama/installed", headers=AUTH)
tests.append(("GET /ollama/installed", r.status_code == 200 and "models" in r.json()))

# ── 安全性測試（有接受字串輸入的 endpoint 必做）──
# 範例：path traversal 防護
r = requests.delete(f"{BASE}/api/settings/ollama/delete",
                    json={"model": "../etc/passwd"}, headers=AUTH)
tests.append(("Path traversal blocked", r.status_code == 400))

# 結果
for name, passed in tests:
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"{status}  {name}")
failed = sum(1 for _, p in tests if not p)
print(f"\n{'全部通過 ✅' if failed == 0 else f'{failed} 項失敗 ❌'}")
```

執行：
```powershell
python scripts/pre_release_test_vX.X.X.py
# 必須全部 PASS，否則不得發布
```

### 5-C. 安全性基本驗證（有新增接受外部輸入的 endpoint 必做）
- [ ] 字串輸入有長度限制（或有 regex 驗證）
- [ ] 路徑相關參數拒絕 `..` / `../` （path traversal）
- [ ] 未登入請求回傳 401（不是 500）
- [ ] 管理員專用 endpoint 非 admin role 回傳 403

---

## 六、Electron 打包驗證

### 6-A. 基本語法 + 依賴
```powershell
node --check electron/main.js
node --check electron/preload.js
cd electron; npm ls --depth=0 2>&1 | Select-String "UNMET\|missing\|ERR"
# 無 UNMET DEPENDENCY 或 missing
```

### 6-B. 版本號確認
```powershell
Get-Content "electron/package.json" | Select-String '"version"'
# 確認版本號符合本次發布計畫
```

### 6-C. Build 測試（非必須，但正式 release 前建議）
```powershell
cd "c:\Users\bruce\PycharmProjects\BruV AI新架構\electron"
npm run dist 2>&1 | Select-String "target|file|error|Error|Building|created" | Select-Object -Last 10
# 確認最後看到 "building block map" 或 "file=dist\BruV.AI.Setup.X.X.X.exe"
```

---

## 七、Docker Image 驗證

### 7-A. 確認最新 dist 已 copy 進 nginx
```powershell
# 確認前端 dist 是最新 build 的結果
docker exec bruv_ai_nginx ls -la /usr/share/nginx/html/assets/ | Select-Object -Last 5
# 確認 timestamp 是今天
```

### 7-B. Container 狀態
```powershell
docker compose ps
# 所有 container 必須 Status = running，Health = healthy（若有 healthcheck）
```

### 7-C. Image Build（正式發布前）
```powershell
# Backend
docker build -t ghcr.io/brucecheng886-png/bruv-ai-backend:latest ./backend 2>&1 | Select-String "naming|ERROR" | Select-Object -Last 3

# Frontend（nginx）
docker build -t ghcr.io/brucecheng886-png/bruv-ai-nginx:latest ./frontend 2>&1 | Select-String "naming|ERROR" | Select-Object -Last 3

# 兩者必須都看到 "naming to ... done"
```

---

## 八、回滾準備

**在發布前，確認有辦法快速回滾**：

```powershell
# 確認上一個 tag 存在且可回滾
git tag --sort=-version:refname | Select-Object -First 3
# 應看到最近 3 個版本 tag

# 確認上一個 release 的 Docker image 仍可拉取
docker pull ghcr.io/brucecheng886-png/bruv-ai-backend:v1.0.48  # 前一版本
```

回滾步驟（若新版本發現嚴重 bug）：
1. `git checkout v前一版本`
2. `docker pull ghcr.io/brucecheng886-png/bruv-ai-backend:v前一版本`
3. 修改 `docker-compose.yml` image tag → 前一版本
4. `docker compose up -d`

---

## 九、發布清單（最終確認）

發布前逐項打勾：

```
版本資訊
  [ ] electron/package.json 版本號已更新
  [ ] git commit message 包含版本號

程式碼品質
  [ ] 所有變更的 .py 檔 py_compile 通過（exit 0）
  [ ] 所有變更的 .vue 檔 import 順序正確（前 30 行目視確認）
  [ ] electron/main.js 和 preload.js node --check 通過
  [ ] 前端 production build 成功（exit 0）

連帶同步
  [ ] 後端 API 變更 → 前端 api/index.js 已同步
  [ ] Electron IPC 新增 → preload.js 已暴露
  [ ] .env 新增變數 → .env.example 已同步

功能測試
  [ ] /api/health 回傳 ok
  [ ] 所有本次新增/修改的 endpoint 測試腳本全 PASS
  [ ] 有新增外部輸入的 endpoint 安全性驗證通過

Docker
  [ ] frontend dist 已用 Docker 重新 build（非本機直接 build）
  [ ] backend image build 成功（naming to ... done）
  [ ] frontend nginx image build 成功（naming to ... done）

發布動作
  [ ] git commit 完整（含所有相關檔案）
  [ ] git push origin main
  [ ] docker push backend image
  [ ] docker push nginx image
  [ ] electron npm run dist（installer 已產出）
  [ ] gh release create 含 .exe 和 .exe.blockmap
```

---

## 十、AI 執行此 Skill 的行動規範

1. **不得跳過任何有「必做」標記的項目**
2. **每個檢查項目必須真實執行命令**，不得憑記憶或猜測
3. **遇到任何 ❌ 必須停止發布流程**，回到修復再重跑此 Skill
4. **對比原始碼與更新碼**：使用 `git diff HEAD^ HEAD -- <file>` 取得 diff，逐行理解變更邏輯
5. **測試腳本必須真實執行**，結果必須全部 PASS 才繼續
6. **最終以第九節「發布清單」為準**，所有項目打勾後才執行發布指令
