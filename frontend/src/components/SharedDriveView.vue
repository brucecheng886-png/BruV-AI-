<template>
  <div class="sdv-wrap">

    <!-- Header: Breadcrumb + Actions -->
    <div class="sdv-header">
      <div class="sdv-breadcrumb">
        <HardDrive :size="15" class="sdv-hd-icon" />
        <button class="sdv-bc-root" @click="navigateRoot">共享硬碟</button>
        <template v-for="(f, i) in navStack" :key="f.id">
          <ChevronRight :size="12" class="sdv-bc-sep" />
          <button
            class="sdv-bc-item"
            :class="{ active: i === navStack.length - 1 }"
            @click="navigateTo(i)"
          >{{ f.name }}</button>
        </template>
      </div>
      <div class="sdv-actions">
        <el-button v-if="currentFolderId" size="small" @click="openAddDocs">
          <Plus :size="13" :stroke-width="1.5" style="margin-right:4px;" />加入文件
        </el-button>
        <el-button size="small" type="primary" @click="openCreateFolder">
          <FolderPlus :size="13" :stroke-width="1.5" style="margin-right:4px;" />新增資料夾
        </el-button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="sdv-loading">
      <Loader2 :size="32" class="lucide-spin" />
    </div>

    <template v-else>

      <!-- Sub-folders grid -->
      <div v-if="subFolders.length > 0" class="sdv-section">
        <div class="sdv-section-title">
          <Folder :size="13" style="margin-right:5px;opacity:0.7;" />資料夾
        </div>
        <div class="sdv-folder-grid">
          <div
            v-for="f in subFolders"
            :key="f.id"
            class="sdv-folder-card"
            @click="navigateInto(f)"
          >
            <div class="sdv-fc-color-bar" :style="{ background: f.color || '#2563eb' }"></div>
            <div class="sdv-fc-body">
              <div class="sdv-fc-icon">{{ f.icon || '📁' }}</div>
              <div class="sdv-fc-name" :title="f.name">{{ f.name }}</div>
              <div class="sdv-fc-meta">{{ folderMeta(f) }}</div>
            </div>
            <div class="sdv-fc-menu" @click.stop>
              <el-dropdown trigger="click" @command="(cmd) => handleFolderCmd(cmd, f)" placement="bottom-end">
                <button class="sdv-fc-btn">
                  <MoreHorizontal :size="14" />
                </button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="into">開啟資料夾</el-dropdown-item>
                    <el-dropdown-item command="rename">重新命名</el-dropdown-item>
                    <el-dropdown-item command="share" v-if="isAdmin">分享設定</el-dropdown-item>
                    <el-dropdown-item command="delete" divided style="color:#f56c6c;">刪除資料夾</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </div>
        </div>
      </div>

      <!-- Documents section (only when inside a folder) -->
      <div v-if="currentFolderId" class="sdv-section">
        <div class="sdv-section-title">
          <FileText :size="13" style="margin-right:5px;opacity:0.7;" />文件（{{ folderDocs.length }} 份）
        </div>
        <div v-if="docsLoading" class="sdv-loading-sm">
          <Loader2 :size="20" class="lucide-spin" />
        </div>
        <el-empty v-else-if="folderDocs.length === 0" description="尚未加入文件" :image-size="50" style="padding:24px 0;" />
        <div v-else class="sdv-doc-grid">
          <div v-for="doc in folderDocs" :key="doc.doc_id" class="sdv-doc-card" @click="emit('open-doc', doc)">
            <div class="sdv-dc-thumb" :style="{ background: fileColor(doc.file_type) }">
              <component :is="fileIcon(doc.file_type)" :size="28" style="color:rgba(255,255,255,0.9)" :stroke-width="1.5" />
              <span class="sdv-dc-badge">{{ (doc.file_type || 'FILE').toUpperCase() }}</span>
            </div>
            <div class="sdv-dc-body">
              <div class="sdv-dc-title" :title="doc.title || doc.filename">{{ doc.title || doc.filename }}</div>
              <div class="sdv-dc-meta">
                <el-tag v-if="doc.knowledge_base_name" size="small" type="info">{{ doc.knowledge_base_name }}</el-tag>
                <span>{{ doc.created_at?.slice(0, 10) }}</span>
              </div>
            </div>
            <button class="sdv-dc-remove" @click.stop="removeDocFromFolder(doc)" title="從資料夾移除">
              <X :size="13" />
            </button>
          </div>
        </div>
      </div>

      <!-- Empty root state -->
      <div v-if="!loading && subFolders.length === 0 && !currentFolderId" class="sdv-empty-root">
        <el-empty description="尚無共享資料夾" :image-size="80">
          <el-button type="primary" @click="openCreateFolder">建立第一個資料夾</el-button>
        </el-empty>
      </div>

    </template>

    <!-- ── Add Docs Dialog ─────────────────── -->
    <el-dialog v-model="addDocsVisible" title="加入文件至資料夾" width="600px" destroy-on-close>
      <el-input
        v-model="addDocsQuery"
        placeholder="搜尋文件名稱..."
        clearable
        size="small"
        style="margin-bottom:12px;"
      >
        <template #prefix><Search :size="14" /></template>
      </el-input>
      <div class="adf-list">
        <div v-if="allDocsLoading" class="sdv-loading" style="padding:40px;">
          <Loader2 :size="24" class="lucide-spin" />
        </div>
        <template v-else>
          <el-empty v-if="filteredAllDocs.length === 0" description="沒有找到文件" :image-size="40" />
          <div
            v-for="doc in filteredAllDocs"
            :key="doc.doc_id"
            class="adf-row"
            :class="{ 'adf-row--selected': selectedAddDocIds.has(doc.doc_id), 'adf-row--added': docInFolder(doc.doc_id) }"
            @click="!docInFolder(doc.doc_id) && toggleAddDoc(doc.doc_id)"
          >
            <div class="adf-check">
              <div v-if="docInFolder(doc.doc_id)" class="adf-added-mark">✓</div>
              <div v-else class="adf-check-box" :class="{ 'adf-check-box--on': selectedAddDocIds.has(doc.doc_id) }">
                <svg v-if="selectedAddDocIds.has(doc.doc_id)" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg" style="width:10px;height:10px;">
                  <path d="M2 6l3 3 5-5" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </div>
            </div>
            <div class="adf-icon" :style="{ background: fileColor(doc.file_type) }">
              <component :is="fileIcon(doc.file_type)" :size="12" style="color:white;" />
            </div>
            <div class="adf-info">
              <div class="adf-title">{{ doc.title || doc.filename }}</div>
              <div class="adf-meta">
                <el-tag v-if="doc.knowledge_base_name" size="small" type="info">{{ doc.knowledge_base_name }}</el-tag>
              </div>
            </div>
          </div>
        </template>
      </div>
      <template #footer>
        <div style="display:flex;align-items:center;gap:8px;">
          <span style="font-size:13px;color:#64748b;">已選 {{ selectedAddDocIds.size }} 份</span>
          <div style="flex:1;" />
          <el-button @click="addDocsVisible = false">取消</el-button>
          <el-button type="primary" :disabled="selectedAddDocIds.size === 0" :loading="addingDocs" @click="confirmAddDocs">
            加入 {{ selectedAddDocIds.size > 0 ? selectedAddDocIds.size + ' 份' : '' }}
          </el-button>
        </div>
      </template>
    </el-dialog>

    <!-- ── Create / Rename Folder Dialog ──── -->
    <el-dialog
      v-model="folderDialogVisible"
      :title="folderDialogMode === 'create' ? '新增資料夾' : '重新命名資料夾'"
      width="420px"
      destroy-on-close
    >
      <el-form label-width="60px" @submit.prevent="submitFolderForm">
        <el-form-item label="名稱">
          <el-input v-model="folderForm.name" placeholder="輸入資料夾名稱" autofocus clearable />
        </el-form-item>
        <el-form-item label="圖示">
          <el-input v-model="folderForm.icon" placeholder="Emoji，例如 📁 📂 🗂️" style="width:160px;" />
        </el-form-item>
        <el-form-item label="顏色">
          <div class="color-presets">
            <div
              v-for="c in COLOR_PRESETS"
              :key="c"
              class="color-dot"
              :class="{ active: folderForm.color === c }"
              :style="{ background: c }"
              @click="folderForm.color = c"
            />
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="folderDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="folderSaving" @click="submitFolderForm">
          {{ folderDialogMode === 'create' ? '建立' : '儲存' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- ── Share Dialog ─────────────────────── -->
    <FolderShareDialog v-model="shareDialogVisible" :folder="sharingFolder" />

  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import {
  HardDrive, ChevronRight, Plus, FolderPlus, Loader2, MoreHorizontal,
  FileText, FileSpreadsheet, Globe, X, Search, Folder
} from 'lucide-vue-next'
import { ElMessage, ElMessageBox } from 'element-plus'
import { foldersApi, docsApi } from '../api/index.js'
import FolderShareDialog from './FolderShareDialog.vue'

const props = defineProps({
  initialFolderId: { type: String, default: null },
  isAdmin: { type: Boolean, default: false },
})

const emit = defineEmits(['folder-navigate', 'reload-tree', 'open-doc'])

// ── Navigation stack ───────────────────────
const navStack = ref([]) // [{ id, name }, ...]
const currentFolderId = computed(() =>
  navStack.value.length > 0 ? navStack.value[navStack.value.length - 1].id : null
)

// ── Folder list ────────────────────────────
const subFolders = ref([])
const loading = ref(false)

async function loadSubFolders() {
  loading.value = true
  try {
    subFolders.value = currentFolderId.value
      ? await foldersApi.children(currentFolderId.value)
      : await foldersApi.list()
  } catch {
    subFolders.value = []
  } finally {
    loading.value = false
  }
}

// ── Documents in current folder ────────────
const folderDocs = ref([])
const docsLoading = ref(false)

async function loadFolderDocs() {
  if (!currentFolderId.value) { folderDocs.value = []; return }
  docsLoading.value = true
  try {
    folderDocs.value = await foldersApi.listDocs(currentFolderId.value)
  } catch {
    folderDocs.value = []
  } finally {
    docsLoading.value = false
  }
}

async function refresh() {
  await Promise.all([loadSubFolders(), loadFolderDocs()])
}

// ── Navigation ─────────────────────────────
async function navigateInto(folder) {
  navStack.value.push({ id: folder.id, name: folder.name })
  emit('folder-navigate', folder.id)
  await refresh()
}

function navigateRoot() {
  navStack.value = []
  emit('folder-navigate', null)
  refresh()
}

function navigateTo(index) {
  navStack.value = navStack.value.slice(0, index + 1)
  const cur = navStack.value[navStack.value.length - 1]
  emit('folder-navigate', cur.id)
  refresh()
}

// ── Watch for sidebar-driven navigation ────
watch(() => props.initialFolderId, async (newId) => {
  if (newId === null) {
    if (currentFolderId.value !== null) {
      navStack.value = []
      await refresh()
    } else {
      await refresh()
    }
  } else if (newId !== currentFolderId.value) {
    try {
      const f = await foldersApi.get(newId)
      navStack.value = [{ id: newId, name: f.name }]
    } catch {
      navStack.value = [{ id: newId, name: '資料夾' }]
    }
    await refresh()
  }
}, { immediate: true })

// ── File type helpers ──────────────────────
function fileIcon(type) {
  const t = (type || '').toLowerCase()
  if (['xls', 'xlsx', 'csv'].includes(t)) return FileSpreadsheet
  if (t === 'url') return Globe
  return FileText
}

function fileColor(type) {
  const t = (type || '').toLowerCase()
  const map = {
    pdf: '#ef4444', xlsx: '#16a34a', xls: '#16a34a', csv: '#16a34a',
    txt: '#64748b', md: '#7c3aed', html: '#f59e0b', url: '#0891b2',
    docx: '#2563eb', doc: '#2563eb',
  }
  return map[t] || '#64748b'
}

function folderMeta(f) {
  const parts = []
  if (f.doc_count > 0) parts.push(`${f.doc_count} 份文件`)
  if (f.children_count > 0) parts.push(`${f.children_count} 個子資料夾`)
  return parts.join(' · ') || '空資料夾'
}

// ── Remove doc from folder ─────────────────
async function removeDocFromFolder(doc) {
  try {
    await foldersApi.removeDoc(currentFolderId.value, doc.doc_id)
    folderDocs.value = folderDocs.value.filter(d => d.doc_id !== doc.doc_id)
    ElMessage.success('已從資料夾移除')
  } catch {
    ElMessage.error('移除失敗')
  }
}

// ── Add docs dialog ────────────────────────
const addDocsVisible = ref(false)
const addDocsQuery = ref('')
const allDocs = ref([])
const allDocsLoading = ref(false)
const selectedAddDocIds = ref(new Set())
const addingDocs = ref(false)

function docInFolder(docId) {
  return folderDocs.value.some(d => d.doc_id === docId)
}

const filteredAllDocs = computed(() => {
  const q = addDocsQuery.value.toLowerCase()
  return allDocs.value.filter(d =>
    !q || (d.title || d.filename || '').toLowerCase().includes(q)
  )
})

async function openAddDocs() {
  if (!currentFolderId.value) return
  addDocsQuery.value = ''
  selectedAddDocIds.value = new Set()
  addDocsVisible.value = true
  allDocsLoading.value = true
  try {
    const res = await docsApi.list({ page: 1, page_size: 500 })
    allDocs.value = res.docs || res.items || res || []
  } catch {
    allDocs.value = []
  } finally {
    allDocsLoading.value = false
  }
}

function toggleAddDoc(docId) {
  const s = new Set(selectedAddDocIds.value)
  if (s.has(docId)) s.delete(docId)
  else s.add(docId)
  selectedAddDocIds.value = s
}

async function confirmAddDocs() {
  if (selectedAddDocIds.value.size === 0) return
  addingDocs.value = true
  try {
    await foldersApi.addDocs(currentFolderId.value, [...selectedAddDocIds.value])
    await loadFolderDocs()
    const count = selectedAddDocIds.value.size
    addDocsVisible.value = false
    ElMessage.success(`已加入 ${count} 份文件`)
  } catch {
    ElMessage.error('加入失敗')
  } finally {
    addingDocs.value = false
  }
}

// ── Folder CRUD ────────────────────────────
const COLOR_PRESETS = [
  '#2563eb', '#7c3aed', '#db2777', '#dc2626',
  '#ea580c', '#ca8a04', '#16a34a', '#0891b2',
  '#64748b', '#1e293b',
]
const folderDialogVisible = ref(false)
const folderDialogMode = ref('create')
const folderForm = ref({ name: '', icon: '📁', color: '#2563eb' })
const folderTarget = ref(null)
const folderSaving = ref(false)

function openCreateFolder() {
  folderDialogMode.value = 'create'
  folderForm.value = { name: '', icon: '📁', color: '#2563eb' }
  folderTarget.value = null
  folderDialogVisible.value = true
}

async function submitFolderForm() {
  if (!folderForm.value.name.trim()) {
    ElMessage.warning('請輸入資料夾名稱')
    return
  }
  folderSaving.value = true
  try {
    if (folderDialogMode.value === 'create') {
      await foldersApi.create({
        name: folderForm.value.name.trim(),
        icon: folderForm.value.icon || '📁',
        color: folderForm.value.color,
        parent_id: currentFolderId.value || null,
      })
      ElMessage.success('資料夾已建立')
    } else {
      await foldersApi.update(folderTarget.value.id, {
        name: folderForm.value.name.trim(),
        icon: folderForm.value.icon || '📁',
        color: folderForm.value.color,
      })
      ElMessage.success('已更新')
    }
    folderDialogVisible.value = false
    emit('reload-tree')
    await loadSubFolders()
  } catch {
    ElMessage.error('操作失敗')
  } finally {
    folderSaving.value = false
  }
}

// ── Folder dropdown ────────────────────────
const shareDialogVisible = ref(false)
const sharingFolder = ref(null)

async function handleFolderCmd(cmd, folder) {
  if (cmd === 'into') {
    await navigateInto(folder)
  } else if (cmd === 'rename') {
    folderDialogMode.value = 'rename'
    folderForm.value = {
      name: folder.name,
      icon: folder.icon || '📁',
      color: folder.color || '#2563eb',
    }
    folderTarget.value = folder
    folderDialogVisible.value = true
  } else if (cmd === 'share') {
    sharingFolder.value = folder
    shareDialogVisible.value = true
  } else if (cmd === 'delete') {
    try {
      await ElMessageBox.confirm(
        `確定要刪除「${folder.name}」？此操作無法復原。`,
        '刪除資料夾',
        { type: 'warning', confirmButtonText: '刪除', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger' }
      )
      await foldersApi.delete(folder.id)
      ElMessage.success('已刪除')
      emit('reload-tree')
      await loadSubFolders()
    } catch {
      // cancelled
    }
  }
}
</script>

<style scoped>
.sdv-wrap {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow-y: auto;
  min-height: 0;
}

/* ── Header ── */
.sdv-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 20px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-shrink: 0;
  flex-wrap: wrap;
  gap: 8px;
}

.sdv-breadcrumb {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

.sdv-hd-icon {
  color: #64748b;
  margin-right: 2px;
  flex-shrink: 0;
}

.sdv-bc-root {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--el-color-primary, #2563eb);
  font-size: 14px;
  font-weight: 600;
  padding: 3px 6px;
  border-radius: 5px;
  transition: background 0.15s;
}
.sdv-bc-root:hover { background: var(--el-color-primary-light-9); }

.sdv-bc-sep { color: #94a3b8; flex-shrink: 0; }

.sdv-bc-item {
  background: none;
  border: none;
  cursor: pointer;
  color: #475569;
  font-size: 14px;
  font-weight: 500;
  padding: 3px 6px;
  border-radius: 5px;
  transition: background 0.15s, color 0.15s;
}
.sdv-bc-item:hover { background: #f1f5f9; color: #1e293b; }
.sdv-bc-item.active { color: #1e293b; cursor: default; }
.sdv-bc-item.active:hover { background: none; }

.sdv-actions { display: flex; gap: 8px; align-items: center; flex-shrink: 0; }

/* ── Loading ── */
.sdv-loading {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 80px 20px;
  color: #94a3b8;
}
.sdv-loading-sm {
  display: flex;
  justify-content: center;
  padding: 24px;
  color: #94a3b8;
}

/* ── Section ── */
.sdv-section { padding: 16px 20px; }
.sdv-section-title {
  display: flex;
  align-items: center;
  font-size: 11px;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 14px;
}

/* ── Folder grid ── */
.sdv-folder-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(148px, 1fr));
  gap: 12px;
}

.sdv-folder-card {
  position: relative;
  background: var(--el-bg-color, #fff);
  border: 1px solid var(--el-border-color, #e2e8f0);
  border-radius: 10px;
  overflow: hidden;
  cursor: pointer;
  transition: border-color 0.18s, box-shadow 0.18s, transform 0.12s;
  user-select: none;
}
.sdv-folder-card:hover {
  border-color: var(--el-color-primary, #2563eb);
  box-shadow: 0 4px 16px rgba(37, 99, 235, 0.12);
  transform: translateY(-2px);
}

.sdv-fc-color-bar { height: 4px; width: 100%; flex-shrink: 0; }

.sdv-fc-body {
  padding: 16px 14px 14px;
  text-align: center;
}

.sdv-fc-icon {
  font-size: 34px;
  line-height: 1;
  margin-bottom: 10px;
}

.sdv-fc-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary, #1e293b);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 5px;
}

.sdv-fc-meta {
  font-size: 11px;
  color: #94a3b8;
  line-height: 1.4;
}

.sdv-fc-menu {
  position: absolute;
  top: 10px;
  right: 8px;
  opacity: 0;
  transition: opacity 0.15s;
}
.sdv-folder-card:hover .sdv-fc-menu { opacity: 1; }

.sdv-fc-btn {
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  cursor: pointer;
  padding: 3px 5px;
  display: flex;
  align-items: center;
  color: #475569;
  transition: background 0.15s, border-color 0.15s;
  backdrop-filter: blur(4px);
}
.sdv-fc-btn:hover { background: #fff; border-color: #94a3b8; }

/* ── Document card grid ── */
.sdv-doc-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(148px, 1fr));
  gap: 12px;
}
.sdv-doc-card {
  position: relative;
  background: var(--el-bg-color, #fff);
  border: 1px solid var(--el-border-color, #e2e8f0);
  border-radius: 10px;
  overflow: hidden;
  cursor: pointer;
  transition: border-color 0.18s, box-shadow 0.18s;
}
.sdv-doc-card:hover {
  border-color: var(--el-color-primary, #2563eb);
  box-shadow: 0 4px 16px rgba(37, 99, 235, 0.12);
  transform: translateY(-1px);
}
.sdv-dc-thumb {
  height: 86px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
.sdv-dc-badge {
  font-size: 10px;
  font-weight: 700;
  color: rgba(255,255,255,0.9);
  background: rgba(0,0,0,0.22);
  padding: 1px 7px;
  border-radius: 6px;
  letter-spacing: 0.05em;
}
.sdv-dc-body {
  padding: 10px 12px 10px;
}
.sdv-dc-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-primary, #1e293b);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 5px;
}
.sdv-dc-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  font-size: 11px;
  color: #94a3b8;
}
.sdv-dc-remove {
  position: absolute;
  top: 8px;
  right: 8px;
  background: rgba(255,255,255,0.9);
  border: 1px solid rgba(0,0,0,0.1);
  border-radius: 5px;
  cursor: pointer;
  padding: 3px 5px;
  display: flex;
  align-items: center;
  color: #94a3b8;
  opacity: 0;
  transition: opacity 0.15s, color 0.15s, background 0.15s;
}
.sdv-doc-card:hover .sdv-dc-remove { opacity: 1; }
.sdv-dc-remove:hover { color: #f56c6c; background: #fff1f1; }

@media (max-width: 768px) {
  .sdv-folder-grid,
  .sdv-doc-grid {
    grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
    gap: 10px;
  }
  .sdv-section { padding: 12px 14px; }
  .sdv-header { padding: 10px 14px; flex-wrap: wrap; gap: 8px; }
}

/* ── Empty root ── */
.sdv-empty-root {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 80px 20px;
}

/* ── Add Docs Dialog ── */
.adf-list {
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
}

.adf-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 14px;
  cursor: pointer;
  transition: background 0.12s;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.adf-row:last-child { border-bottom: none; }
.adf-row:hover:not(.adf-row--added) { background: var(--el-fill-color-light); }
.adf-row--added { opacity: 0.5; cursor: default; }
.adf-row--selected { background: var(--el-color-primary-light-9); }

.adf-check { flex-shrink: 0; }

.adf-check-box {
  width: 16px;
  height: 16px;
  border-radius: 4px;
  border: 1.5px solid var(--el-border-color);
  display: flex;
  align-items: center;
  justify-content: center;
  background: #fff;
  transition: border-color 0.15s, background 0.15s;
}
.adf-check-box--on {
  background: var(--el-color-primary);
  border-color: var(--el-color-primary);
}

.adf-added-mark {
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: var(--el-color-success);
  font-weight: bold;
}

.adf-icon {
  width: 26px;
  height: 26px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.adf-info { flex: 1; min-width: 0; }
.adf-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.adf-meta { margin-top: 3px; }

/* ── Color presets ── */
.color-presets { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 4px; }
.color-dot {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  cursor: pointer;
  border: 2.5px solid transparent;
  transition: border-color 0.15s, transform 0.12s;
}
.color-dot:hover { transform: scale(1.2); }
.color-dot.active { border-color: #1e293b; transform: scale(1.15); }
</style>
