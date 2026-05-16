<template>
  <div class="folder-tree-wrap">
    <div class="folder-tree-title" @click="$emit('enter-drive')" style="cursor:pointer;" title="開啟共享硬碟">
      <HardDrive :size="13" :stroke-width="1.5" style="margin-right:5px;flex-shrink:0;" />
      共享硬碟
      <el-button
        v-if="isAdmin"
        link
        size="small"
        style="margin-left:auto;padding:0;"
        title="新增根目錄資料夾"
        @click.stop="$emit('create-folder', null)"
      >
        <Plus :size="13" :stroke-width="1.5" />
      </el-button>
    </div>

    <div v-if="loading" class="folder-tree-loading">
      <Loader2 :size="16" class="lucide-spin" />
    </div>

    <el-empty v-else-if="rootFolders.length === 0" description="尚無資料夾" :image-size="40" />

    <div v-else class="folder-tree-list">
      <FolderTreeNode
        v-for="f in rootFolders"
        :key="f.id"
        :folder="f"
        :selected-id="selectedId"
        :is-admin="isAdmin"
        @select="onSelect"
        @create-folder="(pid) => $emit('create-folder', pid)"
        @rename="(f) => $emit('rename', f)"
        @share="(f) => $emit('share', f)"
        @delete="(f) => $emit('delete-folder', f)"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, defineProps, defineEmits, defineExpose } from 'vue'
import { HardDrive, Plus, Loader2 } from 'lucide-vue-next'
import { foldersApi } from '../api/index.js'
import FolderTreeNode from './FolderTreeNode.vue'

const props = defineProps({
  selectedId: { type: String, default: null },
  isAdmin: { type: Boolean, default: false },
})

const emit = defineEmits(['folder-selected', 'create-folder', 'rename', 'share', 'delete-folder', 'enter-drive'])

const rootFolders = ref([])
const loading = ref(false)

async function loadFolders() {
  loading.value = true
  try {
    rootFolders.value = await foldersApi.list()
  } catch {
    rootFolders.value = []
  } finally {
    loading.value = false
  }
}

function onSelect(folder) {
  emit('folder-selected', folder)
}

onMounted(loadFolders)

defineExpose({ reload: loadFolders })
</script>

<style scoped>
.folder-tree-wrap {
  padding: 8px 0 4px;
}
.folder-tree-title {
  display: flex;
  align-items: center;
  font-size: 11px;
  font-weight: 600;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: .04em;
  padding: 0 12px 6px;
}
.folder-tree-loading {
  display: flex;
  justify-content: center;
  padding: 12px 0;
  color: #94a3b8;
}
.folder-tree-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
</style>
