; 解除安裝前強制結束 BruV AI 進程，避免檔案鎖定導致解除安裝失敗
!macro customUnInstall
  ; 結束主程式與所有 Electron helper 子進程
  nsExec::Exec 'taskkill /F /IM "BruV AI.exe" /T'
  nsExec::Exec 'taskkill /F /IM "BruV AI Helper.exe" /T'
  nsExec::Exec 'taskkill /F /IM "BruV AI Helper (GPU).exe" /T'
  nsExec::Exec 'taskkill /F /IM "BruV AI Helper (Renderer).exe" /T'
  nsExec::Exec 'taskkill /F /IM "BruV AI Helper (Plugin).exe" /T'
  Sleep 3000

  ; 靜默模式 = electron-updater 自動更新呼叫，跳過解除安裝對話框與資料清理，直接覆蓋安裝
  ${If} ${Silent}
    Return
  ${EndIf}

  ; 用 PowerShell WinForms 顯示有勾選欄位的對話框
  ; Exit Code: 0=什麼都不做  1=刪容器（保留資料）  3=刪容器+資料  99=取消解除安裝
  nsExec::ExecToStack 'powershell -NoProfile -WindowStyle Hidden -Command "\
    Add-Type -AssemblyName System.Windows.Forms; \
    Add-Type -AssemblyName System.Drawing; \
    $$f = New-Object System.Windows.Forms.Form; \
    $$f.Text = \"BruV AI 解除安裝\"; \
    $$f.Size = New-Object System.Drawing.Size(460, 240); \
    $$f.StartPosition = \"CenterScreen\"; \
    $$f.FormBorderStyle = \"FixedDialog\"; \
    $$f.MaximizeBox = $$false; \
    $$f.MinimizeBox = $$false; \
    $$lbl = New-Object System.Windows.Forms.Label; \
    $$lbl.Text = \"請選擇解除安裝後的清理選項：\"; \
    $$lbl.Location = New-Object System.Drawing.Point(20, 20); \
    $$lbl.Size = New-Object System.Drawing.Size(400, 20); \
    $$cb1 = New-Object System.Windows.Forms.CheckBox; \
    $$cb1.Text = \"停止並刪除 Docker 容器（保留資料庫與上傳檔案）\"; \
    $$cb1.Location = New-Object System.Drawing.Point(20, 55); \
    $$cb1.Size = New-Object System.Drawing.Size(400, 24); \
    $$cb2 = New-Object System.Windows.Forms.CheckBox; \
    $$cb2.Text = \"同時刪除所有資料（資料庫、模型、上傳檔案）⚠ 不可復原\"; \
    $$cb2.Location = New-Object System.Drawing.Point(20, 85); \
    $$cb2.Size = New-Object System.Drawing.Size(400, 24); \
    $$cb2.add_CheckedChanged({ if ($$cb2.Checked) { $$cb1.Checked = $$true } }); \
    $$btnOK = New-Object System.Windows.Forms.Button; \
    $$btnOK.Text = \"確認解除安裝\"; \
    $$btnOK.Location = New-Object System.Drawing.Point(240, 155); \
    $$btnOK.Size = New-Object System.Drawing.Size(100, 30); \
    $$btnOK.DialogResult = \"OK\"; \
    $$btnCancel = New-Object System.Windows.Forms.Button; \
    $$btnCancel.Text = \"取消\"; \
    $$btnCancel.Location = New-Object System.Drawing.Point(350, 155); \
    $$btnCancel.Size = New-Object System.Drawing.Size(80, 30); \
    $$btnCancel.DialogResult = \"Cancel\"; \
    $$f.Controls.AddRange(@($$lbl, $$cb1, $$cb2, $$btnOK, $$btnCancel)); \
    $$f.AcceptButton = $$btnOK; \
    $$f.CancelButton = $$btnCancel; \
    $$r = $$f.ShowDialog(); \
    if ($$r -eq \"Cancel\") { exit 99 }; \
    if ($$cb2.Checked) { exit 3 }; \
    if ($$cb1.Checked) { exit 1 }; \
    exit 0"'
  Pop $0  ; stdout（忽略）
  Pop $1  ; exit code

  ; exit code 99 = 使用者按取消 → 中斷解除安裝
  IntCmp $1 99 abort_uninstall done_check done_check
  abort_uninstall:
    Abort "已取消解除安裝。"

  done_check:
  ; exit code 1 或 3 → 刪除容器
  IntCmp $1 0 skip_docker skip_docker do_docker
  do_docker:
    nsExec::Exec 'docker compose -p bruv-ai down --remove-orphans'
    Sleep 3000

    ; exit code 3 → 進一步刪除所有資料
    IntCmp $1 3 do_purge skip_purge skip_purge
    do_purge:
      nsExec::Exec 'docker compose -p bruv-ai down -v --remove-orphans'
      Sleep 3000
      nsExec::Exec 'powershell -NoProfile -Command "& { $$ids = docker ps -aq --filter name=bruv_ai_; if ($$ids) { $$ids | ForEach-Object { docker rm -f $$_ } } }"'
      Sleep 1000
      nsExec::Exec 'docker volume rm bruv-ai_postgres_data bruv-ai_neo4j_data bruv-ai_neo4j_logs bruv-ai_qdrant_data bruv-ai_minio_data bruv-ai_redis_data bruv-ai_ollama_data bruv-ai_huggingface_cache'
      Sleep 1000
    skip_purge:
  skip_docker:

  ; 清除 userData（setup-complete.json、.env、token.enc 等），確保重裝後進入 setup wizard
  ; ⚠️ Electron userData 路徑 = $APPDATA\{package.json "name"} = $APPDATA\bruv-ai-kb
  ;    （不是 productName "BruV AI"，過去刪錯路徑導致 setup-complete.json 殘留）
  nsExec::Exec `powershell -NoProfile -WindowStyle Hidden -Command "Remove-Item -LiteralPath '$APPDATA\bruv-ai-kb' -Recurse -Force -ErrorAction SilentlyContinue"`

  ; 清除 electron-updater 暫存目錄（$LOCALAPPDATA\bruv-ai-kb-updater）
  ; 內含已下載的更新安裝程式，不刪除會殘留佔用空間
  nsExec::Exec `powershell -NoProfile -WindowStyle Hidden -Command "Remove-Item -LiteralPath '$LOCALAPPDATA\bruv-ai-kb-updater' -Recurse -Force -ErrorAction SilentlyContinue"`
!macroend
