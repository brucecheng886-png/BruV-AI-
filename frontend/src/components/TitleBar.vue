<template>
  <div class="titlebar">
    <div class="titlebar-left">
      <div class="titlebar-menus" @mousedown.stop>
        <el-dropdown trigger="click">
          <span class="menu-trigger">檢視</span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="call('reload')">重新整理 (F5)</el-dropdown-item>
              <el-dropdown-item @click="call('forceReload')">強制重新整理</el-dropdown-item>
              <el-dropdown-item divided @click="call('toggleDevTools')">開發者工具 (F12)</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-dropdown trigger="click">
          <span class="menu-trigger">視窗</span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="call('minimize')">最小化</el-dropdown-item>
              <el-dropdown-item divided @click="call('quit')">離開</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>
    <!-- 自訂視窗控制按鈕：最小化 / 全螢幕 / 關閉 -->
    <div class="titlebar-controls" @mousedown.stop>
      <button class="wc-btn" @click="call('minimize')" title="最小化">
        <svg width="10" height="2" viewBox="0 0 10 2"><rect width="10" height="2" rx="1" fill="currentColor"/></svg>
      </button>
      <button class="wc-btn" @click="call('maximize')" title="全螢幕">
        <svg width="10" height="10" viewBox="0 0 10 10"><rect x="0.75" y="0.75" width="8.5" height="8.5" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>
      </button>
      <button class="wc-btn" @click="call('quit')" title="關閉">
        <svg width="10" height="10" viewBox="0 0 10 10"><path d="M1.5 1.5 L8.5 8.5 M8.5 1.5 L1.5 8.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
      </button>
    </div>
  </div>
  <!-- 分隔線：fixed 定位放在 overlay 下方，確保延伸到最右側 -->
  <div class="titlebar-divider" />
</template>

<script setup>
function call(method) {
  window.electronApp?.[method]?.()
}
</script>

<style scoped>
.titlebar {
  height: 38px;
  background: #f0f0f0;
  border-bottom: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  -webkit-app-region: drag;
  user-select: none;
  flex-shrink: 0;
}

.titlebar-controls {
  display: flex;
  align-items: center;
  gap: 6px;
  padding-right: 10px;
  -webkit-app-region: no-drag;
}

.wc-btn {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: none;
  background: #e4e4e4;
  color: #555;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.12s, color 0.12s;
  flex-shrink: 0;
}

.wc-btn:hover {
  background: #c8c8c8;
  color: #222;
}

.titlebar-left {
  display: flex;
  align-items: center;
  height: 100%;
}

.titlebar-menus {
  display: flex;
  align-items: center;
  height: 100%;
  -webkit-app-region: no-drag;
}

.menu-trigger {
  display: inline-flex;
  align-items: center;
  height: 38px;
  padding: 0 12px;
  font-size: 13px;
  color: #333;
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.12s;
}

.menu-trigger:hover {
  background: #ddd;
  color: #111;
}

/* 全寬分隔線：fixed 在 titlebar 正下方，不受 overlay 裁切 */
.titlebar-divider {
  position: fixed;
  top: 38px;
  left: 0;
  right: 0;
  height: 1px;
  background: #b0b8c4;
  z-index: 100;
  -webkit-app-region: no-drag;
}
</style>
