<template>
  <div class="onto-root">

    <!-- Left slide-in node detail panel -->
      <aside v-if="nodeDialogVisible" class="node-panel"
        :class="{ 'panel-visible': nodePanelOpen }"
        :style="{ width: nodePanelWidth + 'px' }">
        <div class="node-panel-resize-handle" @mousedown.prevent="onNodePanelResizeStart"></div>
        <div class="node-panel-header">
          <span class="node-panel-title">{{ selectedNode?.label || '節點詳情' }}</span>
          <el-button link :icon="Close" @click="closeNodePanel" />
        </div>
        <div class="node-panel-body">
          <div v-if="selectedNode">
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="名稱 / ID">
                {{ selectedNode.label }}
              </el-descriptions-item>
              <el-descriptions-item label="類型">
                <el-tag :type="nodeTagType(selectedNode.type)" size="small">{{ selectedNode.type }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item v-if="selectedNode.description" label="描述">
                {{ selectedNode.description }}
              </el-descriptions-item>
            </el-descriptions>

            <div v-if="selectedNodeEdges.length > 0" class="edges-section">
              <div class="edges-title">連結關係（{{ selectedNodeEdges.length }} 條）</div>
              <div
                v-for="(e, i) in selectedNodeEdges"
                :key="i"
                class="edge-row"
              >
                <el-tag size="small" :type="e.dir === 'out' ? 'primary' : 'warning'">
                  {{ e.dir === 'out' ? '→' : '←' }}
                </el-tag>
                <span class="edge-rel">{{ e.rel }}</span>
                <span class="edge-peer">{{ e.peer }}</span>
              </div>
            </div>
            <el-empty v-else description="此節點無連結關係" style="padding:16px 0;" />
          </div>
        </div>
      </aside>

    <!-- Main content area -->
    <div class="onto-main" :style="{ marginRight: nodePanelOpen ? (nodePanelWidth + 16) + 'px' : '0' }">
      <h2 class="onto-heading">知識圖譜</h2>

      <el-tabs v-model="activeTab" class="onto-tabs">
        <!-- Graph Tab -->
        <el-tab-pane label="圖譜視覺化" name="graph">
          <div class="graph-toolbar">
            <el-button @click="loadGraph" :loading="graphLoading">重新載入</el-button>
            <span class="graph-stats">節點：{{ nodeCount }} | 邊：{{ edgeCount }}</span>
            <span class="graph-hint">點擊節點可查看詳情</span>
          </div>
          <div ref="cyContainer" class="cy-container"></div>
        </el-tab-pane>

        <!-- 3D 權重圖譜 Tab -->
        <el-tab-pane name="3d" label="3D 權重圖譜">
          <div class="graph-toolbar">
            <el-button @click="load3DGraph" :loading="graph3dLoading">重新載入</el-button>
            <span class="graph-stats">節點：{{ nodeCount }} | 邊：{{ edgeCount }}</span>
            <span class="graph-hint">節點大小＝連結數；連結粗細＝出現頻率；拖曳旋轉</span>
            <div style="margin-left:auto;display:flex;gap:6px;align-items:center">
              <el-tag v-for="(c, t) in COLOR_MAP_DISPLAY" :key="t" :style="`background:${c};border-color:${c};color:#fff`" size="small">{{ t }}</el-tag>
            </div>
          </div>
          <div class="graph-3d-wrap">
            <div ref="container3d" class="container-3d"></div>
            <div class="graph-3d-sidebar">
              <div class="sidebar-title">🏆 高連結節點 TOP 15</div>
              <div
                v-for="n in topWeightNodes"
                :key="n.id"
                class="weight-row"
                @click="highlight3DNode(n)"
              >
                <span class="weight-dot" :style="`background:${COLOR_MAP_DISPLAY[n.type] || '#909399'}`"></span>
                <span class="weight-name" :title="n.name">{{ n.name }}</span>
                <el-tag size="small" effect="plain">{{ n.weight }}</el-tag>
              </div>
              <el-empty v-if="!topWeightNodes.length" description="尚無資料" :image-size="60" />
            </div>
          </div>
        </el-tab-pane>

        <!-- Review Queue Tab -->
        <el-tab-pane name="review">
          <template #label>
            審核佇列
            <el-badge v-if="pendingCount > 0" :value="pendingCount" style="margin-left:4px;" />
          </template>
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
            <span style="font-size:13px;color:#606266;">共 {{ pendingCount }} 筆待審核</span>
            <el-button type="success" size="small" :loading="batchLoading" @click="batchApproveAll">
              <CheckCheck :size="14" :stroke-width="1.5" style="margin-right:4px" />全部核准
            </el-button>
            <el-button type="danger" size="small" :loading="batchLoading" @click="batchRejectAll">
              <XCircle :size="14" :stroke-width="1.5" style="margin-right:4px" />全部拒絕
            </el-button>
          </div>
          <el-table :data="reviewQueue" v-loading="queueLoading" stripe style="width:100%;">
            <el-table-column label="實體名稱" prop="entity_name" min-width="120" />
            <el-table-column label="類型" prop="entity_type" width="90" />
            <el-table-column label="動作" width="80">
              <template #default="{ row }">
                <el-tag :type="actionType(row.action)">{{ row.action }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="提議資料" min-width="200">
              <template #default="{ row }">
                <el-tooltip :content="JSON.stringify(row.proposed_data)" placement="top">
                  <span style="font-size:12px;color:#666;">{{ JSON.stringify(row.proposed_data).slice(0,60) }}...</span>
                </el-tooltip>
              </template>
            </el-table-column>
            <el-table-column label="建立時間" width="140">
              <template #default="{ row }">{{ row.created_at?.slice(0,16).replace('T',' ') }}</template>
            </el-table-column>
            <el-table-column label="操作" width="160" align="center">
              <template #default="{ row }">
                <el-button size="small" type="success" @click="approveItem(row.id)" :loading="row._loading">核准</el-button>
                <el-button size="small" type="danger" @click="rejectItem(row.id)" :loading="row._loading">拒絕</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- Blocklist Tab -->
        <el-tab-pane label="封鎖清單" name="blocklist">
          <el-table :data="blocklist" v-loading="blocklistLoading" stripe style="width:100%;">
            <el-table-column label="名稱" prop="name" min-width="150" />
            <el-table-column label="類型" prop="entity_type" width="100" />
            <el-table-column label="封鎖時間" width="140">
              <template #default="{ row }">{{ row.created_at?.slice(0,16).replace('T',' ') }}</template>
            </el-table-column>
            <el-table-column label="操作" width="100" align="center">
              <template #default="{ row }">
                <el-popconfirm title="移除封鎖？" @confirm="removeBlocklist(row.id)">
                  <template #reference>
                    <el-button size="small" type="warning" plain>移除</el-button>
                  </template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onActivated, onUnmounted, watch, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Close } from '@element-plus/icons-vue'
import { CheckCheck, XCircle } from 'lucide-vue-next'
import cytoscape from 'cytoscape'
import { ontologyApi } from '../api/index.js'
import ForceGraph3D from '3d-force-graph'

const COLOR_MAP_DISPLAY = {
  Entity: '#4a90d9', Document: '#67c23a', Concept: '#e6a23c',
}

const activeTab = ref('graph')
const cyContainer = ref(null)
let cy = null
let graphData = { nodes: [], edges: [] }

const graphLoading = ref(false)
const nodeCount = ref(0)
const edgeCount = ref(0)

const nodeDialogVisible = ref(false)
const nodePanelOpen = ref(false)
const selectedNode = ref(null)
const selectedNodeEdges = ref([])
const nodePanelWidth = ref(380)
const NODE_PANEL_MIN_W = 280
const NODE_PANEL_MAX_W = 800

function closeNodePanel() {
  nodePanelOpen.value = false
  setTimeout(() => {
    if (!nodePanelOpen.value) nodeDialogVisible.value = false
  }, 320)
}

function onNodePanelResizeStart(e) {
  const startX = e.clientX
  const startW = nodePanelWidth.value
  const onMove = (ev) => {
    const delta = startX - ev.clientX
    nodePanelWidth.value = Math.min(NODE_PANEL_MAX_W, Math.max(NODE_PANEL_MIN_W, startW + delta))
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

const reviewQueue = ref([])
const queueLoading = ref(false)
const pendingCount = ref(0)
const batchLoading = ref(false)

const blocklist = ref([])
const blocklistLoading = ref(false)

let _ontoMounting = false
onMounted(async () => {
  _ontoMounting = true
  try {
    await loadGraph()
    await loadReviewQueue()
    await loadBlocklist()
  } finally {
    _ontoMounting = false
  }
  window.addEventListener('ai-action', _onAiAction)
})

onActivated(async () => {
  if (_ontoMounting) return
  await loadGraph()
  await loadReviewQueue()
  await loadBlocklist()
})

watch(activeTab, (t) => {
  if (t === 'graph') loadGraph()
  else if (t === '3d') load3DGraph()
  else if (t === 'review') loadReviewQueue()
  else if (t === 'blocklist') loadBlocklist()
})

onUnmounted(() => {
  if (graph3d) { try { graph3d._destructor?.() } catch {} ; graph3d = null }
  window.removeEventListener('ai-action', _onAiAction)
})

function _onAiAction(e) {
  const action = e.detail
  if (action.type === 'batch_approve_all' || action.type === 'batch_reject_all') {
    loadReviewQueue()
    loadGraph()
  }
}

// ── 3D 圖譜 ───────────────────────────────────────────────────────────────────
const container3d  = ref(null)
let   graph3d      = null
const graph3dLoading = ref(false)
const graph3dData  = ref({ nodes: [], links: [] })

const topWeightNodes = computed(() =>
  [...graph3dData.value.nodes]
    .sort((a, b) => (b.weight || 1) - (a.weight || 1))
    .slice(0, 15)
)

function _toGraph3D(raw) {
  const colorMap = { Entity: '#4a90d9', Document: '#67c23a', Concept: '#e6a23c' }
  const nodes = (raw.nodes || []).map(n => ({
    id: n.data.id,
    name: n.data.label || n.data.id,
    type: n.data.type || 'Entity',
    weight: n.data.weight || 1,
    description: n.data.description || '',
    color: colorMap[n.data.type] || '#909399',
  }))
  const links = (raw.edges || []).map(e => ({
    source: e.data.source,
    target: e.data.target,
    label: e.data.label || '',
    weight: e.data.weight || 1,
  }))
  return { nodes, links }
}

async function load3DGraph() {
  graph3dLoading.value = true
  try {
    // 共用已載入的 graphData，避免重複請求
    const raw = graphData.nodes?.length ? graphData : await ontologyApi.graph()
    if (!graphData.nodes?.length) {
      graphData = raw
      nodeCount.value = raw.nodes?.length || 0
      edgeCount.value = raw.edges?.length || 0
    }
    graph3dData.value = _toGraph3D(raw)
    await nextTick()
    _init3DGraph()
  } catch (e) {
    console.error('3D graph error:', e)
  } finally {
    graph3dLoading.value = false
  }
}

function _init3DGraph() {
  if (!container3d.value) return
  if (graph3d) {
    try { graph3d._destructor?.() } catch {}
    graph3d = null
  }
  container3d.value.innerHTML = ''

  const w = container3d.value.clientWidth  || 800
  const h = container3d.value.clientHeight || 560

  graph3d = ForceGraph3D({ controlType: 'orbit' })(container3d.value)
    .width(w).height(h)
    .backgroundColor('#0f172a')
    .graphData(graph3dData.value)
    // 節點
    .nodeLabel(n => `<div style="background:#1e293b;padding:4px 8px;border-radius:6px;font-size:12px;color:#e2e8f0">${n.name}<br/><span style="color:#94a3b8">${n.type} · 連結數: ${n.weight}</span></div>`)
    .nodeColor(n => n.color)
    .nodeVal(n => Math.max(1, Math.log2((n.weight || 1) + 1)) * 4)
    .nodeResolution(16)
    .nodeOpacity(0.9)
    // 連結
    .linkLabel(l => l.label)
    .linkWidth(l => Math.max(0.5, Math.log2((l.weight || 1) + 1)))
    .linkColor(l => l.label === 'MENTIONS' ? '#67c23a88' : '#4a90d988')
    .linkOpacity(0.5)
    .linkDirectionalArrowLength(4)
    .linkDirectionalArrowRelPos(1)
    .linkDirectionalParticles(l => Math.min(3, l.weight || 1))
    .linkDirectionalParticleWidth(1.5)
    // 互動
    .onNodeClick(node => {
      selectedNode.value = { id: node.id, label: node.name, type: node.type, description: node.description }
      const relatedEdges = []
      ;(graphData.edges || []).forEach(e => {
        const d = e.data
        const src = typeof d.source === 'object' ? d.source?.id : d.source
        const tgt = typeof d.target === 'object' ? d.target?.id : d.target
        if (src === node.id) relatedEdges.push({ dir: 'out', rel: d.label, peer: tgt })
        else if (tgt === node.id) relatedEdges.push({ dir: 'in', rel: d.label, peer: src })
      })
      selectedNodeEdges.value = relatedEdges
      nodeDialogVisible.value = true
      nextTick(() => { nodePanelOpen.value = true })
    })
}

function highlight3DNode(node) {
  if (!graph3d) return
  const found = graph3dData.value.nodes.find(n => n.id === node.id)
  if (found) {
    const dist = 120
    const distRatio = 1 + dist / Math.hypot(found.x || 1, found.y || 1, found.z || 1)
    graph3d.cameraPosition(
      { x: (found.x || 0) * distRatio, y: (found.y || 0) * distRatio, z: (found.z || 0) * distRatio },
      found,
      1500
    )
  }
}

async function loadGraph() {
  graphLoading.value = true
  try {
    const data = await ontologyApi.graph()
    graphData = data
    nodeCount.value = data.nodes?.length || 0
    edgeCount.value = data.edges?.length || 0
    initCytoscape(data.nodes || [], data.edges || [])
  } catch (e) {
    console.error('Graph load error:', e)
  } finally {
    graphLoading.value = false
  }
}

function initCytoscape(nodes, edges) {
  if (!cyContainer.value) return
  if (cy) { cy.destroy(); cy = null }

  const colorMap = { Entity: '#4a90d9', Document: '#67c23a', Concept: '#e6a23c', default: '#909399' }
  const elements = [
    ...nodes.map(n => ({
      data: {
        id: n.data.id,
        label: n.data.label?.slice(0, 20) || n.data.id,
        fullLabel: n.data.label || n.data.id,
        type: n.data.type || 'Entity',
        description: n.data.description || '',
        bg: colorMap[n.data.type] || colorMap.default,
      }
    })),
    ...edges.map(e => ({
      data: {
        id: e.data.id,
        source: e.data.source,
        target: e.data.target,
        label: e.data.label || '',
      }
    }))
  ]

  cy = cytoscape({
    container: cyContainer.value,
    elements,
    style: [
      {
        selector: 'node',
        style: {
          'background-color': 'data(bg)',
          'label': 'data(label)',
          'color': '#fff',
          'text-outline-color': '#555',
          'text-outline-width': 1,
          'font-size': '11px',
          'width': 42,
          'height': 42,
          'cursor': 'pointer',
        },
      },
      {
        selector: 'node:selected',
        style: { 'border-width': 3, 'border-color': '#f56c6c' },
      },
      {
        selector: 'edge',
        style: {
          'width': 2,
          'line-color': '#aaa',
          'target-arrow-color': '#aaa',
          'target-arrow-shape': 'triangle',
          'curve-style': 'bezier',
          'font-size': '10px',
          'color': '#666',
        },
      },
    ],
    layout: {
      name: 'cose',
      animate: false,
      nodeRepulsion: 80000,
      idealEdgeLength: 100,
    },
  })

  cy.on('tap', 'node', (evt) => {
    const node = evt.target
    const d = node.data()
    selectedNode.value = {
      id: d.id,
      label: d.fullLabel || d.label,
      type: d.type,
      description: d.description,
    }
    const relatedEdges = []
    cy.edges().forEach(edge => {
      const sd = edge.data()
      if (sd.source === d.id) {
        relatedEdges.push({ dir: 'out', rel: sd.label, peer: sd.target })
      } else if (sd.target === d.id) {
        relatedEdges.push({ dir: 'in', rel: sd.label, peer: sd.source })
      }
    })
    selectedNodeEdges.value = relatedEdges
    nodeDialogVisible.value = true
    nextTick(() => { nodePanelOpen.value = true })
  })
}

function nodeTagType(type) {
  return { Entity: 'primary', Document: 'success', Concept: 'warning' }[type] || 'info'
}

async function loadReviewQueue() {
  queueLoading.value = true
  try {
    const data = await ontologyApi.reviewQueue('pending')
    reviewQueue.value = data.map(r => ({ ...r, _loading: false }))
    pendingCount.value = reviewQueue.value.length
  } catch (e) {
    console.error(e)
  } finally {
    queueLoading.value = false
  }
}

async function approveItem(id) {
  const item = reviewQueue.value.find(r => r.id === id)
  if (item) item._loading = true
  try {
    await ontologyApi.approve(id)
    await loadReviewQueue()
    await loadGraph()
  } catch (e) {
    console.error(e)
  } finally {
    if (item) item._loading = false
  }
}

async function rejectItem(id) {
  const item = reviewQueue.value.find(r => r.id === id)
  if (item) item._loading = true
  try {
    await ontologyApi.reject(id)
    await loadReviewQueue()
    await loadBlocklist()
  } catch (e) {
    console.error(e)
  } finally {
    if (item) item._loading = false
  }
}

async function batchApproveAll() {
  try {
    await ElMessageBox.confirm(
      `確定要核准全部 ${pendingCount.value} 筆審核項目？`,
      '批次核准',
      { type: 'warning', confirmButtonText: '確定', cancelButtonText: '取消' }
    )
  } catch { return }
  batchLoading.value = true
  try {
    const res = await ontologyApi.batchApprove({ all: true })
    ElMessage.success(`已核准 ${res.approved} 筆`)
    await loadReviewQueue()
    await loadGraph()
  } catch (e) {
    ElMessage.error(e.message || '批次核准失敗')
  } finally {
    batchLoading.value = false
  }
}

async function batchRejectAll() {
  try {
    await ElMessageBox.confirm(
      `確定要拒絕全部 ${pendingCount.value} 筆審核項目？拒絕後會加入封鎖清單。`,
      '批次拒絕',
      { type: 'warning', confirmButtonText: '確定拒絕', cancelButtonText: '取消' }
    )
  } catch { return }
  batchLoading.value = true
  try {
    const res = await ontologyApi.batchReject({ all: true })
    ElMessage.success(`已拒絕 ${res.rejected} 筆`)
    await loadReviewQueue()
    await loadBlocklist()
  } catch (e) {
    ElMessage.error(e.message || '批次拒絕失敗')
  } finally {
    batchLoading.value = false
  }
}

async function loadBlocklist() {
  blocklistLoading.value = true
  try {
    blocklist.value = await ontologyApi.blocklist()
  } catch (e) {
    console.error(e)
  } finally {
    blocklistLoading.value = false
  }
}

async function removeBlocklist(id) {
  try {
    await ontologyApi.deleteBlocklist(id)
    await loadBlocklist()
  } catch (e) {
    console.error(e)
  }
}

function actionType(action) {
  const map = { create: 'success', update: 'warning', delete: 'danger' }
  return map[action] || 'info'
}
</script>

<style scoped>
/* ── Root layout ── */
.onto-root {
  position: relative;
  height: 100%;
  overflow: hidden;
  display: flex;
  font-family: -apple-system, 'Microsoft JhengHei', sans-serif;
}

/* ── Right slide panel ── */
.node-panel {
  position: absolute;
  right: 0;
  top: 0;
  width: 380px;
  height: 100%;
  background: #fff;
  border-left: 1px solid #e2e8f0;
  border-radius: 16px 0 0 16px;
  box-shadow: -8px 0 32px rgba(0,0,0,0.1);
  z-index: 10;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transform: translateX(100%);
  transition: transform 0.3s ease;
}
.node-panel.panel-visible {
  transform: translateX(0);
}
.node-panel-resize-handle {
  position: absolute;
  left: -3px;
  top: 0;
  width: 6px;
  height: 100%;
  cursor: col-resize;
  z-index: 20;
}
.node-panel-resize-handle:hover,
.node-panel-resize-handle:active {
  background: linear-gradient(90deg, transparent 1px, #409eff 1px, #409eff 3px, transparent 3px);
}

.node-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #e2e8f0;
  flex-shrink: 0;
}
.node-panel-title {
  font-size: 16px;
  font-weight: 600;
  color: #1e293b;
}
.node-panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}
.edges-section { margin-top: 20px; }
.edges-title {
  font-weight: 600;
  margin-bottom: 10px;
  font-size: 14px;
  color: #475569;
}
.edge-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: #f8fafc;
  border-radius: 6px;
  margin-bottom: 6px;
  font-size: 13px;
}
.edge-rel { color: #4a90d9; font-weight: 500; }
.edge-peer { color: #1e293b; }

/* ── Main content ── */
.onto-main {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
  transition: margin-right 0.3s ease;
  min-width: 0;
}

.onto-heading {
  font-size: 20px;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 20px;
}

.onto-tabs { flex: 1; }

.graph-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.graph-stats { font-size: 13px; color: #666; }
.graph-hint { font-size: 12px; color: #aaa; margin-left: 8px; }

.cy-container {
  width: 100%;
  height: 520px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #fafafa;
}

/* ── 3D Graph ── */
.graph-3d-wrap {
  display: flex;
  gap: 12px;
  height: 580px;
}
.container-3d {
  flex: 1;
  min-width: 0;
  border-radius: 10px;
  overflow: hidden;
  background: #0f172a;
}
.graph-3d-sidebar {
  width: 200px;
  flex-shrink: 0;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 10px;
  padding: 12px;
  overflow-y: auto;
}
.sidebar-title {
  font-size: 12px;
  font-weight: 600;
  color: #666;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.weight-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 4px;
  border-radius: 5px;
  cursor: pointer;
  transition: background .15s;
}
.weight-row:hover { background: var(--el-fill-color-light); }
.weight-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.weight-name { flex: 1; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
