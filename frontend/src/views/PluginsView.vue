<template>
  <div class="plugins-root">
    <!-- Header -->
    <div class="plugins-header">
      <div>
        <h2 class="page-title">插件管理</h2>
        <p class="page-subtitle">擴充 AI 能力，每個插件均可由 AI 自動調用</p>
      </div>
      <el-button type="primary" @click="openWebhookDialog">
        <el-icon style="margin-right:4px"><Plus /></el-icon>新增 Webhook 插件
      </el-button>
    </div>

    <!-- Tabs -->
    <el-tabs v-model="activeTab" class="plugins-tabs">
      <!-- ── 已安裝 ───────────────────────────── -->
      <el-tab-pane name="installed">
        <template #label>
          <span>已安裝 <el-badge :value="installedPlugins.length" class="tab-badge" /></span>
        </template>

        <div v-if="loadingInstalled" class="loading-wrap">
          <el-skeleton :rows="2" animated style="width:320px" />
        </div>
        <template v-else>
          <!-- 分類群組 -->
          <template v-for="(group, cat) in installedByCategory" :key="cat">
            <div v-if="group.length" class="category-section">
              <div class="category-label">{{ CATEGORY_LABELS[cat] || cat }}</div>
              <div class="card-grid">
                <div v-for="p in group" :key="p.id" class="plugin-card">
                  <div class="plugin-card-top">
                    <span class="cat-icon">{{ getCatalogEntry(p.builtin_key)?.icon || '🔌' }}</span>
                    <div style="flex:1;min-width:0">
                      <div class="plugin-name">{{ p.name }}</div>
                      <el-tag size="small" type="primary" effect="plain" style="margin-top:4px">AI 可調動</el-tag>
                    </div>
                    <el-switch :model-value="p.enabled" @change="togglePlugin(p)" />
                  </div>
                  <div class="plugin-desc">{{ p.description || getCatalogEntry(p.builtin_key)?.description }}</div>
                  <div class="plugin-card-foot">
                    <el-button size="small" plain @click="openConfigure(p)">設定</el-button>
                    <el-button size="small" plain @click="testPlugin(p)">測試</el-button>
                    <el-button size="small" type="danger" plain @click="confirmDelete(p)">刪除</el-button>
                  </div>
                </div>
              </div>
            </div>
          </template>
          <!-- Webhook 類型 -->
          <div v-if="installedUncategorized.length" class="category-section">
            <div class="category-label">自訂 Webhook</div>
            <div class="card-grid">
              <div v-for="p in installedUncategorized" :key="p.id" class="plugin-card">
                <div class="plugin-card-top">
                  <span class="cat-icon">🔗</span>
                  <div style="flex:1;min-width:0">
                    <div class="plugin-name">{{ p.name }}</div>
                    <el-tag size="small" type="warning" effect="plain" style="margin-top:4px">Webhook</el-tag>
                  </div>
                  <el-switch :model-value="p.enabled" @change="togglePlugin(p)" />
                </div>
                <div class="plugin-desc">{{ p.description }}</div>
                <div class="plugin-desc" style="font-size:11px;color:#aaa;word-break:break-all">{{ p.endpoint }}</div>
                <div class="plugin-card-foot">
                  <el-button size="small" plain @click="openConfigure(p)">設定</el-button>
                  <el-button size="small" plain @click="testPlugin(p)">測試</el-button>
                  <el-button size="small" type="danger" plain @click="confirmDelete(p)">刪除</el-button>
                </div>
              </div>
            </div>
          </div>
          <el-empty v-if="!installedPlugins.length" description="尚未安裝任何插件，前往「插件目錄」一鍵安裝" />
        </template>
      </el-tab-pane>

      <!-- ── 插件目錄 ──────────────────────────── -->
      <el-tab-pane name="catalog" label="插件目錄">
        <div v-if="loadingCatalog" class="loading-wrap">
          <el-skeleton :rows="3" animated style="width:320px" />
        </div>
        <template v-else>
          <div class="catalog-filter">
            <el-radio-group v-model="filterCat" size="small">
              <el-radio-button value="">全部</el-radio-button>
              <el-radio-button v-for="c in catalogCategories" :key="c" :value="c">
                {{ CATEGORY_LABELS[c] || c }}
              </el-radio-button>
            </el-radio-group>
          </div>
          <div v-for="(group, cat) in filteredCatalogByCategory" :key="cat" class="category-section">
            <div v-if="group.length">
              <div class="category-label">{{ CATEGORY_LABELS[cat] || cat }}</div>
              <div class="card-grid">
                <div
                  v-for="item in group"
                  :key="item.key"
                  class="catalog-card"
                  :class="{ 'catalog-card--planned': item.planned }"
                >
                  <div class="catalog-card-top">
                    <span class="cat-icon">{{ item.icon }}</span>
                    <div style="flex:1;min-width:0">
                      <div class="catalog-name">{{ item.name }}</div>
                      <el-tag v-if="item.planned" size="small" type="info" style="margin-top:4px">規劃中</el-tag>
                      <el-tag v-else-if="isInstalled(item.key)" size="small" type="success" style="margin-top:4px">已安裝</el-tag>
                      <el-tag v-else size="small" type="primary" style="margin-top:4px">AI 可調動</el-tag>
                    </div>
                  </div>
                  <div class="catalog-desc">{{ item.description }}</div>
                  <div v-if="item.actions?.length" class="catalog-actions-list">
                    <el-tag v-for="a in item.actions" :key="a" size="small" effect="plain" style="margin:2px">{{ a }}</el-tag>
                  </div>
                  <div class="catalog-card-foot">
                    <el-button v-if="!item.planned && !isInstalled(item.key)" type="primary" size="small" :loading="installing[item.key]" @click="installBuiltin(item)">安裝</el-button>
                    <el-button v-else-if="!item.planned && isInstalled(item.key)" size="small" @click="openConfigureByKey(item.key)">設定</el-button>
                    <span v-else class="planned-text">即將推出</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </template>
      </el-tab-pane>
    </el-tabs>

    <!-- ── Configure Dialog ── -->
    <el-dialog v-model="showConfigDialog" :title="`設定：${configTarget?.name || ''}`" width="520px" destroy-on-close>
      <el-form label-width="130px" size="default">
        <el-form-item label="名稱"><el-input v-model="configForm.name" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="configForm.description" type="textarea" :rows="2" /></el-form-item>
        <template v-if="configTarget?.plugin_type === 'webhook'">
          <el-form-item label="端點 URL"><el-input v-model="configForm.endpoint" placeholder="https://..." /></el-form-item>
          <el-form-item label="Auth Header"><el-input v-model="configForm.auth_header" show-password /></el-form-item>
        </template>
        <template v-else>
          <el-form-item v-for="field in configFields" :key="field.key" :label="field.label">
            <el-select v-if="field.type === 'select'" v-model="configForm.plugin_config[field.key]" style="width:100%">
              <el-option v-for="o in field.options" :key="o" :label="o" :value="o" />
            </el-select>
            <el-input v-else-if="field.type === 'textarea'" v-model="configForm.plugin_config[field.key]" type="textarea" :rows="3" :placeholder="field.placeholder || ''" />
            <div v-else>
              <el-input v-model="configForm.plugin_config[field.key]" :type="field.type === 'password' ? 'password' : 'text'" :placeholder="field.placeholder || field.help || ''" :show-password="field.type === 'password'" />
              <div v-if="field.help" class="field-help">{{ field.help }}</div>
            </div>
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="showConfigDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveConfig">儲存</el-button>
      </template>
    </el-dialog>

    <!-- ── Webhook Create Dialog ── -->
    <el-dialog v-model="showWebhookDialog" title="新增 Webhook 插件" width="480px" destroy-on-close>
      <el-form :model="webhookForm" label-width="100px">
        <el-form-item label="名稱" required><el-input v-model="webhookForm.name" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="webhookForm.description" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="端點 URL" required><el-input v-model="webhookForm.endpoint" placeholder="https://..." /></el-form-item>
        <el-form-item label="Auth Header"><el-input v-model="webhookForm.auth_header" show-password /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showWebhookDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="createWebhook">新增</el-button>
      </template>
    </el-dialog>

    <!-- ── Test Dialog ── -->
    <el-dialog v-model="showTestDialog" :title="`測試：${testTarget?.name || ''}`" width="500px" destroy-on-close>
      <el-form label-width="80px">
        <el-form-item label="Action"><el-input v-model="testForm.action" placeholder="action 名稱（選填）" /></el-form-item>
        <el-form-item label="參數 JSON"><el-input v-model="testForm.params" type="textarea" :rows="4" placeholder='{"query": "你好"}' /></el-form-item>
      </el-form>
      <div v-if="testResult !== null" class="test-result">
        <pre>{{ typeof testResult === 'string' ? testResult : JSON.stringify(testResult, null, 2) }}</pre>
      </div>
      <template #footer>
        <el-button @click="showTestDialog = false">關閉</el-button>
        <el-button type="primary" :loading="testing" @click="runTest">執行測試</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted } from 'vue'
