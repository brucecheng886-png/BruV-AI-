@echo off
chcp 65001 >nul
:: 用 PowerShell 執行真正的啟動邏輯（彩色輸出、並行健康檢查）
powershell -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0scripts\dev-start.ps1'"

