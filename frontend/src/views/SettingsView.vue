<template>
  <div style="padding:24px;">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:24px;">
      <h2 style="font-size:20px;margin:0;">設定</h2>
      <el-button :icon="Refresh" circle title="重新整理頁面" @click="reloadPage" />
    </div>

    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <!-- Model Providers Tab -->
      <el-tab-pane label="模型提供者" name="list">
        <!-- Provider Cards -->
        <div class="provider-grid">
          <div class="provider-card" :class="{ active: selectedProvider === null }" @click="selectedProvider = null">
            <div class="pcard-icon">🗂</div>
            <div class="pcard-name">全部</div>
            <div class="pcard-count">{{ models.length }} 個模型</div>
          </div>
          <div v-for="p in PROVIDER_DEFS" :key="p.key"
               class="provider-card" :class="{ active: selectedProvider === p.key }"
               @click="selectedProvider = p.key">
            <div class="pcard-icon">{{ p.icon }}</div>
            <div class="pcard-name">{{ p.name }}</div>
            <div class="pcard-types">
              <el-tag v-for="t in p.types" :key="t" size="small"
                :type="t === 'embedding' ? 'success' : t === 'rerank' ? 'warning' : ''"
                style="margin:2px 2px 0 0;">{{ t }}</el-tag>
            </div>
            <div class="pcard-count">{{ providerCount(p.key) }} 個模型</div>
            <el-button size="small" type="primary" plain style="margin-top:8px;width:100%;"
              @click.stop="openNewDialogForProvider(p.key)">+ 新增</el-button>
          </div>
        </div>

        <!-- Toolbar -->
        <div style="display:flex;gap:10px;margin-top:20px;margin-bottom:12px;align-items:center;">
          <span style="font-size:14px;font-weight:500;">
            {{ selectedProvider ? (PROVIDER_DEFS.find(p => p.key === selectedProvider)?.name || selectedProvider) : '全部模型' }}
            （{{ filteredModels.length }}）
          </span>
          <el-input v-model="searchQ" placeholder="搜尋模型名稱..." style="width:190px;" clearable @input="loadModels" />
          <el-button type="primary" @click="openNewDialog">新增模型</el-button>
        </div>

        <!-- Model Table -->
        <el-table :data="filteredModels" v-loading="loading" stripe style="width:100%;" empty-text="尚無模型">
          <el-table-column label="名稱" prop="name" min-width="160" />
          <el-table-column label="類型" width="100" align="center">
            <template #default="{ row }">
              <el-tag size="small"
                :type="row.model_type === 'embedding' ? 'success' : row.model_type === 'rerank' ? 'warning' : ''">
                {{ row.model_type || 'chat' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="Provider" min-width="120">
            <template #default="{ row }">
              {{ PROVIDER_DEFS.find(p => p.key === row.provider)?.icon || '❓' }}
              {{ PROVIDER_DEFS.find(p => p.key === row.provider)?.name || row.provider || '-' }}
            </template>
          </el-table-column>
          <el-table-column label="Max tokens" width="110" align="center">
            <template #default="{ row }">{{ row.max_tokens ? row.max_tokens.toLocaleString() : '-' }}</template>
          </el-table-column>
          <el-table-column label="Vision" width="70" align="center">
            <template #default="{ row }">
              <el-icon v-if="row.vision_support" color="#67c23a"><Check /></el-icon>
              <span v-else style="color:#ccc;">—</span>
            </template>
          </el-table-column>
          <el-table-column label="Context" width="90" align="center">
            <template #default="{ row }">{{ row.context_length ? row.context_length.toLocaleString() : '-' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="120" align="center">
            <template #default="{ row }">
              <el-button size="small" type="primary" plain @click="openEdit(row)">編輯</el-button>
              <el-popconfirm title="刪除此模型？" @confirm="deleteModel(row.id)">
                <template #reference>
                  <el-button size="small" type="danger" plain>刪</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 模型比較 Tab (第二階段) -->
      <el-tab-pane v-if="false" label="模型比較" name="compare">
        <div style="display:flex;gap:20px;margin-bottom:20px;align-items:center;">
          <div>
            <div style="font-size:13px;color:#666;margin-bottom:6px;">模型 A</div>
            <el-select v-model="compareA" placeholder="選擇模型 A" style="width:200px;">
              <el-option v-for="m in models" :key="m.id" :label="m.name" :value="m.id" />
            </el-select>
          </div>
          <div>
            <div style="font-size:13px;color:#666;margin-bottom:6px;">模型 B</div>
            <el-select v-model="compareB" placeholder="選擇模型 B" style="width:200px;">
              <el-option v-for="m in models" :key="m.id" :label="m.name" :value="m.id" />
            </el-select>
          </div>
          <el-button type="primary" :disabled="!compareA || !compareB" @click="doCompare" style="margin-top:20px;">比較</el-button>
        </div>

        <div v-if="compareResult" style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
          <ModelCard :model="compareResult.model_a" label="模型 A" />
          <ModelCard :model="compareResult.model_b" label="模型 B" />
        </div>
        <div v-else-if="compareLoading" style="text-align:center;padding:40px;"><el-icon class="is-loading"><Loading /></el-icon></div>
        <div v-else style="text-align:center;color:#bbb;padding:40px;font-size:14px;">選擇兩個模型後點擊「比較」</div>
      </el-tab-pane>

      <!-- 雲端 API 設定 Tab (第二階段) -->
      <el-tab-pane v-if="false" label="雲端 API 設定" name="api">
        <div v-loading="apiLoading" style="max-width:560px;">
          <el-alert type="info" :closable="false" style="margin-bottom:20px;">
            切換 LLM Provider 後對話頁即會使用新的服務，無需重啟。Ollama 嵌入模型不受影響。
          </el-alert>

          <el-form :model="apiForm" label-width="130px" label-position="left">
            <!-- Provider -->
            <el-form-item label="LLM Provider">
              <el-select v-model="apiForm.llm_provider" style="width:220px;">
                <el-option value="ollama"     label="🏠 Ollama（本地）" />
                <el-option value="groq"       label="⚡ Groq（免費額度）" />
                <el-option value="openai"     label="🤖 OpenAI" />
                <el-option value="gemini"     label="💎 Google Gemini" />
                <el-option value="openrouter" label="🌐 OpenRouter" />
              </el-select>
            </el-form-item>

            <!-- Cloud model override -->
            <el-form-item label="模型名稱（選填）">
              <el-input v-model="apiForm.cloud_llm_model"
                :placeholder="providerDefaultModel"
                style="width:320px;" clearable />
              <div style="font-size:12px;color:#999;margin-top:4px;">留空使用預設：{{ providerDefaultModel }}</div>
            </el-form-item>

            <!-- Groq -->
            <template v-if="apiForm.llm_provider === 'groq'">
              <el-form-item label="Groq API Key">
                <el-input v-model="apiForm.groq_api_key" type="password" show-password
                  :placeholder="maskedKeys.groq || '貼上 API Key...'" style="width:320px;" />
                <el-link href="https://console.groq.com" target="_blank" style="margin-left:8px;font-size:12px;">申請免費 Key ↗</el-link>
              </el-form-item>
            </template>

            <!-- OpenAI -->
            <template v-if="apiForm.llm_provider === 'openai'">
              <el-form-item label="OpenAI API Key">
                <el-input v-model="apiForm.openai_api_key" type="password" show-password
                  :placeholder="maskedKeys.openai || 'sk-...'" style="width:320px;" />
                <el-link href="https://platform.openai.com/api-keys" target="_blank" style="margin-left:8px;font-size:12px;">取得 Key ↗</el-link>
              </el-form-item>
            </template>

            <!-- Gemini -->
            <template v-if="apiForm.llm_provider === 'gemini'">
              <el-form-item label="Gemini API Key">
                <el-input v-model="apiForm.gemini_api_key" type="password" show-password
                  :placeholder="maskedKeys.gemini || 'AIzaSy...'" style="width:320px;" />
                <el-link href="https://aistudio.google.com/app/apikey" target="_blank" style="margin-left:8px;font-size:12px;">取得 Key ↗</el-link>
              </el-form-item>
            </template>

            <!-- OpenRouter -->
            <template v-if="apiForm.llm_provider === 'openrouter'">
              <el-form-item label="OpenRouter API Key">
                <el-input v-model="apiForm.openrouter_api_key" type="password" show-password
                  :placeholder="maskedKeys.openrouter || 'sk-or-...'" style="width:320px;" />
                <el-link href="https://openrouter.ai/keys" target="_blank" style="margin-left:8px;font-size:12px;">申請（有免費模型）↗</el-link>
              </el-form-item>
            </template>

            <el-form-item>
              <el-button type="primary" :loading="apiSaving" @click="saveApiSettings">儲存設定</el-button>
              <el-button
                v-if="apiForm.llm_provider !== 'ollama'"
                :loading="apiTesting"
                @click="testConnection">
                測試連線
              </el-button>
              <el-tag v-if="testResult === true" type="success" style="margin-left:8px;">✓ 連線成功</el-tag>
              <el-tag v-if="testResult === false" type="danger" style="margin-left:8px;">✗ 連線失敗</el-tag>
            </el-form-item>
          </el-form>

          <el-alert v-if="testError" type="error" :closable="false" :description="testError" style="margin-top:12px;" />
        </div>
      </el-tab-pane>

      <!-- RAG 參數 Tab -->
      <el-tab-pane label="RAG 參數" name="rag">
        <div v-loading="ragLoading" style="max-width:520px;">
          <el-alert type="info" :closable="false" style="margin-bottom:20px;">
            調整後立即生效（下一次查詢即使用新參數），無需重啟服務。
          </el-alert>
          <el-form :model="ragForm" label-width="160px" label-position="left">
            <el-form-item label="初次召回數（top_k）">
              <el-input-number v-model="ragForm.rag_top_k" :min="1" :max="100" :step="5" style="width:150px;" />
              <span style="margin-left:10px;font-size:12px;color:#999;">Qdrant 向量搜索返回筆數</span>
            </el-form-item>
            <el-form-item label="Rerank 保留數">
              <el-input-number v-model="ragForm.rag_rerank_top_k" :min="1" :max="20" :step="1" style="width:150px;" />
              <span style="margin-left:10px;font-size:12px;color:#999;">Re-ranker 精排後送入 LLM 的筆數</span>
            </el-form-item>
            <el-form-item label="Context 上限（字元）">
              <el-input-number v-model="ragForm.rag_max_context_chars" :min="500" :max="32000" :step="500" style="width:150px;" />
              <span style="margin-left:10px;font-size:12px;color:#999;">送給 LLM 的參考資料總長度上限</span>
            </el-form-item>
            <el-form-item label="啟用 Re-ranker">
              <el-switch v-model="ragForm.rag_rerank_enabled"
                active-text="啟用（BGE Re-ranker）"
                inactive-text="停用（直接取 top_k 筆）" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="ragSaving" @click="saveRagSettings">儲存設定</el-button>
              <el-button @click="loadRagSettings">重置</el-button>
            </el-form-item>
          </el-form>
        </div>
      </el-tab-pane>

      <!-- 備份管理 Tab (第二階段) -->
      <el-tab-pane v-if="false" label="備份管理" name="backup">
        <div style="max-width:720px;">
          <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px;">
            <el-button type="primary" :loading="backupTriggering" @click="triggerBackup">立即備份</el-button>
            <el-button :loading="backupListLoading" @click="loadBackupList" :icon="Refresh">重新整理</el-button>
            <span style="font-size:12px;color:#999;">備份範圍：系統設定、模型庫、Qdrant 快照</span>
          </div>
          <el-alert v-if="backupTriggerMsg" :type="backupTriggerOk ? 'success' : 'error'"
            :description="backupTriggerMsg" :closable="false" style="margin-bottom:16px;" />

          <el-table :data="backupFiles" v-loading="backupListLoading" stripe style="width:100%;" empty-text="尚無備份記錄">
            <el-table-column label="檔案名稱" prop="name" min-width="240" />
            <el-table-column label="大小" width="100" align="right">
              <template #default="{ row }">{{ row.size ? (row.size / 1024).toFixed(1) + ' KB' : '-' }}</template>
            </el-table-column>
            <el-table-column label="備份時間" min-width="180">
              <template #default="{ row }">{{ row.last_modified ? new Date(row.last_modified).toLocaleString('zh-TW') : '-' }}</template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <!-- 使用者設定 Tab -->
      <el-tab-pane label="使用者設定" name="user">
        <div style="max-width:480px;">
          <!-- 帳號資訊 -->
          <el-card style="margin-bottom:20px;">
            <template #header><b>帳號資訊</b></template>
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="Email">{{ userEmail }}</el-descriptions-item>
              <el-descriptions-item label="角色">
                <el-tag :type="userRole === 'admin' ? 'danger' : 'info'" size="small">{{ userRole }}</el-tag>
              </el-descriptions-item>
            </el-descriptions>
          </el-card>

          <!-- 修改密碼 -->
          <el-card>
            <template #header><b>修改密碼</b></template>
            <el-form :model="pwdForm" label-width="110px" label-position="left">
              <el-form-item label="目前密碼">
                <el-input v-model="pwdForm.current_password" type="password" show-password style="width:260px;" />
              </el-form-item>
              <el-form-item label="新密碼">
                <el-input v-model="pwdForm.new_password" type="password" show-password style="width:260px;" />
                <div style="font-size:12px;color:#999;margin-top:4px;">至少 8 個字元</div>
              </el-form-item>
              <el-form-item label="確認新密碼">
                <el-input v-model="pwdForm.confirm_password" type="password" show-password style="width:260px;" />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :loading="pwdSaving" @click="changePassword">更新密碼</el-button>
              </el-form-item>
            </el-form>
          </el-card>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- Add / Edit Dialog -->
    <el-dialog v-model="showAddDialog" :title="editingId ? '編輯模型' : '新增模型'" width="600px" @closed="onDialogClosed">
      <el-form :model="modelForm" label-width="110px">
        <el-form-item label="Provider" required>
          <el-select v-model="modelForm.provider" style="width:220px;" @change="onProviderChange">
            <el-option v-for="p in PROVIDER_DEFS" :key="p.key" :label="p.icon + ' ' + p.name" :value="p.key" />
          </el-select>
        </el-form-item>
        <el-form-item label="模型類型">
          <el-select v-model="modelForm.model_type" style="width:220px;">
            <el-option value="chat"      label="💬 Chat（對話）" />
            <el-option value="embedding" label="📐 Embedding（嵌入）" />
            <el-option value="rerank"    label="🔄 Re-rank（重排）" />
          </el-select>
        </el-form-item>
        <el-form-item label="模型名稱" required>
          <el-input v-model="modelForm.name" placeholder="如: qwen2.5:7b 或 gpt-4o" />
        </el-form-item>
        <el-form-item v-if="modelForm.provider === 'ollama'" label="Base URL">
          <el-input v-model="modelForm.base_url" placeholder="http://ollama:11434" />
        </el-form-item>
        <el-form-item v-if="modelForm.provider !== 'ollama'" label="API Key">
          <el-input v-model="modelForm._api_key" type="password" show-password
            placeholder="填入 API Key（不儲存至資料庫）" />
          <div style="font-size:11px;color:#999;margin-top:3px;">僅用於驗證，不儲存至資料庫</div>
        </el-form-item>
        <el-form-item label="Max tokens">
          <el-input-number v-model="modelForm.max_tokens" :min="512" :step="1024" style="width:160px;" />
        </el-form-item>
        <el-form-item v-if="modelForm.model_type === 'chat'" label="支援 Vision？">
          <el-switch v-model="modelForm.vision_support" active-text="是" inactive-text="否" />
        </el-form-item>
        <el-form-item label="">
          <el-button :loading="verifying" @click="verifyModel">🔗 驗證連線</el-button>
          <el-tag v-if="verifyStatus === 'ok'"   type="success" style="margin-left:8px;">{{ verifyMsg }}</el-tag>
          <el-tag v-if="verifyStatus === 'fail'" type="danger"  style="margin-left:8px;">{{ verifyMsg }}</el-tag>
        </el-form-item>
        <el-divider>進階資訊（選填）</el-divider>
        <el-form-item label="Family"><el-input v-model="modelForm.family" /></el-form-item>
        <el-form-item label="開發者"><el-input v-model="modelForm.developer" /></el-form-item>
        <el-form-item label="參數(B)"><el-input-number v-model="modelForm.params_b" :precision="1" :step="0.5" /></el-form-item>
        <el-form-item label="Context 長度"><el-input-number v-model="modelForm.context_length" :step="1024" /></el-form-item>
        <el-form-item label="License"><el-input v-model="modelForm.license" /></el-form-item>
        <el-form-item v-if="modelForm.provider === 'ollama'" label="Ollama ID">
          <el-input v-model="modelForm.ollama_id" />
        </el-form-item>
        <el-form-item label="HF ID"><el-input v-model="modelForm.hf_id" /></el-form-item>
        <el-form-item label="Tags">
          <el-input v-model="modelForm.tags_str" placeholder="逗號分隔，如: llm,chat,code" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveModel">儲存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive, defineComponent, computed } from 'vue'
import { Refresh, Check } from '@element-plus/icons-vue'
import { wikiApi, systemSettingsApi } from '../api/index.js'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth.js'

const authStore = useAuthStore()
const userEmail = computed(() => authStore.userEmail)
const userRole  = computed(() => authStore.userRole)

// Inline ModelCard component
const ModelCard = defineComponent({
  props: { model: Object, label: String },
  template: `
    <el-card>
      <template #header><b>{{ label }}: {{ model?.name }}</b></template>
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item label="Family">{{ model?.family || '-' }}</el-descriptions-item>
        <el-descriptions-item label="開發者">{{ model?.developer || '-' }}</el-descriptions-item>
        <el-descriptions-item label="參數">{{ model?.params_b ? model.params_b + 'B' : '-' }}</el-descriptions-item>
        <el-descriptions-item label="Context">{{ model?.context_length ? model.context_length.toLocaleString() : '-' }}</el-descriptions-item>
        <el-descriptions-item label="License">{{ model?.license || '-' }}</el-descriptions-item>
        <el-descriptions-item label="Ollama ID">{{ model?.ollama_id || '-' }}</el-descriptions-item>
        <el-descriptions-item label="HF ID">{{ model?.hf_id || '-' }}</el-descriptions-item>
        <el-descriptions-item label="Tags">{{ model?.tags?.join(', ') || '-' }}</el-descriptions-item>
      </el-descriptions>
    </el-card>
  `,
})

// ── 頁面刷新 ─────────────────────────────────────────────────────────────────
function reloadPage() {
  window.location.reload()
}

// ── Tab 切換 ──────────────────────────────────────────────────────────────────
const activeTab = ref('list')
function onTabChange(tab) {
  if (tab === 'rag') loadRagSettings()
}

// ── Model List ────────────────────────────────────────────────────────────────
const models = ref([])
const loading = ref(false)
const searchQ = ref('')
const PROVIDER_DEFS = [
  { key: 'ollama',     name: 'Ollama',     icon: '🏠', types: ['chat', 'embedding'] },
  { key: 'openai',     name: 'OpenAI',     icon: '🤖', types: ['chat', 'embedding'] },
  { key: 'groq',       name: 'Groq',       icon: '⚡', types: ['chat'] },
  { key: 'gemini',     name: 'Gemini',     icon: '💎', types: ['chat'] },
  { key: 'openrouter', name: 'OpenRouter', icon: '🌐', types: ['chat'] },
]
const selectedProvider = ref(null)
const filteredModels = computed(() => {
  if (!selectedProvider.value) return models.value
  return models.value.filter(m => m.provider === selectedProvider.value)
})
const providerCount = (key) => models.value.filter(m => m.provider === key).length
const showAddDialog = ref(false)
const saving = ref(false)
const editingId = ref(null)

const compareA = ref('')
const compareB = ref('')
const compareResult = ref(null)
const compareLoading = ref(false)

const modelForm = reactive({
  name: '', family: '', developer: '', params_b: null,
  context_length: null, license: '', ollama_id: '', hf_id: '', tags_str: '',
  model_type: 'chat', max_tokens: null, vision_support: false,
  provider: 'ollama', base_url: '',
  _api_key: '',
})

onMounted(loadModels)

async function loadModels() {
  loading.value = true
  try {
    models.value = await wikiApi.list(searchQ.value)
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

function openNewDialog() {
  editingId.value = null
  const prov = selectedProvider.value || 'ollama'
  Object.assign(modelForm, {
    name: '', family: '', developer: '', params_b: null,
    context_length: null, license: '', ollama_id: '', hf_id: '',
    tags_str: '', _api_key: '',
    model_type: 'chat', max_tokens: null, vision_support: false,
    provider: prov, base_url: prov === 'ollama' ? 'http://ollama:11434' : '',
  })
  verifyStatus.value = ''
  verifyMsg.value = ''
  showAddDialog.value = true
}

function openNewDialogForProvider(providerKey) {
  openNewDialog()
  modelForm.provider = providerKey
  modelForm.base_url = providerKey === 'ollama' ? 'http://ollama:11434' : ''
}

function openEdit(row) {
  editingId.value = row.id
  Object.assign(modelForm, {
    name: row.name, family: row.family || '', developer: row.developer || '',
    params_b: row.params_b, context_length: row.context_length,
    license: row.license || '', ollama_id: row.ollama_id || '',
    hf_id: row.hf_id || '', tags_str: (row.tags || []).join(', '), _api_key: '',
    model_type: row.model_type || 'chat',
    max_tokens: row.max_tokens || null,
    vision_support: row.vision_support || false,
    provider: row.provider || 'ollama',
    base_url: row.base_url || '',
  })
  verifyStatus.value = ''
  verifyMsg.value = ''
  showAddDialog.value = true
}

function onDialogClosed() {
  modelForm._api_key = ''
  editingId.value = null
  verifyStatus.value = ''
  verifyMsg.value = ''
}

// ── Verify ──────────────────────────────────────────────────────────────────────────────
const verifying    = ref(false)
const verifyStatus = ref('')
const verifyMsg    = ref('')

function onProviderChange(val) {
  if (val === 'ollama' && !modelForm.base_url) modelForm.base_url = 'http://ollama:11434'
  verifyStatus.value = ''
  verifyMsg.value = ''
}

async function verifyModel() {
  if (!modelForm.name) { ElMessage.warning('請先填入模型名稱'); return }
  verifying.value = true
  verifyStatus.value = ''
  verifyMsg.value = ''
  try {
    const res = await wikiApi.verifyModel({
      provider:   modelForm.provider,
      model_name: modelForm.name,
      base_url:   modelForm.base_url || null,
      api_key:    modelForm._api_key || null,
    })
    verifyStatus.value = res.ok ? 'ok' : 'fail'
    verifyMsg.value    = res.message
  } catch (e) {
    verifyStatus.value = 'fail'
    verifyMsg.value    = e.message
  } finally {
    verifying.value = false
  }
}

async function saveModel() {
  if (!modelForm.name) { ElMessage.warning('名稱為必填'); return }
  saving.value = true
  try {
    const body = {
      ...modelForm,
      tags: modelForm.tags_str.split(',').map(t => t.trim()).filter(Boolean),
      benchmarks: {},
      quantizations: {},
    }
    delete body.tags_str
    delete body._api_key
    if (editingId.value) {
      await wikiApi.update(editingId.value, body)
    } else {
      await wikiApi.create(body)
    }
    showAddDialog.value = false
    editingId.value = null
    await loadModels()
    ElMessage.success('已儲存')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function deleteModel(id) {
  try {
    await wikiApi.delete(id)
    await loadModels()
    ElMessage.success('已刪除')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function doCompare() {
  compareLoading.value = true
  compareResult.value = null
  try {
    compareResult.value = await wikiApi.compare(compareA.value, compareB.value)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    compareLoading.value = false
  }
}

// ── Cloud API Settings ────────────────────────────────────────────────────────
const _DEFAULT_MODELS = {
  ollama:     'qwen2.5:14b（本地）',
  groq:       'llama-3.3-70b-versatile',
  openai:     'gpt-4o-mini',
  gemini:     'gemini-2.0-flash',
  openrouter: 'meta-llama/llama-3.3-70b-instruct:free',
}

const apiLoading = ref(false)
const apiSaving  = ref(false)
const apiTesting = ref(false)
const testResult = ref(null)   // true | false | null
const testError  = ref('')

const maskedKeys = reactive({ openai: '', groq: '', gemini: '', openrouter: '' })

const apiForm = reactive({
  llm_provider:      'ollama',
  cloud_llm_model:   '',
  openai_api_key:    null,
  groq_api_key:      null,
  gemini_api_key:    null,
  openrouter_api_key: null,
})

const providerDefaultModel = computed(() => _DEFAULT_MODELS[apiForm.llm_provider] || '')

async function loadApiSettings() {
  apiLoading.value = true
  try {
    const data = await systemSettingsApi.getLlm()
    apiForm.llm_provider    = data.llm_provider    || 'ollama'
    apiForm.cloud_llm_model = data.cloud_llm_model || ''
    maskedKeys.openai       = data.openai_api_key_masked
    maskedKeys.groq         = data.groq_api_key_masked
    maskedKeys.gemini       = data.gemini_api_key_masked
    maskedKeys.openrouter   = data.openrouter_api_key_masked
  } catch (e) {
    console.error(e)
  } finally {
    apiLoading.value = false
  }
}

async function saveApiSettings() {
  apiSaving.value = true
  testResult.value = null
  testError.value = ''
  try {
    // 儲存前先記錄，避免 loadApiSettings 重設前遺失
    const savedProvider  = apiForm.llm_provider
    const savedModelName = apiForm.cloud_llm_model || providerDefaultModel.value

    await systemSettingsApi.saveLlm({
      llm_provider:      apiForm.llm_provider,
      cloud_llm_model:   apiForm.cloud_llm_model,
      openai_api_key:    apiForm.openai_api_key,
      groq_api_key:      apiForm.groq_api_key,
      gemini_api_key:    apiForm.gemini_api_key,
      openrouter_api_key: apiForm.openrouter_api_key,
    })
    ElMessage.success('設定已儲存，對話頁立即生效')
    // 重新載入遮罩
    await loadApiSettings()
    // 清空明文輸入（已儲存）
    apiForm.openai_api_key = null
    apiForm.groq_api_key = null
    apiForm.gemini_api_key = null
    apiForm.openrouter_api_key = null

    // ── 自動新增模型到模型清單（非 Ollama 本地模型才新增）────────────────────
    if (savedModelName && savedProvider !== 'ollama') {
      const _devMap = { openai: 'OpenAI', groq: 'Groq', gemini: 'Google', openrouter: 'OpenRouter' }
      try {
        const existing = await wikiApi.list(savedModelName)
        const alreadyExists = existing.find(m => m.name === savedModelName)
        if (!alreadyExists) {
          await wikiApi.create({
            name:      savedModelName,
            tags:      [savedProvider, 'cloud'],
            developer: _devMap[savedProvider] || savedProvider,
          })
          ElMessage.success(`已將 ${savedModelName} 新增至模型清單`)
          await loadModels()
        }
      } catch (_) { /* 新增失敗不影響主流程 */ }
    }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    apiSaving.value = false
  }
}

async function testConnection() {
  const provider = apiForm.llm_provider
  const key = apiForm[`${provider}_api_key`]
  if (!key) {
    ElMessage.warning('請先輸入 API Key 後再測試')
    return
  }
  apiTesting.value = true
  testResult.value = null
  testError.value = ''
  try {
    const res = await systemSettingsApi.testLlm(provider, key)
    testResult.value = res.ok
    if (!res.ok) testError.value = res.message
  } catch (e) {
    testResult.value = false
    testError.value = e.message
  } finally {
    apiTesting.value = false
  }
}

// ── RAG 參數 ──────────────────────────────────────────────────────────────────
const ragLoading = ref(false)
const ragSaving  = ref(false)
const ragForm = reactive({
  rag_top_k:             20,
  rag_rerank_top_k:      5,
  rag_max_context_chars: 4000,
  rag_rerank_enabled:    true,
})

async function loadRagSettings() {
  ragLoading.value = true
  try {
    const data = await systemSettingsApi.getRag()
    ragForm.rag_top_k             = data.rag_top_k
    ragForm.rag_rerank_top_k      = data.rag_rerank_top_k
    ragForm.rag_max_context_chars = data.rag_max_context_chars
    ragForm.rag_rerank_enabled    = data.rag_rerank_enabled
  } catch (e) {
    console.error(e)
  } finally {
    ragLoading.value = false
  }
}

async function saveRagSettings() {
  ragSaving.value = true
  try {
    await systemSettingsApi.saveRag({ ...ragForm })
    ElMessage.success('RAG 參數已儲存，下次查詢即生效')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    ragSaving.value = false
  }
}

// ── 備份管理 ──────────────────────────────────────────────────────────────────
const backupFiles        = ref([])
const backupListLoading  = ref(false)
const backupTriggering   = ref(false)
const backupTriggerMsg   = ref('')
const backupTriggerOk    = ref(true)

async function loadBackupList() {
  backupListLoading.value = true
  try {
    const data = await systemSettingsApi.listBackups()
    backupFiles.value = data.files || []
  } catch (e) {
    console.error(e)
  } finally {
    backupListLoading.value = false
  }
}

async function triggerBackup() {
  backupTriggering.value = true
  backupTriggerMsg.value = ''
  try {
    const res = await systemSettingsApi.triggerBackup()
    backupTriggerOk.value  = res.ok
    const okParts  = (res.results || []).filter(r => r.ok).map(r => r.type)
    const failParts = (res.results || []).filter(r => !r.ok).map(r => `${r.type}: ${r.error || '失敗'}`)
    if (res.ok) {
      backupTriggerMsg.value = `備份完成（${okParts.join(', ')}）${failParts.length ? '；部分失敗：' + failParts.join(' | ') : ''}`
    } else {
      backupTriggerMsg.value = '備份失敗：' + failParts.join(' | ')
    }
    await loadBackupList()
  } catch (e) {
    backupTriggerOk.value  = false
    backupTriggerMsg.value = e.message
  } finally {
    backupTriggering.value = false
  }
}

// ── 使用者設定 ────────────────────────────────────────────────────────────────
const pwdSaving = ref(false)
const pwdForm = reactive({
  current_password: '',
  new_password:     '',
  confirm_password: '',
})

async function changePassword() {
  if (!pwdForm.current_password || !pwdForm.new_password) {
    ElMessage.warning('請填寫所有密碼欄位')
    return
  }
  if (pwdForm.new_password !== pwdForm.confirm_password) {
    ElMessage.warning('新密碼與確認密碼不一致')
    return
  }
  if (pwdForm.new_password.length < 8) {
    ElMessage.warning('新密碼至少需要 8 個字元')
    return
  }
  pwdSaving.value = true
  try {
    await systemSettingsApi.changePassword(pwdForm.current_password, pwdForm.new_password)
    ElMessage.success('密碼已更新，請用新密碼重新登入')
    pwdForm.current_password = ''
    pwdForm.new_password = ''
    pwdForm.confirm_password = ''
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    pwdSaving.value = false
  }
}
</script>

<style scoped>
.provider-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 8px;
}
.provider-card {
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
  padding: 14px 16px;
  cursor: pointer;
  width: 148px;
  transition: border-color 0.2s, box-shadow 0.2s;
  background: var(--el-bg-color);
  text-align: center;
}
.provider-card:hover {
  border-color: var(--el-color-primary);
  box-shadow: 0 2px 8px rgba(64,158,255,0.15);
}
.provider-card.active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.pcard-icon { font-size: 26px; line-height: 1; margin-bottom: 6px; }
.pcard-name { font-size: 14px; font-weight: 600; margin-bottom: 6px; }
.pcard-types { min-height: 24px; margin-bottom: 4px; }
.pcard-count { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
</style>