import { pluginsApi } from '../api/index.js'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'

const CATEGORY_LABELS = {
  productivity: '生產力', data: '數據分析', utility: '工具',
  dev: '開發工具', visualization: '視覺化',
}

const activeTab        = ref('installed')
const installedPlugins = ref([])
const catalog          = ref([])
const loadingInstalled = ref(false)
const loadingCatalog   = ref(false)
const filterCat        = ref('')
const installing       = reactive({})
const saving           = ref(false)
const creating         = ref(false)
const testing          = ref(false)
const showConfigDialog  = ref(false)
const showWebhookDialog = ref(false)
const showTestDialog    = ref(false)
const configTarget      = ref(null)
const testTarget        = ref(null)
const testResult        = ref(null)
const configForm  = reactive({ name: '', description: '', endpoint: '', auth_header: '', plugin_config: {} })
const webhookForm = reactive({ name: '', description: '', endpoint: '', auth_header: '' })
const testForm    = reactive({ action: '', params: '{}' })

onMounted(() => { loadInstalled(); loadCatalog() })

async function loadInstalled() {
  loadingInstalled.value = true
  try { installedPlugins.value = await pluginsApi.list() }
  catch { ElMessage.error('載入插件失敗') }
  finally { loadingInstalled.value = false }
}

async function loadCatalog() {
  loadingCatalog.value = true
  try { catalog.value = await pluginsApi.catalog() }
  catch { catalog.value = [] }
  finally { loadingCatalog.value = false }
}

