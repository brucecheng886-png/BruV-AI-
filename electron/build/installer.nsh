; 解除安裝前強制結束 BruV AI 進程，避免檔案鎖定導致解除安裝失敗
!macro customUnInstall
  nsExec::Exec 'taskkill /F /IM "BruV AI.exe" /T'
  Sleep 2000
!macroend
