<template>
  <div class="pg-root">

    <!-- ── 左側控制面板 ───────────────────────────────── -->
    <aside class="pg-sidebar">
      <div class="pg-logo">🧬 蛋白質互作圖譜</div>

      <!-- 上傳 -->
      <div class="pg-section">
        <div class="pg-section-title">上傳資料</div>
        <el-upload
          ref="uploadRef"
          multiple
          :auto-upload="false"
          :limit="2"
          accept=".xlsx"
          :on-change="onFileChange"
          :on-remove="onFileRemove"
          drag
          class="pg-upload"
        >
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">拖曳或點擊上傳 xlsx（最多 2 個）</div>
          <template #tip>
            <div class="el-upload__tip">genes list + scores xlsx</div>
          </template>
        </el-upload>
        <el-button
          type="primary"
          :loading="importing"
          :disabled="pendingFiles.length === 0"
          @click="doImport"
          style="width:100%;margin-top:8px;"
        >匯入 Excel</el-button>
        <div v-if="importResult" class="import-result">
          <el-tag type="success" size="small">✅ 基因 {{ importResult.genes_imported }} 筆</el-tag>
          <el-tag type="success" size="small">✅ 互作 {{ importResult.interactions_imported }} 筆</el-tag>
        </div>
      </div>

      <!-- Network 選擇 -->
      <div class="pg-section">
        <div class="pg-section-title">Network</div>
        <el-select v-model="selectedNetwork" placeholder="選擇 Network" style="width:100%;" @change="loadGraph">
          <el-option v-for="n in networks" :key="n" :label="n" :value="n" />
        </el-select>
        <div class="pg-slider-row">
          <span>最低評分</span>
          <el-slider v-model="minScore" :min="0" :max="1" :step="0.05" style="flex:1;margin:0 10px;" @change="loadGraph" />
          <span>{{ minScore }}</span>
        </div>
      </div>

      <!-- 節點數 / 邊數 -->
      <div class="pg-section pg-stats">
        <div><span class="stat-num">{{ nodeCount }}</span><span class="stat-label">節點</span></div>
        <div><span class="stat-num">{{ edgeCount }}</span><span class="stat-label">連結</span></div>
      </div>

      <!-- Top 排行 -->
      <div class="pg-section" style="flex:1;overflow:hidden;display:flex;flex-direction:column;">
        <div class="pg-section-title">🏆 高分連結 TOP {{ topList.length }}</div>
        <div class="top-list">
          <div v-for="(row, i) in topList" :key="i" class="top-row" @click="highlightPair(row)">
            <span class="top-rank">{{ i + 1 }}</span>
            <span class="top-pair">{{ row.protein_a }} ↔ {{ row.protein_b }}</span>
            <span class="top-score" :style="scoreColor(row.score)">{{ row.score.toFixed(3) }}</span>
          </div>
          <el-empty v-if="!topList.length" description="尚無資料" :image-size="50" />
        </div>
      </div>
    </aside>

    <!-- ── 右側 3D 圖 ──────────────────────────────────── -->
    <div class="pg-graph-area">
      <!-- 工具列 -->
      <div class="pg-toolbar">
        <el-button-group>
          <el-button size="small" :type="viewMode==='3d'?'primary':''" @click="viewMode='3d'">3D 圖譜</el-button>
          <el-button size="small" :type="viewMode==='table'?'primary':''" @click="viewMode='table'">表格</el-button>
        </el-button-group>
        <el-button size="small" :loading="graphLoading" @click="loadGraph" style="margin-left:8px;">
          <el-icon><Refresh /></el-icon> 重新整理
        </el-button>
        <span class="pg-hint">節點大小 = 連結度；邊顏色 = 評分深淺；點擊節點開啟 GeneCards</span>
      </div>

      <!-- 3D force graph 容器 -->
      <div v-show="viewMode==='3d'" ref="container3d" class="pg-3d-container" v-loading="graphLoading" />

      <!-- 表格視圖 -->
      <div v-if="viewMode==='table'" class="pg-table-wrap">
        <el-table :data="allEdges" stripe style="width:100%;" max-height="calc(100vh - 120px)">
          <el-table-column label="蛋白質 A" prop="source" width="140" sortable />
          <el-table-column label="蛋白質 B" prop="target" width="140" sortable />
          <el-table-column label="評分" prop="value" width="100" sortable>
            <template #default="{ row }">
              <el-tag :type="row.value >= 0.8 ? 'danger' : row.value >= 0.6 ? 'warning' : 'info'" size="small">
                {{ row.value.toFixed(3) }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, Refresh } from '@element-plus/icons-vue'