const getCatalogEntry = (key) => catalog.value.find(c => c.key === key) || null

const installedByCategory = computed(() => {
  const g = {}
  for (const p of installedPlugins.value) {
    if (p.plugin_type !== 'builtin') continue
    const cat = getCatalogEntry(p.builtin_key)?.category || 'other'
    if (!g[cat]) g[cat] = []
    g[cat].push(p)
  }
  return g
})

const installedUncategorized = computed(() =>
  installedPlugins.value.filter(p => p.plugin_type !== 'builtin')
)

const isInstalled = (key) => installedPlugins.value.some(p => p.builtin_key === key)

const catalogCategories = computed(() => {
  const cats = new Set(catalog.value.filter(c => !c.planned).map(c => c.category))
  return [...cats]
})

const filteredCatalogByCategory = computed(() => {
  const items = filterCat.value ? catalog.value.filter(c => c.category === filterCat.value) : catalog.value
  const g = {}
  for (const item of items) {
    if (!g[item.category]) g[item.category] = []
    g[item.category].push(item)
  }
  return g
})

const configFields = computed(() => {
  if (!configTarget.value || configTarget.value.plugin_type !== 'builtin') return []
  return getCatalogEntry(configTarget.value.builtin_key)?.config_fields || []
})

async function togglePlugin(plugin) {
  try {
    await pluginsApi.toggle(plugin.id)
    plugin.enabled = !plugin.enabled
  } catch (e) {
    ElMessage.error(e.message)
    await loadInstalled()
  }
}

function openConfigure(plugin) {
  configTarget.value = plugin
  Object.assign(configForm, {
    name: plugin.name, description: plugin.description || '',
    endpoint: plugin.endpoint || '', auth_header: '',
    plugin_config: { ...(plugin.plugin_config || {}) },
  })
  showConfigDialog.value = true
}

function openConfigureByKey(key) {
  const plugin = installedPlugins.value.find(p => p.builtin_key === key)
  if (plugin) { openConfigure(plugin); activeTab.value = 'installed' }
}

async function saveConfig() {
  saving.value = true
  try {
    const body = { name: configForm.name, description: configForm.description }
    if (configTarget.value.plugin_type === 'webhook') {
      body.endpoint = configForm.endpoint
      if (configForm.auth_header) body.auth_header = configForm.auth_header
    } else {
      body.plugin_config = { ...configForm.plugin_config }
      const entry = getCatalogEntry(configTarget.value.builtin_key)
      if (entry) {
        for (const f of entry.config_fields) {
          if (f.type === 'password') {
            const val = body.plugin_config[f.key]
            if (val) { body.auth_header = val; delete body.plugin_config[f.key] }
          }
        }
      }
    }
    const updated = await pluginsApi.update(configTarget.value.id, body)
    const idx = installedPlugins.value.findIndex(p => p.id === updated.id)
    if (idx >= 0) installedPlugins.value[idx] = updated
    showConfigDialog.value = false
    ElMessage.success('設定已儲存')
  } catch (e) {
    ElMessage.error(e.message || '儲存失敗')
  } finally {
    saving.value = false
  }
}

