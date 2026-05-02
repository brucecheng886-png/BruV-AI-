; 解除安裝前強制結束 BruV AI 進程，避免檔案鎖定導致解除安裝失敗
!macro customUnInstall
  nsExec::Exec 'taskkill /F /IM "BruV AI.exe" /T'
  Sleep 2000

  ; 詢問是否清除 Docker 容器
  MessageBox MB_YESNO|MB_ICONQUESTION "是否同時停止並刪除 BruV AI 的 Docker 容器？$\n$\n選「是」：停止容器並刪除，但保留資料（資料庫、上傳檔案）$\n選「否」：不動 Docker，容器保持現狀" IDNO skip_docker_stop
    nsExec::Exec 'docker compose -p bruv-ai down --remove-orphans'
    Sleep 3000

    ; 詢問是否進一步完全刪除資料
    MessageBox MB_YESNO|MB_ICONEXCLAMATION "是否進一步刪除所有資料？$\n$\n❗ 此操作將永久刪除：$\n• 資料庫內容（知識庫、對話記錄）$\n• AI 模型安裝檔案$\n• 上傳的所有檔案$\n$\n此操作不可復原！" IDNO skip_purge
      nsExec::Exec 'docker compose -p bruv-ai down -v --remove-orphans'
      Sleep 3000
      nsExec::Exec 'powershell -NoProfile -Command "& { $$ids = docker ps -aq --filter name=bruv_ai_; if ($$ids) { $$ids | ForEach-Object { docker rm -f $$_ } } }"'
      Sleep 1000
      nsExec::Exec 'docker volume rm bruv-ai_postgres_data bruv-ai_neo4j_data bruv-ai_neo4j_logs bruv-ai_qdrant_data bruv-ai_minio_data bruv-ai_redis_data bruv-ai_ollama_data bruv-ai_huggingface_cache'
      Sleep 1000
    skip_purge:
  skip_docker_stop:

  ; 清除 userData（setup-complete.json、.env、token.enc 等），確保重裝後進入 setup wizard
  RMDir /r "$APPDATA\BruV AI"
!macroend
