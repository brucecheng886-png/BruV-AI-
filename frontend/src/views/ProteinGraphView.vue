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
          <el-button size="small" :type="viewMode==='stats'?'primary':''" @click="viewMode='stats';loadStats()">權重分布</el-button>
        </el-button-group>
        <el-button size="small" :loading="graphLoading" @click="loadGraph" style="margin-left:8px;">
          <el-icon><Refresh /></el-icon> 重新整理
        </el-button>
        <span class="pg-hint">節點大小 = 連結度；Z 軸高度 = 加權度；邊顏色 = 評分深淺；點擊節點開啟 GeneCards</span>
        <div v-if="nodeCount > 0" style="margin-left:auto;display:flex;align-items:center;gap:6px;flex-shrink:0;">
          <span style="font-size:11px;color:#64748b;">匯出：</span>
          <el-button size="small" @click="exportPng" title="下載 3D 圖譜 PNG（含座標軸）">🖼 PNG</el-button>
          <el-button size="small" @click="exportCyjs" title="Cytoscape Desktop 可直接開啟">Cytoscape</el-button>
          <el-button size="small" @click="exportCsv" title="邊列表 CSV（蛋白質對 + 評分）">CSV</el-button>
        </div>
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

      <!-- 權重分布統計視圖 -->
      <div v-if="viewMode==='stats'" class="pg-stats-panel">
        <div v-if="statsLoading" style="text-align:center;padding:40px;color:#94a3b8;">載入中...</div>
        <div v-else-if="statsData" class="stats-content">
          <div class="stats-summary">
            <div class="stats-card"><div class="stats-val">{{ statsData.total_edges.toLocaleString() }}</div><div class="stats-lbl">邊總數</div></div>
            <div class="stats-card"><div class="stats-val">{{ statsData.mean_score }}</div><div class="stats-lbl">平均分</div></div>
            <div class="stats-card"><div class="stats-val">{{ statsData.p50 }}</div><div class="stats-lbl">中位數 P50</div></div>
            <div class="stats-card"><div class="stats-val">{{ statsData.p75 }}</div><div class="stats-lbl">P75</div></div>
            <div class="stats-card"><div class="stats-val">{{ statsData.p90 }}</div><div class="stats-lbl">P90</div></div>
            <div class="stats-card"><div class="stats-val">{{ statsData.std_score }}</div><div class="stats-lbl">標準差</div></div>
          </div>
          <div class="stats-chart-wrap">
            <div class="stats-chart-title">評分分布直方圖（{{ selectedNetwork }}，閾值 ≥ {{ minScore }}）</div>
            <canvas ref="statsCanvas" class="stats-canvas" />
          </div>
        </div>
        <el-empty v-else description="尚無統計資料，請先匯入蛋白質互作資料" />
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onActivated, onUnmounted, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, Refresh } from '@element-plus/icons-vue'
import ForceGraph3D from '3d-force-graph'
import * as THREE from 'three'
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

// 統計相關
const statsLoading = ref(false)
const statsData    = ref(null)
const statsCanvas  = ref(null)

const pendingFiles = ref([])
const uploadRef    = ref(null)
const container3d  = ref(null)
let   graph3d      = null
const graphData    = ref({ nodes: [], links: [] })

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
    graphData.value = { nodes: data.nodes || [], links: data.links || [] }
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

// ── 載入統計 ──────────────────────────────────────────────────
async function loadStats() {
  if (!selectedNetwork.value) return
  statsLoading.value = true
  statsData.value    = null
  try {
    const data = await proteinApi.stats(selectedNetwork.value, minScore.value)
    statsData.value = data
    await nextTick()
    _drawStatsChart(data)
  } catch (e) {
    ElMessage.error(e.message || '統計載入失敗')
  } finally {
    statsLoading.value = false
  }
}

function _drawStatsChart(data) {
  const canvas = statsCanvas.value
  if (!canvas || !data?.distribution?.length) return
  const ctx    = canvas.getContext('2d')
  const dists  = data.distribution
  const maxCnt = Math.max(...dists.map(d => d.count), 1)
  const W = canvas.parentElement?.clientWidth  || 700
  const H = 260
  canvas.width  = W
  canvas.height = H
  ctx.clearRect(0, 0, W, H)

  const padL = 55, padR = 20, padT = 20, padB = 45
  const chartW = W - padL - padR
  const chartH = H - padT - padB
  const barW   = chartW / dists.length

  // 背景
  ctx.fillStyle = '#0f172a'
  ctx.fillRect(0, 0, W, H)

  // 格線
  ctx.strokeStyle = '#334155'
  ctx.lineWidth   = 0.5
  for (let i = 0; i <= 4; i++) {
    const y = padT + chartH - (i / 4) * chartH
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(padL + chartW, y); ctx.stroke()
    ctx.fillStyle = '#64748b'; ctx.font = '11px monospace'
    ctx.fillText(Math.round((i / 4) * maxCnt), 4, y + 4)
  }

  // 柱狀
  dists.forEach((d, i) => {
    const ratio   = d.count / maxCnt
    const barH    = ratio * chartH
    const x       = padL + i * barW + 2
    const y       = padT + chartH - barH
    const hue     = Math.round((1 - ratio) * 200 + 20)
    ctx.fillStyle = `hsl(${hue},80%,55%)`
    ctx.fillRect(x, y, barW - 4, barH)

    // X 軸標籤
    ctx.fillStyle = '#94a3b8'; ctx.font = '10px monospace'
    ctx.save(); ctx.translate(x + (barW - 4) / 2, padT + chartH + 14); ctx.rotate(-Math.PI / 4)
    ctx.fillText(d.range_lo.toFixed(2), 0, 0)
    ctx.restore()
  })

  // 軸線
  ctx.strokeStyle = '#475569'; ctx.lineWidth = 1
  ctx.beginPath(); ctx.moveTo(padL, padT); ctx.lineTo(padL, padT + chartH + 1); ctx.stroke()
  ctx.beginPath(); ctx.moveTo(padL, padT + chartH); ctx.lineTo(padL + chartW, padT + chartH); ctx.stroke()
}