async function confirmDelete(plugin) {
  try {
    await ElMessageBox.confirm(`確定刪除插件「${plugin.name}」？`, '刪除確認', {
      type: 'warning', confirmButtonText: '刪除', cancelButtonText: '取消',
    })
    await pluginsApi.delete(plugin.id)
    await loadInstalled()
    ElMessage.success('已刪除')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.message || '刪除失敗')
  }
}

function openWebhookDialog() {
  Object.assign(webhookForm, { name: '', description: '', endpoint: '', auth_header: '' })
  showWebhookDialog.value = true
}

async function createWebhook() {
  if (!webhookForm.name || !webhookForm.endpoint) { ElMessage.warning('名稱和端點為必填'); return }
  creating.value = true
  try {
    await pluginsApi.create({
      name: webhookForm.name, description: webhookForm.description,
      plugin_type: 'webhook', endpoint: webhookForm.endpoint,
      auth_header: webhookForm.auth_header || null,
    })
    showWebhookDialog.value = false
    await loadInstalled()
    ElMessage.success('Webhook 插件已新增')
    activeTab.value = 'installed'
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    creating.value = false
  }
}

async function installBuiltin(catalogItem) {
  installing[catalogItem.key] = true
  try {
    await pluginsApi.create({
      name: catalogItem.name, description: catalogItem.description,
      plugin_type: 'builtin', builtin_key: catalogItem.key, enabled: true,
    })
    await loadInstalled()
    ElMessage.success(`「${catalogItem.name}」已安裝`)
    if (catalogItem.config_fields?.length) {
      const plugin = installedPlugins.value.find(p => p.builtin_key === catalogItem.key)
      if (plugin) openConfigure(plugin)
    }
    activeTab.value = 'installed'
  } catch (e) {
    ElMessage.error(e.message || '安裝失敗')
  } finally {
    installing[catalogItem.key] = false
  }
}

function testPlugin(plugin) {
  testTarget.value = plugin
  testResult.value = null
  testForm.action = getCatalogEntry(plugin.builtin_key)?.actions?.[0] || ''
  testForm.params = '{}'
  showTestDialog.value = true
}

async function runTest() {
  testing.value = true; testResult.value = null
  try {
    let payload = {}
    try { payload = JSON.parse(testForm.params) } catch { payload = { query: testForm.params } }
    if (testForm.action) payload.action = testForm.action
    testResult.value = await pluginsApi.invoke(testTarget.value.id, payload)
  } catch (e) {
    testResult.value = `錯誤：${e.message}`
  } finally {
    testing.value = false
  }
}
</script>

<style scoped>
.plugins-root { padding: 24px; max-width: 1280px; }
.plugins-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
.page-title   { font-size: 20px; font-weight: 600; margin: 0 0 4px; }
.page-subtitle { font-size: 13px; color: #888; margin: 0; }
.plugins-tabs { margin-top: 4px; }
.loading-wrap { display: flex; gap: 16px; flex-wrap: wrap; margin-top: 16px; }
.category-section { margin-bottom: 28px; }
.category-label {
  font-size: 12px; font-weight: 600; color: #888;
  text-transform: uppercase; letter-spacing: .5px;
  margin-bottom: 12px; padding-left: 2px;
}
.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
.plugin-card, .catalog-card {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 10px; padding: 16px;
  display: flex; flex-direction: column; gap: 8px;
  transition: box-shadow .2s;
}
.plugin-card:hover, .catalog-card:hover { box-shadow: 0 2px 12px rgba(0,0,0,.08); }
.catalog-card--planned { opacity: .6; }
.plugin-card-top, .catalog-card-top { display: flex; align-items: flex-start; gap: 12px; }
.cat-icon     { font-size: 28px; line-height: 1; flex-shrink: 0; }
.plugin-name, .catalog-name { font-size: 15px; font-weight: 600; }
.plugin-desc, .catalog-desc { font-size: 13px; color: #666; line-height: 1.5; flex: 1; }
.plugin-card-foot, .catalog-card-foot { margin-top: auto; padding-top: 8px; display: flex; gap: 6px; flex-wrap: wrap; }
.catalog-actions-list { display: flex; flex-wrap: wrap; gap: 2px; }
.planned-text { font-size: 12px; color: #aaa; }
.catalog-filter { margin-bottom: 16px; }
.test-result { margin-top: 14px; background: var(--el-fill-color-light); border-radius: 6px; padding: 12px; max-height: 260px; overflow-y: auto; }
.test-result pre { margin: 0; font-size: 12px; white-space: pre-wrap; word-break: break-all; }
.field-help { font-size: 11px; color: #999; margin-top: 4px; }
.tab-badge :deep(.el-badge__content) { top: -4px; }
</style>
