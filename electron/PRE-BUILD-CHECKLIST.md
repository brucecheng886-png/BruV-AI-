# Electron 打包前檢查清單

每次執行 `npm run dist` 前，逐一確認以下項目。

---

## 🔴 絕對不能打包的檔案

| 檔案 | 原因 | 替代方案 |
|------|------|----------|
| `../.env` | 含真實密碼（POSTGRES_PASSWORD、JWT_SECRET_KEY 等），打包後所有用戶共用開發者密碼 | 打包 `../.env.example`（含 `changeme_` 佔位符） |
| `../docker-compose.yml` | 使用 `build: ./backend`（本機原始碼 build），安裝到用戶機器上會找不到路徑 | 打包 `../docker-compose.release.yml`（使用 `image: ghcr.io/...`） |

---

## ✅ 打包前逐項確認

### 1. extraResources 來源正確

在 `package.json` 的 `build.extraResources` 確認：

```jsonc
// ✅ 正確
{ "from": "../.env.example",             "to": ".env.example" }
{ "from": "../docker-compose.release.yml","to": "docker-compose.yml" }

// ❌ 錯誤（絕不能出現）
{ "from": "../.env",                     "to": ".env" }
{ "from": "../docker-compose.yml",       "to": "docker-compose.yml" }
```

**快速指令確認：**
```powershell
Select-String -Path "electron\package.json" -Pattern '"from"' | Select-Object Line
```
輸出應該只看到 `.env.example` 和 `docker-compose.release.yml`，不能出現 `"../.env"` 或 `"docker-compose.yml"`。

---

### 2. .env.example 佔位符完整（未被意外替換）

```powershell
Select-String -Path ".env.example" -Pattern "changeme_|your_.*_here"
```
應該回傳 **8 個** matches（POSTGRES_PASSWORD、NEO4J_PASSWORD 等）。
若回傳 0，代表 `.env.example` 被真實值汙染，需從 git 還原。

---

### 3. docker-compose.release.yml 使用 image 而非 build

```powershell
Select-String -Path "docker-compose.release.yml" -Pattern "^\s*build:"
```
應該**無輸出**。若有輸出，代表某個 service 還在用本機 build，用戶裝機後找不到原始碼。

---

### 4. GHCR images 已推送最新版

若本次有改動以下目錄，必須先 rebuild + push 對應 image，否則用戶拉到舊版：

| 改動位置 | 需 rebuild 的 image |
|----------|---------------------|
| `frontend/src/**` 或 `frontend/nginx.conf` | `ghcr.io/.../bruv-ai-nginx:latest` |
| `backend/**` | `ghcr.io/.../bruv-ai-backend:latest` |

**確認指令（看 digest 是否與最後一次 push 一致）：**
```powershell
docker inspect ghcr.io/brucecheng886-png/bruv-ai-nginx:latest --format "{{index .RepoDigests 0}}"
docker inspect ghcr.io/brucecheng886-png/bruv-ai-backend:latest --format "{{index .RepoDigests 0}}"
```

---

### 5. electron/package.json 版本號已更新

```powershell
Select-String -Path "electron\package.json" -Pattern '"version"'
```
確認比上一個 release 版本高。

---

## 打包指令

```powershell
cd electron
npm run dist
```

打包成功的標誌（最後幾行）：
```
building block map  blockMapFile=dist\BruV AI Setup X.X.X.exe.blockmap
```

---

## 打包後驗證

```powershell
# 確認 .env.example 有進 resources（不能是 .env）
Test-Path "electron\dist\win-unpacked\resources\.env.example"   # → True
Test-Path "electron\dist\win-unpacked\resources\.env"           # → False

# 確認 docker-compose 用 image（不能有 build:）
Select-String "electron\dist\win-unpacked\resources\docker-compose.yml" -Pattern "^\s*build:"
# → 無輸出
```
