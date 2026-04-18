import sys
content = r'''<template>
  <div class="docs-root">
    <!-- KB Sidebar -->
    <aside class="kb-sidebar">
      <div class="kb-sidebar-header">
        <span class="kb-sidebar-title">知識庫</span>
        <el-button circle size="small" :icon="Plus" @click="openKbDialog(null)" />
      </div>

      <ul class="kb-list">
        <li
          class="kb-item"
          :class="{ active: selectedKbId === null }"
          @click="selectKb(null)"
        >
          <span class="kb-icon">&#x1F4CB;</span>
          <span class="kb-name">全部文件</span>
          <span class="kb-count">{{ totalDocCount }}</span>
        </li>
        <li
          v-for="kb in kbs"
          :key="kb.id"
          class="kb-item"
          :class="{ active: selectedKbId === kb.id }"
          @click="selectKb(kb.id)"
        >
          <span class="kb-icon">{{ kb.icon }}</span>
          <span class="kb-name">{{ kb.name }}</span>
          <span class="kb-count">{{ kb.doc_count }}</span>
          <el-dropdown @command="(cmd) => handleKbCommand(cmd, kb)" @click.stop trigger="click">
            <el-icon class="kb-more"><MoreFilled /></el-icon>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="edit">編輯</el-dropdown-item>
                <el-dropdown-item command="delete" divided>刪除</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </li>
      </ul>

      <div class="kb-sidebar-footer">
        <el-button size="small" plain style="width:100%;" :icon="Plus" @click="openKbDialog(null)">
          新建知識庫
        </el-button>
      </div>
    </aside>

    <!-- Main Content -->
    <main class="docs-main" :class="{ 'panel-open': !!panelDoc }">

      <!-- Toolbar -->
      <div class="docs-toolbar">
        <div class="breadcrumb">
          <span>文件管理</span>
          <span v-if="selectedKb" class="bc-sep">/</span>
          <span v-if="selectedKb" class="bc-kb">{{ selectedKb.icon }} {{ selectedKb.name }}</span>
        </div>

        <div class="search-wrap">
          <el-input
            v-model="searchQuery"
            placeholder="AI 語意搜尋文件..."
            clearable
            @keyup.enter="doAiSearch"
            @clear="clearSearch"
            class="search-input"
          >
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <el-button
            type="primary"
            :loading="searching"
            @click="doAiSearch"
            :disabled="!searchQuery.trim()"
          >搜尋</el-button>
        </div>

        <div class="toolbar-right">
          <el-upload
            :http-request="handleUpload"
            :show-file-list="false"
            accept=".pdf,.docx,.xlsx,.txt,.md,.html,.csv"
            :disabled="uploading"
          >
            <el-button type="primary" :loading="uploading" :icon="Upload">上傳文件</el-button>
          </el-upload>

          <el-button-group class="view-toggle">
            <el-button
              v-for="m in viewModes"
              :key="m.value"
              :type="viewMode === m.value ? 'primary' : ''"
              @click="switchView(m.value)"
              :title="m.label"
            >
              <el-icon><component :is="m.icon" /></el-icon>
            </el-button>
          </el-button-group>
        </div>
      </div>

      <!-- Upload feedback -->
      <el-alert v-if="uploadError" type="error" :description="uploadError" show-icon closable
        @close="uploadError=''" style="margin:0 20px 12px;" />
      <el-alert v-if="uploadSuccess" type="success" description="文件上傳成功，後台處理中..." show-icon closable
        @close="uploadSuccess=false" style="margin:0 20px 12px;" />

      <!-- Search Results Mode -->
      <div v-if="searchMode" class="search-results-wrap">
        <div class="search-results-header">
          <span>AI 搜尋結果：「{{ lastQuery }}」</span>
          <span class="result-count">共 {{ searchResults.length }} 筆</span>
          <el-button link :icon="Close" @click="clearSearch">清除搜尋</el-button>
        </div>
        <div v-if="searching" class="loading-center">
          <el-icon class="is-loading" :size="32"><Loading /></el-icon>
          <p>語意搜尋中...</p>
        </div>
        <div v-else-if="searchResults.length === 0" class="empty-state">
          <el-empty description="沒有找到相關文件" />
        </div>
        <div v-else class="search-result-list">
          <div
            v-for="r in searchResults"
            :key="r.doc_id"
            class="search-result-card"
            @click="openPanelById(r.doc_id, r)"
          >
            <div class="src-thumb" :style="{ background: fileColor(r.file_type) }">
              <el-icon :size="22" color="white"><component :is="fileIcon(r.file_type)" /></el-icon>
            </div>
            <div class="src-body">
              <div class="src-title">{{ r.title }}</div>
              <div class="src-snippet">{{ r.snippet }}</div>
              <div class="src-meta">
                <el-tag v-if="r.knowledge_base_name" size="small" type="info">{{ r.knowledge_base_name }}</el-tag>
                <span class="score-badge">相似度 {{ (r.score * 100).toFixed(0) }}%</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Normal Content Area -->
      <div v-else class="docs-content">

        <!-- Grid View -->
        <div v-if="viewMode === 'grid'" class="grid-view">
          <div v-if="loading" class="loading-center">
            <el-icon class="is-loading" :size="32"><Loading /></el-icon>
          </div>
          <el-empty v-else-if="docs.length === 0" description="此知識庫尚無文件，請上傳第一份文件" style="margin-top:80px;" />
          <div v-else class="grid-cards">
            <div
              v-for="doc in docs"
              :key="doc.doc_id"
              class="doc-card"
              @click="openPanel(doc)"
            >
              <div class="card-thumb" :style="{ background: fileColor(doc.file_type) }">
                <el-icon :size="36" color="white"><component :is="fileIcon(doc.file_type)" /></el-icon>
                <span class="file-badge">{{ (doc.file_type || 'FILE').toUpperCase() }}</span>
              </div>
              <div class="card-body">
                <div class="card-title" :title="doc.title">{{ doc.title }}</div>
                <div class="card-meta">
                  <span class="status-dot" :class="'dot-' + doc.status" />
                  <span class="status-text">{{ statusLabel(doc.status) }}</span>
                  <span class="chunk-count">{{ doc.chunk_count }} chunks</span>
                </div>
                <div class="card-kb" v-if="doc.knowledge_base_name">
                  <el-tag size="small" type="info">{{ doc.knowledge_base_name }}</el-tag>
                </div>
                <div class="card-date">{{ doc.created_at?.slice(0, 10) }}</div>
              </div>
              <div class="card-actions" @click.stop>
                <el-dropdown @command="(cmd) => handleDocCommand(cmd, doc)">
                  <el-button link size="small" :icon="MoreFilled" />
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="detail">查看詳情</el-dropdown-item>
                      <el-dropdown-item command="move">移至知識庫</el-dropdown-item>
                      <el-dropdown-item command="delete" divided>刪除</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </div>
          </div>
        </div>

        <!-- Table View -->
        <div v-else-if="viewMode === 'table'" class="table-view">
          <el-table
            :data="docs"
            v-loading="loading"
            style="width:100%"
            stripe
            highlight-current-row
            @row-click="openPanel"
          >
            <el-table-column label="標題" prop="title" min-width="200" show-overflow-tooltip />
            <el-table-column label="知識庫" width="130">
              <template #default="{ row }">
                <el-tag v-if="row.knowledge_base_name" size="small" type="info">
                  {{ row.knowledge_base_name }}
                </el-tag>
                <span v-else style="color:#bbb;font-size:12px;">未分類</span>
              </template>
            </el-table-column>
            <el-table-column label="類型" prop="file_type" width="70" align="center">
              <template #default="{ row }">
                <span style="font-size:12px;font-weight:600;color:#64748b">
                  {{ (row.file_type || '—').toUpperCase() }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="狀態" width="100" align="center">
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="Chunks" prop="chunk_count" width="80" align="center" />
            <el-table-column label="建立時間" width="140">
              <template #default="{ row }">{{ row.created_at?.slice(0, 16).replace('T', ' ') }}</template>
            </el-table-column>
            <el-table-column label="操作" width="130" align="center">
              <template #default="{ row }">
                <el-button size="small" link :icon="View" @click.stop="openPanel(row)">詳情</el-button>
                <el-popconfirm title="確定刪除此文件？" @confirm="deleteDoc(row.doc_id)">
                  <template #reference>
                    <el-button size="small" link type="danger" :icon="Delete" @click.stop />
                  </template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- Node View -->
        <div v-else-if="viewMode === 'node'" class="node-view">
          <div v-if="cyLoading" class="loading-center">
            <el-icon class="is-loading" :size="32"><Loading /></el-icon>
            <p>建立節點圖...</p>
          </div>
          <div ref="cyContainer" class="cy-container" />
          <div class="cy-legend">
            <div v-for="kb in kbs" :key="kb.id" class="legend-item">
              <span class="legend-dot" :style="{ background: kb.color }" />
              <span>{{ kb.icon }} {{ kb.name }}</span>
            </div>
            <div class="legend-item">
              <span class="legend-dot" style="background:#94a3b8" />
              <span>未分類</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Pagination -->
      <div v-if="!searchMode && viewMode !== 'node'" class="pagination-bar">
        <el-pagination
          v-model:current-page="page"
          :page-size="PAGE_SIZE"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="loadDocs"
        />
      </div>
    </main>

    <!-- Right Detail Panel -->
    <transition name="panel-slide">
      <aside v-if="panelDoc" class="detail-panel">
        <div class="panel-header">
          <div class="panel-thumb" :style="{ background: fileColor(panelDoc.file_type) }">
            <el-icon :size="18" color="white"><component :is="fileIcon(panelDoc.file_type)" /></el-icon>
          </div>
          <div class="panel-title-wrap">
            <div class="panel-title" :title="panelDoc.title">{{ panelDoc.title }}</div>
            <el-tag :type="statusTagType(panelDoc.status)" size="small">{{ statusLabel(panelDoc.status) }}</el-tag>
          </div>
          <el-button link :icon="Close" @click="closePanel" />
        </div>

        <el-tabs v-model="panelTab" class="panel-tabs" @tab-click="onPanelTabChange">

          <el-tab-pane label="資訊" name="info">
            <div class="info-section">
              <div class="info-row">
                <span class="info-label">知識庫</span>
                <span class="info-val">
                  {{ panelDoc.knowledge_base_name || '未分類' }}
                  <el-button link size="small" @click="openMoveDialog(panelDoc)">移動</el-button>
                </span>
              </div>
              <div class="info-row">
                <span class="info-label">檔案類型</span>
                <span class="info-val">{{ (panelDoc.file_type || '—').toUpperCase() }}</span>
              </div>
              <div class="info-row">
                <span class="info-label">Chunks 數量</span>
                <span class="info-val">{{ panelDoc.chunk_count }}</span>
              </div>
              <div class="info-row">
                <span class="info-label">建立時間</span>
                <span class="info-val">{{ panelDoc.created_at?.slice(0, 19).replace('T', ' ') }}</span>
              </div>
              <div v-if="panelDoc.error_message" class="info-row">
                <span class="info-label" style="color:#ef4444">錯誤訊息</span>
                <span class="info-val" style="color:#ef4444">{{ panelDoc.error_message }}</span>
              </div>
            </div>
            <div class="panel-actions">
              <el-button type="danger" plain size="small" :icon="Delete"
                @click="deleteDoc(panelDoc.doc_id)">刪除文件</el-button>
            </div>
          </el-tab-pane>

          <el-tab-pane name="chunks">
            <template #label>
              Chunks
              <el-badge v-if="chunksTotal > 0" :value="chunksTotal" :max="999" class="chunk-badge" />
            </template>
            <div v-if="chunksLoading" class="loading-center">
              <el-icon class="is-loading" :size="28"><Loading /></el-icon>
            </div>
            <template v-else>
              <div class="chunks-toolbar">
                <el-tag type="info" size="small">共 {{ chunksTotal }} 個</el-tag>
                <el-pagination
                  v-if="chunksTotal > CHUNK_PAGE_SIZE"
                  v-model:current-page="chunkPage"
                  :page-size="CHUNK_PAGE_SIZE"
                  :total="chunksTotal"
                  layout="prev, pager, next"
                  small
                  @current-change="loadChunks"
                />
              </div>
              <el-empty v-if="chunks.length === 0" description="尚無 Chunks" />
              <el-scrollbar class="chunks-scroll">
                <div v-for="chunk in chunks" :key="chunk.id" class="chunk-card">
                  <div class="chunk-header">
                    <el-tag size="small" type="primary">#{{ chunk.index }}</el-tag>
                    <el-tag v-if="chunk.page_number != null" size="small" type="info">
                      第 {{ chunk.page_number }} 頁
                    </el-tag>
                    <span class="chunk-len">{{ chunk.content.length }} 字元</span>
                  </div>
                  <p class="chunk-content">{{ chunk.content }}</p>
                </div>
              </el-scrollbar>
            </template>
          </el-tab-pane>

          <el-tab-pane label="完整內容" name="content">
            <div v-if="contentLoading" class="loading-center">
              <el-icon class="is-loading" :size="28"><Loading /></el-icon>
              <p>載入完整內容...</p>
            </div>
            <el-scrollbar v-else class="content-scroll">
              <pre class="full-content">{{ fullContent || '（此文件尚無內容）' }}</pre>
            </el-scrollbar>
          </el-tab-pane>

        </el-tabs>
      </aside>
    </transition>

    <!-- KB Dialog -->
    <el-dialog v-model="showKbDialog" :title="editKb ? '編輯知識庫' : '新建知識庫'" width="420px" destroy-on-close>
      <el-form :model="kbForm" label-width="70px">
        <el-form-item label="名稱">
          <el-input v-model="kbForm.name" placeholder="知識庫名稱" maxlength="50" />
        </el-form-item>
        <el-form-item label="圖示">
          <el-input v-model="kbForm.icon" placeholder="📚" maxlength="4" style="width:80px;margin-right:8px;" />
          <span style="font-size:24px;">{{ kbForm.icon }}</span>
        </el-form-item>
        <el-form-item label="色彩">
          <div class="color-swatches">
            <div
              v-for="c in COLOR_PRESETS"
              :key="c"
              class="swatch"
              :style="{ background: c, outline: kbForm.color === c ? '3px solid #1e293b' : '' }"
              @click="kbForm.color = c"
            />
          </div>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="kbForm.description" type="textarea" :rows="2" placeholder="選填說明" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showKbDialog = false">取消</el-button>
        <el-button type="primary" @click="saveKb" :loading="kbSaving">儲存</el-button>
      </template>
    </el-dialog>

    <!-- Move to KB Dialog -->
    <el-dialog v-model="showMoveDialog" title="移至知識庫" width="380px" destroy-on-close>
      <el-radio-group v-model="moveTargetKbId" style="display:flex;flex-direction:column;gap:10px;">
        <el-radio :label="null">
          <span>&#x1F4CB; 未分類</span>
        </el-radio>
        <el-radio v-for="kb in kbs" :key="kb.id" :label="kb.id">
          <span>{{ kb.icon }} {{ kb.name }}</span>
        </el-radio>
      </el-radio-group>
      <template #footer>
        <el-button @click="showMoveDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmMove" :loading="moving">確認移動</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import {
  Upload, View, Delete, Loading, Search, Plus,
  MoreFilled, Close, Grid, List, Share,
  Document as DocIcon, Memo, Files
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { docsApi, kbApi } from '../api/index.js'

const PAGE_SIZE = 24
const CHUNK_PAGE_SIZE = 50
const COLOR_PRESETS = [
  '#2563eb', '#7c3aed', '#db2777', '#dc2626',
  '#ea580c', '#ca8a04', '#16a34a', '#0891b2',
  '#64748b', '#1e293b',
]
const viewModes = [
  { value: 'grid', label: 'Grid 卡片', icon: 'Grid' },
  { value: 'table', label: '表格', icon: 'List' },
  { value: 'node', label: '節點圖', icon: 'Share' },
]

const kbs = ref([])
const selectedKbId = ref(null)
const selectedKb = computed(() => kbs.value.find(k => k.id === selectedKbId.value) || null)
const totalDocCount = computed(() => kbs.value.reduce((s, k) => s + k.doc_count, 0))

const docs = ref([])
const loading = ref(false)
const page = ref(1)
const total = ref(0)

const viewMode = ref('grid')

const uploading = ref(false)
const uploadError = ref('')
const uploadSuccess = ref(false)

const searchQuery = ref('')
const searchMode = ref(false)
const searching = ref(false)
const searchResults = ref([])
const lastQuery = ref('')

const panelDoc = ref(null)
const panelTab = ref('info')
const chunks = ref([])
const chunksTotal = ref(0)
const chunkPage = ref(1)
const chunksLoading = ref(false)
const fullContent = ref('')
const contentLoading = ref(false)

const cyContainer = ref(null)
const cyLoading = ref(false)
let cyInstance = null

const showKbDialog = ref(false)
const editKb = ref(null)
const kbSaving = ref(false)
const kbForm = ref({ name: '', icon: '📚', color: '#2563eb', description: '' })

const showMoveDialog = ref(false)
const moveTargetDoc = ref(null)
const moveTargetKbId = ref(null)
const moving = ref(false)

onMounted(async () => {
  await loadKbs()
  await loadDocs()
})

onUnmounted(() => {
  if (cyInstance) { cyInstance.destroy(); cyInstance = null }
})

async function loadKbs() {
  try {
    kbs.value = await kbApi.list()
  } catch (e) {
    console.error(e)
  }
}

function selectKb(id) {
  selectedKbId.value = id
  page.value = 1
  searchMode.value = false
  loadDocs()
}

function openKbDialog(kb) {
  editKb.value = kb
  if (kb) {
    kbForm.value = { name: kb.name, icon: kb.icon, color: kb.color, description: kb.description || '' }
  } else {
    kbForm.value = { name: '', icon: '📚', color: '#2563eb', description: '' }
  }
  showKbDialog.value = true
}

async function saveKb() {
  if (!kbForm.value.name.trim()) return ElMessage.warning('請輸入知識庫名稱')
  kbSaving.value = true
  try {
    if (editKb.value) {
      await kbApi.update(editKb.value.id, kbForm.value)
    } else {
      await kbApi.create(kbForm.value)
    }
    showKbDialog.value = false
    await loadKbs()
    ElMessage.success(editKb.value ? '更新成功' : '知識庫建立成功')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    kbSaving.value = false
  }
}

async function handleKbCommand(cmd, kb) {
  if (cmd === 'edit') {
    openKbDialog(kb)
  } else if (cmd === 'delete') {
    try {
      await ElMessageBox.confirm(
        `確定刪除知識庫「${kb.name}」？文件不會被刪除，但會移出此知識庫。`,
        '刪除知識庫',
        { type: 'warning', confirmButtonText: '確定刪除', cancelButtonText: '取消' }
      )
      await kbApi.delete(kb.id)
      if (selectedKbId.value === kb.id) selectedKbId.value = null
      await loadKbs()
      await loadDocs()
      ElMessage.success('知識庫已刪除')
    } catch {}
  }
}

async function loadDocs() {
  loading.value = true
  try {
    const params = { limit: PAGE_SIZE, offset: (page.value - 1) * PAGE_SIZE }
    if (selectedKbId.value) params.kb_id = selectedKbId.value
    const data = await docsApi.list(params)
    docs.value = data
    if (data.length === PAGE_SIZE) {
      total.value = page.value * PAGE_SIZE + 1
    } else {
      total.value = (page.value - 1) * PAGE_SIZE + data.length
    }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function handleUpload({ file }) {
  uploading.value = true
  uploadError.value = ''
  uploadSuccess.value = false
  try {
    await docsApi.upload(file, selectedKbId.value)
    uploadSuccess.value = true
    await loadKbs()
    await loadDocs()
  } catch (e) {
    uploadError.value = e.message
  } finally {
    uploading.value = false
  }
}

async function deleteDoc(docId) {
  try {
    await ElMessageBox.confirm('確定刪除此文件？此操作無法復原。', '刪除文件', {
      type: 'warning', confirmButtonText: '確定刪除', cancelButtonText: '取消',
    })
    await docsApi.delete(docId)
    if (panelDoc.value?.doc_id === docId) closePanel()
    await loadKbs()
    await loadDocs()
    ElMessage.success('文件已刪除')
  } catch {}
}

function handleDocCommand(cmd, doc) {
  if (cmd === 'detail') openPanel(doc)
  else if (cmd === 'move') openMoveDialog(doc)
  else if (cmd === 'delete') deleteDoc(doc.doc_id)
}

function switchView(mode) {
  viewMode.value = mode
  if (mode === 'node') {
    nextTick(() => initCytoscape())
  } else {
    if (cyInstance) { cyInstance.destroy(); cyInstance = null }
  }
}

async function doAiSearch() {
  if (!searchQuery.value.trim()) return
  searching.value = true
  searchMode.value = true
  lastQuery.value = searchQuery.value
  searchResults.value = []
  try {
    searchResults.value = await docsApi.aiSearch(searchQuery.value, selectedKbId.value)
  } catch (e) {
    ElMessage.error('搜尋失敗：' + e.message)
  } finally {
    searching.value = false
  }
}

function clearSearch() {
  searchMode.value = false
  searchQuery.value = ''
  searchResults.value = []
}

function openPanel(doc) {
  panelDoc.value = doc
  panelTab.value = 'info'
  chunks.value = []
  chunksTotal.value = 0
  fullContent.value = ''
}

function openPanelById(docId, partialDoc) {
  panelDoc.value = { ...partialDoc, doc_id: docId }
  panelTab.value = 'info'
  chunks.value = []
  chunksTotal.value = 0
  fullContent.value = ''
}

function closePanel() {
  panelDoc.value = null
}

async function onPanelTabChange({ paneName }) {
  if (!panelDoc.value) return
  if (paneName === 'chunks' && chunks.value.length === 0) {
    await loadChunks()
  } else if (paneName === 'content' && !fullContent.value) {
    await loadFullContent()
  }
}

async function loadChunks() {
  if (!panelDoc.value) return
  chunksLoading.value = true
  try {
    const res = await docsApi.getChunks(panelDoc.value.doc_id, {
      limit: CHUNK_PAGE_SIZE,
      offset: (chunkPage.value - 1) * CHUNK_PAGE_SIZE,
    })
    chunks.value = res.chunks || []
    chunksTotal.value = res.total || 0
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    chunksLoading.value = false
  }
}

async function loadFullContent() {
  if (!panelDoc.value) return
  contentLoading.value = true
  try {
    const res = await docsApi.getChunks(panelDoc.value.doc_id, { limit: 500, offset: 0 })
    fullContent.value = (res.chunks || []).map(c => c.content).join('\n\n---\n\n')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    contentLoading.value = false
  }
}

function openMoveDialog(doc) {
  moveTargetDoc.value = doc
  moveTargetKbId.value = doc.knowledge_base_id || null
  showMoveDialog.value = true
}

async function confirmMove() {
  if (!moveTargetDoc.value) return
  moving.value = true
  try {
    await docsApi.moveToKb(moveTargetDoc.value.doc_id, moveTargetKbId.value)
    showMoveDialog.value = false
    await loadKbs()
    await loadDocs()
    if (panelDoc.value?.doc_id === moveTargetDoc.value.doc_id) {
      const updated = docs.value.find(d => d.doc_id === moveTargetDoc.value.doc_id)
      if (updated) panelDoc.value = updated
    }
    ElMessage.success('文件已移動')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    moving.value = false
  }
}

async function initCytoscape() {
  if (!cyContainer.value || docs.value.length === 0) return
  cyLoading.value = true
  try {
    const cytoscape = (await import('cytoscape')).default
    if (cyInstance) { cyInstance.destroy(); cyInstance = null }

    const elements = []
    kbs.value.forEach(kb => {
      elements.push({
        data: { id: `kb-${kb.id}`, label: `${kb.icon} ${kb.name}`, kbColor: kb.color },
        classes: 'kb-parent',
      })
    })
    elements.push({
      data: { id: 'kb-none', label: '未分類', kbColor: '#94a3b8' },
      classes: 'kb-parent',
    })
    docs.value.forEach(doc => {
      const parentId = doc.knowledge_base_id ? `kb-${doc.knowledge_base_id}` : 'kb-none'
      const kbColor = doc.knowledge_base_id
        ? (kbs.value.find(k => k.id === doc.knowledge_base_id)?.color || '#2563eb')
        : '#94a3b8'
      elements.push({
        data: {
          id: doc.doc_id,
          label: doc.title.length > 16 ? doc.title.slice(0, 15) + '...' : doc.title,
          parent: parentId,
          kbColor,
          doc,
        },
        classes: `doc-node status-${doc.status}`,
      })
    })

    cyInstance = cytoscape({
      container: cyContainer.value,
      elements,
      style: [
        {
          selector: '.kb-parent',
          style: {
            'background-color': 'data(kbColor)',
            'background-opacity': 0.07,
            'border-width': 2,
            'border-color': 'data(kbColor)',
            'border-opacity': 0.5,
            label: 'data(label)',
            'text-valign': 'top',
            'text-halign': 'center',
            'font-size': '13px',
            'font-weight': 600,
            color: '#1e293b',
            'text-margin-y': -6,
          },
        },
        {
          selector: '.doc-node',
          style: {
            'background-color': 'data(kbColor)',
            'background-opacity': 0.85,
            label: 'data(label)',
            color: '#1e293b',
            'font-size': '10px',
            'text-wrap': 'wrap',
            'text-max-width': '70px',
            'text-valign': 'bottom',
            'text-margin-y': 4,
            width: 50,
            height: 50,
            'border-width': 2,
            'border-color': '#fff',
          },
        },
        { selector: '.status-failed', style: { 'background-color': '#ef4444' } },
        { selector: '.status-processing', style: { 'background-color': '#eab308' } },
        { selector: '.status-pending', style: { 'background-color': '#94a3b8' } },
        { selector: ':selected', style: { 'border-width': 3, 'border-color': '#1e293b' } },
      ],
      layout: {
        name: 'cose',
        padding: 40,
        nodeRepulsion: 8000,
        idealEdgeLength: 100,
        animate: true,
        animationDuration: 500,
      },
      wheelSensitivity: 0.3,
    })

    cyInstance.on('tap', 'node.doc-node', (evt) => {
      const doc = evt.target.data('doc')
      if (doc) openPanel(doc)
    })
  } catch (e) {
    console.error('Cytoscape init error', e)
  } finally {
    cyLoading.value = false
  }
}

watch(docs, () => {
  if (viewMode.value === 'node') nextTick(() => initCytoscape())
})

function fileIcon(type) {
  const map = { pdf: 'Memo', docx: 'Document', xlsx: 'Files', csv: 'Files', txt: 'Document', md: 'Document', html: 'Memo' }
  return map[type] || 'Document'
}

function fileColor(type) {
  const map = { pdf: '#ef4444', docx: '#2563eb', xlsx: '#16a34a', csv: '#16a34a', txt: '#64748b', md: '#7c3aed', html: '#ea580c' }
  return map[type] || '#94a3b8'
}

function statusLabel(s) {
  return { ready: '完成', processing: '處理中', pending: '等待', failed: '失敗', done: '完成' }[s] || s
}

function statusTagType(s) {
  return { ready: 'success', done: 'success', processing: 'warning', pending: 'info', failed: 'danger' }[s] || 'info'
}
</script>

<style scoped>
.docs-root {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: #f8fafc;
  font-family: -apple-system, 'Microsoft JhengHei', sans-serif;
}

.kb-sidebar {
  width: 220px;
  min-width: 220px;
  background: #f1f5f9;
  border-right: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.kb-sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 16px 8px;
}
.kb-sidebar-title {
  font-size: 12px;
  font-weight: 700;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.kb-list {
  list-style: none;
  padding: 4px 8px;
  margin: 0;
  flex: 1;
  overflow-y: auto;
}
.kb-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: #475569;
  transition: background 0.15s;
  position: relative;
}
.kb-item:hover { background: #e2e8f0; }
.kb-item.active { background: #dbeafe; color: #1d4ed8; font-weight: 600; }
.kb-icon { font-size: 15px; flex-shrink: 0; }
.kb-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kb-count {
  font-size: 11px;
  background: #e2e8f0;
  color: #64748b;
  padding: 1px 7px;
  border-radius: 10px;
}
.kb-item.active .kb-count { background: #bfdbfe; color: #1d4ed8; }
.kb-more { opacity: 0; transition: opacity 0.15s; color: #94a3b8; cursor: pointer; }
.kb-item:hover .kb-more { opacity: 1; }
.kb-sidebar-footer { padding: 12px; border-top: 1px solid #e2e8f0; }

.docs-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: margin-right 0.3s ease;
  min-width: 0;
}
.docs-main.panel-open { margin-right: 380px; }

.docs-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  background: #fff;
  border-bottom: 1px solid #e2e8f0;
  flex-wrap: wrap;
  flex-shrink: 0;
}
.breadcrumb {
  font-size: 15px;
  font-weight: 600;
  color: #1e293b;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}
.bc-sep { color: #94a3b8; }
.bc-kb { color: #2563eb; }
.search-wrap {
  flex: 1;
  min-width: 220px;
  max-width: 460px;
  display: flex;
  gap: 8px;
}
.search-input { flex: 1; }
.toolbar-right { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.view-toggle { overflow: hidden; }

.docs-content { flex: 1; overflow-y: auto; padding: 20px; }

.grid-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(175px, 1fr));
  gap: 16px;
}
.doc-card {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  overflow: hidden;
  cursor: pointer;
  transition: box-shadow 0.15s, transform 0.1s;
  position: relative;
  display: flex;
  flex-direction: column;
}
.doc-card:hover {
  box-shadow: 0 4px 16px rgba(0,0,0,0.1);
  transform: translateY(-1px);
}
.card-thumb {
  height: 96px;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
}
.file-badge {
  position: absolute;
  bottom: 6px;
  right: 6px;
  background: rgba(0,0,0,0.32);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  padding: 2px 5px;
  border-radius: 3px;
}
.card-body { padding: 10px 12px; flex: 1; }
.card-title {
  font-size: 13px;
  font-weight: 600;
  color: #1e293b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: 5px;
}
.card-meta {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: #64748b;
  margin-bottom: 4px;
}
.status-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.dot-ready, .dot-done { background: #22c55e; }
.dot-processing { background: #eab308; animation: blink 1.2s infinite; }
.dot-pending { background: #94a3b8; }
.dot-failed { background: #ef4444; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.3} }
.chunk-count { margin-left: auto; }
.card-kb { margin-bottom: 2px; }
.card-date { font-size: 11px; color: #94a3b8; }
.card-actions { position: absolute; top: 6px; right: 6px; }

.table-view { padding-bottom: 16px; }

.node-view {
  position: relative;
  width: 100%;
  height: calc(100vh - 200px);
}
.cy-container {
  width: 100%;
  height: 100%;
  border-radius: 10px;
  border: 1px solid #e2e8f0;
  background: #fff;
}
.cy-legend {
  position: absolute;
  bottom: 20px;
  left: 16px;
  background: rgba(255,255,255,0.9);
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.legend-item { display: flex; align-items: center; gap: 8px; font-size: 12px; color: #475569; }
.legend-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }

.search-results-wrap { flex: 1; overflow-y: auto; padding: 20px; }
.search-results-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  font-size: 14px;
  color: #1e293b;
  font-weight: 600;
}
.result-count { color: #64748b; font-weight: 400; }
.search-result-list { display: flex; flex-direction: column; gap: 10px; }
.search-result-card {
  display: flex;
  gap: 14px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 14px 16px;
  cursor: pointer;
  transition: box-shadow 0.15s;
}
.search-result-card:hover { box-shadow: 0 2px 10px rgba(0,0,0,0.08); }
.src-thumb {
  width: 44px; height: 44px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.src-body { flex: 1; overflow: hidden; }
.src-title { font-size: 14px; font-weight: 600; color: #1e293b; margin-bottom: 4px; }
.src-snippet {
  font-size: 12px;
  color: #64748b;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  margin-bottom: 6px;
}
.src-meta { display: flex; align-items: center; gap: 8px; }
.score-badge {
  font-size: 11px;
  color: #2563eb;
  background: #eff6ff;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
}

.pagination-bar {
  padding: 12px 20px;
  display: flex;
  justify-content: flex-end;
  border-top: 1px solid #e2e8f0;
  background: #fff;
  flex-shrink: 0;
}

.detail-panel {
  position: fixed;
  top: 0;
  right: 0;
  width: 380px;
  height: 100vh;
  background: #fff;
  border-left: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  z-index: 100;
  box-shadow: -4px 0 20px rgba(0,0,0,0.06);
}
.panel-slide-enter-active,
.panel-slide-leave-active { transition: transform 0.3s ease; }
.panel-slide-enter-from,
.panel-slide-leave-to { transform: translateX(100%); }

.panel-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-bottom: 1px solid #e2e8f0;
  flex-shrink: 0;
}
.panel-thumb {
  width: 36px; height: 36px;
  border-radius: 7px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.panel-title-wrap { flex: 1; overflow: hidden; }
.panel-title {
  font-size: 13px;
  font-weight: 600;
  color: #1e293b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: 3px;
}
.panel-tabs { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
:deep(.el-tabs__content) { flex: 1; overflow: hidden; padding: 0; }
:deep(.el-tab-pane) { height: 100%; display: flex; flex-direction: column; }

.info-section { padding: 14px 16px; }
.info-row {
  display: flex;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid #f1f5f9;
  font-size: 13px;
}
.info-label { color: #64748b; width: 78px; flex-shrink: 0; }
.info-val { color: #1e293b; flex: 1; word-break: break-all; }
.panel-actions { padding: 12px 16px; }

.chunk-badge { margin-left: 6px; }
.chunks-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-bottom: 1px solid #f1f5f9;
  flex-shrink: 0;
}
.chunks-scroll { flex: 1; padding: 8px 16px; }
.chunk-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 8px;
}
.chunk-header { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.chunk-len { margin-left: auto; font-size: 11px; color: #94a3b8; }
.chunk-content {
  font-size: 12px;
  line-height: 1.7;
  color: #334155;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
}

.content-scroll { flex: 1; padding: 16px; }
.full-content {
  font-size: 12px;
  line-height: 1.8;
  color: #334155;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'Courier New', monospace;
  margin: 0;
}

.color-swatches { display: flex; gap: 8px; flex-wrap: wrap; }
.swatch {
  width: 26px; height: 26px;
  border-radius: 50%;
  cursor: pointer;
  transition: transform 0.1s;
  outline-offset: 2px;
}
.swatch:hover { transform: scale(1.2); }

.loading-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 0;
  gap: 10px;
  color: #94a3b8;
  font-size: 13px;
}
</style>'''

with open(r'c:\Users\bruce\PycharmProjects\BruV AI新架構\frontend\src\views\DocsView.vue', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done. Lines:', content.count('\n') + 1)
