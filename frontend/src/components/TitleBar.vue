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
              <el-dropdown-item @click="call('maximize')">最大化 / 還原</el-dropdown-item>
              <el-dropdown-item divided @click="call('quit')">離開</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>
  </div>
</template>

<script setup>
function call(method) {
  window.electronApp?.[method]?.()
}
</script>

<style scoped>
.titlebar {
  height: 38px;
  background: #f1f5f9;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  align-items: center;
  -webkit-app-region: drag;
  user-select: none;
  flex-shrink: 0;
  /* right side reserved for native window controls (~138px) */
  padding-right: 145px;
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
  color: #475569;
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.12s;
}

.menu-trigger:hover {
  background: #e2e8f0;
  color: #1e293b;
}
</style>
