<template>
  <div class="titlebar">
    <!-- 左側：Logo + 名稱 -->
    <div class="tb-left" @mousedown.stop>
      <img src="/logo.svg" class="tb-logo" alt="logo" />
      <span class="tb-appname">BruV AI 知識庫</span>
    </div>

    <!-- 中間：拖曳空白區 -->
    <div class="tb-drag"></div>

    <!-- 右側：icon 按鈕區 -->
    <div class="tb-right" @mousedown.stop>
      <button class="tb-btn" title="重新整理 (F5)" @click="call('reload')">
        <RefreshCw :size="15" :stroke-width="1.8" />
      </button>
      <button class="tb-btn" title="開發者工具 (F12)" @click="call('toggleDevTools')">
        <Terminal :size="15" :stroke-width="1.8" />
      </button>
    </div>

    <!-- Windows 原生視窗按鈕佔位，約 138px -->
    <div class="tb-winctl"></div>
  </div>
  <div class="titlebar-divider" />
</template>

<script setup>
import { RefreshCw, Terminal } from 'lucide-vue-next'

function call(method) {
  window.electronApp?.[method]?.()
}
</script>

<style scoped>
.titlebar {
  height: 38px;
  background: #1e293b;
  display: flex;
  align-items: center;
  -webkit-app-region: drag;
  user-select: none;
  flex-shrink: 0;
}

/* 左側 Logo + 名稱 */
.tb-left {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 14px;
  -webkit-app-region: no-drag;
  flex-shrink: 0;
}
.tb-logo {
  width: 22px;
  height: 22px;
}
.tb-appname {
  font-size: 13px;
  font-weight: 600;
  color: #e2e8f0;
  letter-spacing: 0.02em;
  white-space: nowrap;
}

/* 中間拖曳區 */
.tb-drag {
  flex: 1;
  height: 100%;
}

/* 右側 icon 按鈕 */
.tb-right {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 0 6px;
  -webkit-app-region: no-drag;
  flex-shrink: 0;
}
.tb-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 28px;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: #94a3b8;
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}
.tb-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #e2e8f0;
}

/* Windows 原生視窗按鈕佔位 */
.tb-winctl {
  width: 138px;
  flex-shrink: 0;
  -webkit-app-region: no-drag;
}

/* 全寬分隔線 */
.titlebar-divider {
  position: fixed;
  top: 38px;
  left: 0;
  right: 0;
  height: 1px;
  background: #334155;
  z-index: 100;
  -webkit-app-region: no-drag;
}
</style>
