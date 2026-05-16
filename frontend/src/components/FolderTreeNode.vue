<template>
  <div class="ftn-wrap">
    <!-- 節點列 -->
    <div
      class="ftn-row"
      :class="{ 'ftn-row--active': selectedId === folder.id }"
      :style="{ paddingLeft: (depth * 14 + 8) + 'px' }"
      @click="$emit('select', folder)"
    >
      <!-- 展開/收合箭頭 -->
      <button
        v-if="folder.children_count > 0 || expanded"
        class="ftn-toggle"
        @click.stop="toggle"
      >
        <ChevronRight
          :size="12"
          :stroke-width="2"
          :style="{ transform: expanded ? 'rotate(90deg)' : 'rotate(0)', transition: 'transform .15s' }"
        />
      </button>
      <span v-else class="ftn-toggle-ph" />

      <span class="ftn-icon">{{ folder.icon || '📁' }}</span>
      <span class="ftn-name">{{ folder.name }}</span>

      <!-- 操作選單 -->
      <el-dropdown
        trigger="click"
        placement="bottom-end"
        @command="(cmd) => handleCmd(cmd)"
        @click.stop
        class="ftn-menu"
      >
        <span class="ftn-menu-btn" @click.stop>
          <MoreHorizontal :size="13" :stroke-width="1.5" />
        </span>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="add-sub">新增子資料夾</el-dropdown-item>
            <el-dropdown-item command="rename">重新命名</el-dropdown-item>
            <el-dropdown-item command="share">分享 / 白名單</el-dropdown-item>
            <el-dropdown-item command="delete" divided style="color:#f56c6c;">刪除</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 子節點（展開後顯示） -->
    <div v-if="expanded">
      <div v-if="loadingChildren" class="ftn-loading">
        <Loader2 :size="12" class="lucide-spin" />
      </div>
      <FolderTreeNode
        v-for="child in children"
        :key="child.id"
        :folder="child"
        :depth="depth + 1"
        :selected-id="selectedId"
        :is-admin="isAdmin"
        @select="(f) => $emit('select', f)"
        @create-folder="(pid) => $emit('create-folder', pid)"
        @rename="(f) => $emit('rename', f)"
        @share="(f) => $emit('share', f)"
        @delete="(f) => $emit('delete', f)"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, defineProps, defineEmits } from 'vue'
import { ChevronRight, MoreHorizontal, Loader2 } from 'lucide-vue-next'
import { foldersApi } from '../api/index.js'

const props = defineProps({
  folder: { type: Object, required: true },
  depth: { type: Number, default: 0 },
  selectedId: { type: String, default: null },
  isAdmin: { type: Boolean, default: false },
})
const emit = defineEmits(['select', 'create-folder', 'rename', 'share', 'delete'])

const expanded = ref(false)
const loadingChildren = ref(false)
const children = ref([])

async function toggle() {
  if (expanded.value) {
    expanded.value = false
    return
  }
  expanded.value = true
  if (children.value.length === 0) {
    loadingChildren.value = true
    try {
      children.value = await foldersApi.children(props.folder.id)
    } catch {
      children.value = []
    } finally {
      loadingChildren.value = false
    }
  }
}

function handleCmd(cmd) {
  if (cmd === 'add-sub') emit('create-folder', props.folder.id)
  else if (cmd === 'rename') emit('rename', props.folder)
  else if (cmd === 'share') emit('share', props.folder)
  else if (cmd === 'delete') emit('delete', props.folder)
}
</script>

<style scoped>
.ftn-wrap { display: flex; flex-direction: column; }
.ftn-row {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 30px;
  cursor: pointer;
  border-radius: 6px;
  margin: 0 4px;
  padding-right: 4px;
  transition: background .12s;
  user-select: none;
}
.ftn-row:hover { background: rgba(100,116,139,.08); }
.ftn-row--active { background: rgba(59,130,246,.1); color: #3b82f6; }
.ftn-toggle {
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  display: flex;
  align-items: center;
  color: #94a3b8;
  flex-shrink: 0;
}
.ftn-toggle-ph { width: 12px; flex-shrink: 0; }
.ftn-icon { font-size: 13px; flex-shrink: 0; }
.ftn-name {
  flex: 1;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ftn-menu { margin-left: auto; flex-shrink: 0; }
.ftn-menu-btn {
  display: flex;
  align-items: center;
  opacity: 0;
  padding: 2px 3px;
  border-radius: 4px;
  cursor: pointer;
  color: #64748b;
  transition: opacity .12s, background .12s;
}
.ftn-row:hover .ftn-menu-btn { opacity: 1; }
.ftn-menu-btn:hover { background: rgba(100,116,139,.15); }
.ftn-loading {
  display: flex;
  padding: 4px 12px;
  color: #94a3b8;
}
</style>