// ── 3D 圖初始化 ───────────────────────────────────────────────
function _scoreToColor(score) {
  // 0 → 藍, 1 → 紅 (HSL)
  const h = Math.round((1 - score) * 240)
  return `hsl(${h},85%,55%)`
}

const Z_SCALE = 0.5   // Z 軸縮放比（weighted_degree 乘以此值）

function _initGraph(data) {
  if (!container3d.value) return
  if (graph3d) {
    try { graph3d._destructor?.() } catch {}
    graph3d = null
  }
  container3d.value.innerHTML = ''

  const w = container3d.value.clientWidth  || 900
  const h = container3d.value.clientHeight || 600

  // 預計算最大值（供顏色/Z 軸比例）
  const maxVal = Math.max(...(data.nodes || []).map(n => n.val || 1), 1)
  const maxWD  = Math.max(...(data.nodes || []).map(n => n.weighted_degree || 0), 1)

  // 設定初始 Z 座標：weighted_degree 越高，Z 越高
  const nodes = (data.nodes || []).map(n => ({
    ...n,
    fz: (n.weighted_degree || 0) / maxWD * 200 * Z_SCALE,
  }))

  graph3d = ForceGraph3D({ controlType: 'orbit' })(container3d.value)
    .width(w).height(h)
    .backgroundColor('#0f172a')
    .graphData({ nodes, links: data.links || [] })
    // ── 節點 ──
    .nodeLabel(n =>
      `<div style="background:#1e293b;padding:4px 10px;border-radius:6px;font-size:12px;color:#e2e8f0">
        <b>${n.name}</b><br/>
        <span style="color:#94a3b8">連結度: ${n.val} | 加權度: ${(n.weighted_degree || 0).toFixed(2)}</span>
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
    // Z 軸：依 weighted_degree 固定 z 值（強制 z 方向分層）
    .nodeThreeObject(null)
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
    .onEngineStop(() => _addAxes(graph3d, maxWD))
}

// ── 建立文字標籤 Sprite ──────────────────────────────────
function _makeTextSprite(text, hexColor) {
  const canvas = document.createElement('canvas')
  canvas.width = 320; canvas.height = 72
  const ctx = canvas.getContext('2d')
  ctx.font = 'bold 32px monospace'
  ctx.fillStyle = hexColor
  ctx.fillText(text, 6, 50)
  const tex = new THREE.CanvasTexture(canvas)
  const mat = new THREE.SpriteMaterial({ map: tex, depthWrite: false, transparent: true })
  const sprite = new THREE.Sprite(mat)
  sprite.scale.set(60, 14, 1)
  return sprite
}

// ── 在場景中迷加 XYZ 軸 ────────────────────────────────
function _addAxes(g, maxWD) {
  if (!g) return
  const scene = g.scene()
  // 移除舊軸組
  const old = scene.getObjectByName('protein-axes')
  if (old) scene.remove(old)

  const group = new THREE.Group()
  group.name = 'protein-axes'

  const L = 160   // 軸長
  const axesDef = [
    { dir: new THREE.Vector3(1, 0, 0), color: '#e74c3c', label: 'X  互作佈局' },
    { dir: new THREE.Vector3(0, 1, 0), color: '#2ecc71', label: 'Y  互作佈局' },
    { dir: new THREE.Vector3(0, 0, 1), color: '#3498db', label: `Z  加權度 (max=${maxWD.toFixed(1)})` },
  ]

  axesDef.forEach(({ dir, color, label }) => {
    const hex = parseInt(color.slice(1), 16)
    // 實線箔頭
    const arrow = new THREE.ArrowHelper(dir, new THREE.Vector3(0, 0, 0), L, hex, 16, 8)
    group.add(arrow)
    // 文字標籤
    const sprite = _makeTextSprite(label, color)
    sprite.position.copy(dir.clone().multiplyScalar(L + 32))
    group.add(sprite)
    // 負方向虛線
    const pts = [new THREE.Vector3(0,0,0), dir.clone().multiplyScalar(-L * 0.4)]
    const geom = new THREE.BufferGeometry().setFromPoints(pts)
    const mat  = new THREE.LineDashedMaterial({ color: hex, dashSize: 6, gapSize: 4, opacity: 0.35, transparent: true })
    const line = new THREE.Line(geom, mat)
    line.computeLineDistances()
    group.add(line)
  })

  // 原點小球
  const originGeo = new THREE.SphereGeometry(4, 12, 12)
  const originMat = new THREE.MeshBasicMaterial({ color: 0xffffff })
  group.add(new THREE.Mesh(originGeo, originMat))

  scene.add(group)
}

// ── 匯出功能 ─────────────────────────────────────────────────
function _triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

function exportPng() {
  if (!graph3d) return
  try {
    const renderer = graph3d.renderer()
    renderer.render(graph3d.scene(), graph3d.camera())
    renderer.domElement.toBlob(blob => {
      if (blob) _triggerDownload(blob, `protein_${selectedNetwork.value}_${new Date().toISOString().slice(0, 10)}.png`)
    })
  } catch (e) {
    ElMessage.error('PNG 匯出失敗：' + e.message)
  }
}

function exportCyjs() {
  const { nodes, links } = graphData.value
  if (!nodes.length) { ElMessage.warning('尚無圖譜資料'); return }
  const cyNodes = nodes.map(n => ({
    data: { id: n.id, label: n.name, degree: n.val, weighted_degree: n.weighted_degree, url: n.url }
  }))
  const cyEdges = links.map((l, i) => ({
    data: {
      id: `e${i}`,
      source: typeof l.source === 'object' ? l.source.id : l.source,
      target: typeof l.target === 'object' ? l.target.id : l.target,
      weight: l.value
    }
  }))
  const cyjs = {
    format_version: '1.0',
    generated_by: 'BruV AI Protein Graph',
    target_cytoscapejs_version: '~2.1',
    data: { name: selectedNetwork.value },
    elements: { nodes: cyNodes, edges: cyEdges },
    style: [
      {
        selector: 'node',
        css: {
          content: 'data(label)',
          'text-valign': 'center',
          width: 'mapData(degree, 1, 50, 20, 80)',
          height: 'mapData(degree, 1, 50, 20, 80)',
          'background-color': '#3498db',
          color: '#ffffff',
          'font-size': 10
        }
      },
      {
        selector: 'edge',
        css: {
          width: 'mapData(weight, 0, 1, 1, 6)',
          'line-color': 'mapData(weight, 0, 1, #aaaaff, #ff4444)',
          opacity: 0.7
        }
      }
    ]
  }
  const blob = new Blob([JSON.stringify(cyjs, null, 2)], { type: 'application/json' })
  _triggerDownload(blob, `protein_${selectedNetwork.value}.cyjs`)
}

function exportCsv() {
  const { links } = graphData.value
  if (!links.length) { ElMessage.warning('尚無邊資料'); return }
  const header = 'protein_a,protein_b,score,network\n'
  const rows = links.map(l => {
    const a = typeof l.source === 'object' ? l.source.id : l.source
    const b = typeof l.target === 'object' ? l.target.id : l.target
    return `${a},${b},${Number(l.value).toFixed(4)},${selectedNetwork.value}`
  }).join('\n')
  const blob = new Blob([header + rows], { type: 'text/csv;charset=utf-8;' })
  _triggerDownload(blob, `protein_${selectedNetwork.value}_edges.csv`)
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

// ── 將目前選擇的 network 寫入 localStorage，供 AgentPanel 讀取 ───────────────
watch(selectedNetwork, (val) => {
  if (val) localStorage.setItem('protein_selected_network', val)
})

// ── resize 處理 ───────────────────────────────────────────────
// 當 minScore 改變且統計面板開啟時，自動刷新
watch(minScore, () => {
  if (viewMode.value === 'stats') loadStats()
})

let resizeObs = null
let _proteinMounting = false
onMounted(async () => {
  _proteinMounting = true
  try {
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
  } finally {
    _proteinMounting = false
  }
})

onActivated(async () => {
  if (_proteinMounting) return
  await loadNetworks()
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

/* 統計面板 */
.pg-stats-panel {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  color: #e2e8f0;
}
.stats-content { display: flex; flex-direction: column; gap: 20px; }
.stats-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
.stats-card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 10px;
  padding: 14px 20px;
  min-width: 120px;
  text-align: center;
}
.stats-val  { font-size: 22px; font-weight: 700; color: #7dd3fc; }
.stats-lbl  { font-size: 11px; color: #64748b; margin-top: 4px; }
.stats-chart-wrap {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 10px;
  padding: 16px;
}
.stats-chart-title { font-size: 12px; color: #94a3b8; margin-bottom: 12px; }
.stats-canvas { display: block; width: 100%; }

/* Element Plus dark overrides */
:deep(.el-select .el-input__wrapper) { background: #0f172a; border-color: #334155; }
:deep(.el-select .el-input__inner)   { color: #e2e8f0; }
:deep(.el-button)                     { border-color: #334155; }
</style>