import ForceGraph3D from '3d-force-graph'
import { proteinApi } from '../api/index.js'

// ── 狀態 ──────────────────────────────────────────────────────
const networks        = ref([])
const selectedNetwork = ref('')
const minScore        = ref(0.5)
const graphLoading    = ref(false)
const importing       = ref(false)
const importResult    = ref(null)
const viewMode        = ref('3d')

const nodeCount = ref(0)
const edgeCount = ref(0)
const allEdges  = ref([])
const topList   = ref([])

const pendingFiles = ref([])
const uploadRef    = ref(null)
const container3d  = ref(null)
let   graph3d      = null

// ── 上傳 ──────────────────────────────────────────────────────
function onFileChange(file, fileList) {
  pendingFiles.value = fileList.map(f => f.raw)
}
function onFileRemove(file, fileList) {
  pendingFiles.value = fileList.map(f => f.raw)
}

async function doImport() {
  if (!pendingFiles.value.length) return
  importing.value = true
  importResult.value = null
  try {
    const result = await proteinApi.import(pendingFiles.value)
    importResult.value = result
    ElMessage.success(`匯入完成：${result.interactions_imported} 筆互作`)
    // 重新載入 networks
    await loadNetworks()
    if (result.networks?.length) {
      selectedNetwork.value = result.networks[0]
    }
    await loadGraph()
    await loadTop()
  } catch (e) {
    ElMessage.error(e.message || '匯入失敗')
  } finally {
    importing.value = false
  }
}

// ── 載入 networks ─────────────────────────────────────────────
async function loadNetworks() {
  try {
    const data = await proteinApi.networks()
    networks.value = data.networks || []
    if (!selectedNetwork.value && networks.value.length) {
      selectedNetwork.value = networks.value[0]
    }
  } catch {
    // 尚未匯入，忽略
  }
}

// ── 載入圖譜 ──────────────────────────────────────────────────
async function loadGraph() {
  if (!selectedNetwork.value) return
  graphLoading.value = true
  try {
    const data = await proteinApi.graph(selectedNetwork.value, minScore.value)
    nodeCount.value = data.nodes?.length || 0
    edgeCount.value = data.links?.length || 0
    allEdges.value  = data.links || []
    await nextTick()
    _initGraph(data)
  } catch (e) {
    ElMessage.error(e.message || '載入圖譜失敗')
  } finally {
    graphLoading.value = false
  }
}

// ── 載入 Top 排行 ─────────────────────────────────────────────
async function loadTop() {
  if (!selectedNetwork.value) return
  try {
    const data = await proteinApi.top(selectedNetwork.value, 20)
    topList.value = data.interactions || []
  } catch {}
}

// ── 3D 圖初始化 ───────────────────────────────────────────────
function _scoreToColor(score) {
  // 0 → 藍, 1 → 紅 (HSL)
  const h = Math.round((1 - score) * 240)
  return `hsl(${h},85%,55%)`
}

function _initGraph(data) {
  if (!container3d.value) return
  if (graph3d) {
    try { graph3d._destructor?.() } catch {}
    graph3d = null
  }
  container3d.value.innerHTML = ''

  const w = container3d.value.clientWidth  || 900
  const h = container3d.value.clientHeight || 600

  // 節點顏色按連結度分層
  const maxVal = Math.max(...(data.nodes || []).map(n => n.val || 1), 1)

  graph3d = ForceGraph3D({ controlType: 'orbit' })(container3d.value)
    .width(w).height(h)
    .backgroundColor('#0f172a')
    .graphData({ nodes: data.nodes || [], links: data.links || [] })
    // ── 節點 ──
    .nodeLabel(n =>
      `<div style="background:#1e293b;padding:4px 10px;border-radius:6px;font-size:12px;color:#e2e8f0">
        <b>${n.name}</b><br/>
        <span style="color:#94a3b8">連結度: ${n.val}</span>
      </div>`
    )
    .nodeColor(n => {
      const ratio = (n.val || 1) / maxVal
      const h = Math.round((1 - ratio) * 200 + 20)   // 橘→藍漸層
      return `hsl(${h},80%,55%)`
    })
    .nodeVal(n => Math.max(1, Math.log2((n.val || 1) + 1)) * 5)
    .nodeResolution(16)
    .nodeOpacity(0.9)
    // ── 連結 ──
    .linkLabel(l => `${l.source?.name || l.source} ↔ ${l.target?.name || l.target}<br/>score: ${Number(l.value).toFixed(3)}`)
    .linkWidth(l => Math.max(0.3, (l.value || 0) * 3))
    .linkColor(l => _scoreToColor(l.value || 0))
    .linkOpacity(0.6)
    .linkDirectionalParticles(l => l.value > 0.8 ? 3 : l.value > 0.6 ? 2 : 0)
    .linkDirectionalParticleWidth(1.5)
    .linkDirectionalParticleSpeed(0.006)
    // ── 互動 ──
    .onNodeClick(node => {
      if (node.url) window.open(node.url, '_blank', 'noopener')
    })
}

