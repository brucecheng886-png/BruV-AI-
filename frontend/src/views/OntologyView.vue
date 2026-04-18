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

        <!-- Review Queue Tab -->
        <el-tab-pane name="review">
          <template #label>
            審核佇列
            <el-badge v-if="pendingCount > 0" :value="pendingCount" style="margin-left:4px;" />
          </template>
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
import { ref, onMounted, watch, nextTick } from 'vue'
import { Close } from '@element-plus/icons-vue'
import cytoscape from 'cytoscape'
import { ontologyApi } from '../api/index.js'

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

const blocklist = ref([])
const blocklistLoading = ref(false)

onMounted(async () => {
  await loadGraph()
  await loadReviewQueue()
  await loadBlocklist()
})

watch(activeTab, (t) => {
  if (t === 'graph') loadGraph()
  else if (t === 'review') loadReviewQueue()
  else if (t === 'blocklist') loadBlocklist()
})

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
</style>