// ── 高亮指定節點對 ────────────────────────────────────────────
function highlightPair(row) {
  if (!graph3d) return
  const gd = graph3d.graphData()
  const node = gd.nodes.find(n => n.id === row.protein_a || n.id === row.protein_b)
  if (!node) return
  const dist = 120
  const { x = 0, y = 0, z = 0 } = node
  const r = Math.hypot(x, y, z) || 1
  const ratio = 1 + dist / r
  graph3d.cameraPosition(
    { x: x * ratio, y: y * ratio, z: z * ratio },
    { x, y, z },
    1200,
  )
}

// ── 評分色 ────────────────────────────────────────────────────
function scoreColor(score) {
  if (score >= 0.8) return 'color:#f56c6c;font-weight:700'
  if (score >= 0.6) return 'color:#e6a23c;font-weight:600'
  return 'color:#67c23a'
}

// ── resize 處理 ───────────────────────────────────────────────
let resizeObs = null
onMounted(async () => {
  await loadNetworks()
  if (selectedNetwork.value) {
    await loadGraph()
    await loadTop()
  }
  resizeObs = new ResizeObserver(() => {
    if (graph3d && container3d.value) {
      graph3d.width(container3d.value.clientWidth)
            .height(container3d.value.clientHeight)
    }
  })
  if (container3d.value) resizeObs.observe(container3d.value)
})
onUnmounted(() => {
  if (resizeObs) resizeObs.disconnect()
  if (graph3d) { try { graph3d._destructor?.() } catch {} }
})
</script>

<style scoped>
.pg-root {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: #0f172a;
  color: #e2e8f0;
  font-family: -apple-system, 'Microsoft JhengHei', sans-serif;
}

/* ── 左側欄 ── */
.pg-sidebar {
  width: 280px;
  min-width: 260px;
  background: #1e293b;
  border-right: 1px solid #334155;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  overflow-x: hidden;
  padding-bottom: 12px;
}
.pg-logo {
  padding: 16px 16px 10px;
  font-size: 16px;
  font-weight: 700;
  color: #7dd3fc;
  border-bottom: 1px solid #334155;
}
.pg-section {
  padding: 12px 14px;
  border-bottom: 1px solid #334155;
}
.pg-section-title {
  font-size: 11px;
  font-weight: 600;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 8px;
}
:deep(.pg-upload .el-upload-dragger) {
  background: #0f172a;
  border-color: #334155;
  padding: 12px;
}
:deep(.pg-upload .el-icon--upload) { color: #7dd3fc; }
:deep(.pg-upload .el-upload__text) { color: #94a3b8; font-size: 12px; }
:deep(.pg-upload .el-upload__tip)  { color: #64748b; font-size: 11px; }

.import-result {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 8px;
}
.pg-slider-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #94a3b8;
  margin-top: 10px;
}
.pg-stats {
  display: flex;
  justify-content: space-around;
  text-align: center;
}
.stat-num   { display: block; font-size: 24px; font-weight: 700; color: #7dd3fc; }
.stat-label { font-size: 11px; color: #64748b; }

.top-list {
  flex: 1;
  overflow-y: auto;
  margin-top: 4px;
}
.top-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 2px;
  border-bottom: 1px solid #1e293b;
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.15s;
}
.top-row:hover { background: #334155; }
.top-rank  { font-size: 11px; color: #64748b; width: 18px; text-align: right; flex-shrink: 0; }
.top-pair  { flex: 1; font-size: 12px; color: #cbd5e1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.top-score { font-size: 12px; font-weight: 700; flex-shrink: 0; }

/* ── 右側圖區 ── */
.pg-graph-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}
.pg-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: #1e293b;
  border-bottom: 1px solid #334155;
  flex-shrink: 0;
}
.pg-hint {
  font-size: 11px;
  color: #64748b;
  margin-left: 8px;
}
.pg-3d-container {
  flex: 1;
  min-height: 0;
}
.pg-table-wrap {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

/* Element Plus dark overrides */
:deep(.el-select .el-input__wrapper) { background: #0f172a; border-color: #334155; }
:deep(.el-select .el-input__inner)   { color: #e2e8f0; }
:deep(.el-button)                     { border-color: #334155; }
</style>
