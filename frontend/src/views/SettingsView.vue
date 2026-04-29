<template>
  <div class="settings-root">
    <div class="settings-header">
      <h2 class="settings-title">設定</h2>
      <el-button :icon="Refresh" circle title="重新整理頁面" @click="reloadPage" />
    </div>

    <div class="group-tabs">
      <button v-for="g in GROUP_DEFS" :key="g.key"
        class="group-tab" :class="{ active: activeGroup === g.key }"
        @click="onGroupChange(g.key)">{{ g.label }}</button>
    </div>

    <div class="settings-body">
      <template v-if="activeGroup === 'model'">
        <div class="settings-section">
          <div class="section-header" style="justify-content:space-between;">
            <span style="display:flex;align-items:center;gap:8px;">
              <Cpu :size="16" :stroke-width="1.5" class="section-icon" />
              <span>模型管理</span>
            </span>
            <el-button type="primary" size="small" @click="openNewDialog">新增模型</el-button>
          </div>
          <div class="section-body">
            <!-- 地端模型 -->
            <div class="model-group-title">地端模型</div>
            <el-table :data="models.filter(m => m.provider === 'ollama')" v-loading="loading" stripe style="width:100%;" empty-text="尚無地端模型">
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
              <el-table-column label="啟用" width="70" align="center">
                <template #default="{ row }">
                  <el-switch :model-value="row.enabled" @change="(v) => toggleEnabled(row, v)" />
                </template>
              </el-table-column>
              <el-table-column label="預設" width="70" align="center">
                <template #default="{ row }">
                  <el-tag v-if="row.is_default" type="success" size="small">預設</el-tag>
                  <el-button v-else size="small" plain @click="setDefault(row)">設為</el-button>
                </template>
              </el-table-column>
              <el-table-column label="月度上限 (USD)" width="110" align="center">
                <template #default="{ row }">
                  <span v-if="row.monthly_quota_usd != null">${{ Number(row.monthly_quota_usd).toFixed(2) }}</span>
                  <span v-else style="color:#ccc;">—</span>
                </template>
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

            <el-divider />

            <!-- 雲端模型 -->
            <div class="model-group-title">雲端模型</div>
            <el-table :data="models.filter(m => m.provider !== 'ollama')" v-loading="loading" stripe style="width:100%;" empty-text="尚無雲端模型">
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
              <el-table-column label="啟用" width="70" align="center">
                <template #default="{ row }">
                  <el-switch :model-value="row.enabled" @change="(v) => toggleEnabled(row, v)" />
                </template>
              </el-table-column>
              <el-table-column label="預設" width="70" align="center">
                <template #default="{ row }">
                  <el-tag v-if="row.is_default" type="success" size="small">預設</el-tag>
                  <el-button v-else size="small" plain @click="setDefault(row)">設為</el-button>
                </template>
              </el-table-column>
              <el-table-column label="月度上限 (USD)" width="110" align="center">
                <template #default="{ row }">
                  <span v-if="row.monthly_quota_usd != null">${{ Number(row.monthly_quota_usd).toFixed(2) }}</span>
                  <span v-else style="color:#ccc;">—</span>
                </template>
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
          </div>
        </div>
      </template>
      <template v-if="activeGroup === 'chat'">
        <div class="settings-section">
          <div class="section-header">
            <Sliders :size="16" :stroke-width="1.5" class="section-icon" />
            <span>RAG 參數</span>
          </div>
          <div class="section-body">
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
            <el-divider />
            <el-form-item label="Chunk 大小（字元）">
              <el-input-number v-model="ragForm.doc_chunk_size" :min="100" :max="2000" :step="100" style="width:150px;" />
              <span style="margin-left:10px;font-size:12px;color:#999;">文件分塊軟上限，影響新上傳的文件</span>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="ragSaving" @click="saveRagSettings">儲存設定</el-button>
              <el-button @click="loadRagSettings">重置</el-button>
            </el-form-item>
          </el-form>
        </div>
          </div>
        </div>
        <div class="settings-section">
          <div class="section-header">
            <MessageSquare :size="16" :stroke-width="1.5" class="section-icon" />
            <span>對話行為</span>
          </div>
          <div class="section-body">
        <div v-loading="chatLoading" style="max-width:580px;">
          <el-alert type="info" :closable="false" style="margin-bottom:20px;">
            調整後立即生效（下一次問答即使用新參數）。
          </el-alert>
          <el-form :model="chatForm" label-width="180px" label-position="left">
            <el-form-item label="溫度（Temperature）">
              <el-slider v-model="chatForm.chat_temperature"
                :min="0" :max="2" :step="0.1"
                show-input :input-size="'small'" style="width:320px;" />
              <div style="font-size:12px;color:#999;margin-top:4px;">
                0 = 嚴謹精確，0.7 = 平衡（建議），2 = 富有創意
              </div>
            </el-form-item>
            <el-form-item label="回應最大長度 Tokens">
              <el-input-number v-model="chatForm.chat_max_tokens" :min="256" :max="16384" :step="256" style="width:200px;" />
              <span style="margin-left:10px;font-size:12px;color:#999;">一般建議 2048</span>
            </el-form-item>
            <el-form-item label="對話歷史保留輪數">
              <el-input-number v-model="chatForm.chat_history_rounds" :min="1" :max="50" :step="1" style="width:150px;" />
              <span style="margin-left:10px;font-size:12px;color:#999;">每輪 = 1 張 user + 1 張 AI</span>
            </el-form-item>
            <el-form-item label="全域 System Prompt">
              <el-input
                v-model="chatForm.chat_system_prompt"
                type="textarea"
                :rows="5"
                placeholder="可不填。填寫後會追加在 AI 的開頭指令中，讓 AI 承擔特定角色或風格。"
                style="width:380px;font-family:monospace;font-size:13px;"
              />
            </el-form-item>

            <!-- 文件處理模型 -->
            <el-divider content-position="left">文件處理模型</el-divider>
            <el-form-item label="文件分析模型">
              <el-select
                v-model="chatForm.doc_analysis_model"
                placeholder="（與對話模型相同）"
                style="width:280px;"
                clearable
              >
                <el-option
                  v-for="m in chatModels"
                  :key="m.id"
                  :label="m.name"
                  :value="m.name"
                />
              </el-select>
              <div style="font-size:12px;color:#999;margin-top:4px;">
                用於文件攝取時的 LLM 分析（實體抽取、KB 建議、Tag 建議）。不填則與對話模型相同。
              </div>
            </el-form-item>

            <el-form-item>
              <el-button type="primary" :loading="chatSaving" @click="saveChatSettings">儲存設定</el-button>
              <el-button @click="loadChatSettings">重置</el-button>
            </el-form-item>
          </el-form>
        </div>
          </div>
        </div>
      </template>
      <template v-if="activeGroup === 'data'">
        <div class="settings-section">
          <div class="section-header">
            <HardDrive :size="16" :stroke-width="1.5" class="section-icon" />
            <span>備份管理</span>
          </div>
          <div class="section-body">
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
          </div>
        </div>
        <div class="settings-section">
          <div class="section-header">
            <Database :size="16" :stroke-width="1.5" class="section-icon" />
            <span>知識庫 Schema</span>
          </div>
          <div class="section-body">
        <div v-loading="schemaLoading" style="max-width:760px;">
          <el-alert type="info" :closable="false" style="margin-bottom:20px;">
            Schema 會被注入至每次問答的 System Prompt，用來告訴 AI 知識庫的結構與回答準則。若為空則不注入。
          </el-alert>
          <el-input
            v-model="schemaText"
            type="textarea"
            :rows="20"
            placeholder="用 Markdown 格式描述知識庫結構、領域、回答規則…"
            style="font-family:monospace;font-size:13px;"
          />
          <div style="margin-top:12px;display:flex;gap:8px;">
            <el-button type="primary" :loading="schemaSaving" @click="saveSchema">儲存 Schema</el-button>
            <el-button @click="loadSchema">重置</el-button>
            <span style="font-size:12px;color:#999;align-self:center;">上限 8000 字元</span>
          </div>
        </div>
          </div>
        </div>
      </template>
      <template v-if="activeGroup === 'user'">
        <div class="settings-section">
          <div class="section-header">
            <User :size="16" :stroke-width="1.5" class="section-icon" />
            <span>使用者設定</span>
          </div>
          <div class="section-body">
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
          </div>
        </div>
      </template>
      <template v-if="activeGroup === 'usage'">
        <div class="settings-section">
          <div class="section-header" style="justify-content:space-between;">
            <span style="display:flex;align-items:center;gap:8px;">
              <Sliders :size="16" :stroke-width="1.5" class="section-icon" />
              <span>LLM 使用量</span>
            </span>
            <div style="display:flex;gap:8px;align-items:center;">
              <el-select v-model="usageRangeDays" size="small" style="width:140px;" @change="loadUsage">
                <el-option :value="7"   label="最近 7 天" />
                <el-option :value="30"  label="最近 30 天" />
                <el-option :value="90"  label="最近 90 天" />
              </el-select>
              <el-button size="small" :loading="usageLoading" @click="loadUsage">重新整理</el-button>
            </div>
          </div>
          <div class="section-body">
            <div class="usage-totals">
              <div class="usage-card">
                <div class="usage-card-label">總呼叫次數</div>
                <div class="usage-card-value">{{ usageTotals.calls.toLocaleString() }}</div>
              </div>
              <div class="usage-card">
                <div class="usage-card-label">總 Tokens</div>
                <div class="usage-card-value">{{ usageTotals.total_tokens.toLocaleString() }}</div>
              </div>
              <div class="usage-card">
                <div class="usage-card-label">估算成本 (USD)</div>
                <div class="usage-card-value">${{ Number(usageTotals.cost_usd || 0).toFixed(4) }}</div>
              </div>
            </div>
            <el-table :data="usageItems" v-loading="usageLoading" stripe style="width:100%;margin-top:16px;" empty-text="尚無使用紀錄">
              <el-table-column label="模型" prop="model_name" min-width="180" />
              <el-table-column label="Provider" prop="provider" width="120" />
              <el-table-column label="呼叫次數" width="100" align="right">
                <template #default="{ row }">{{ row.calls.toLocaleString() }}</template>
              </el-table-column>
              <el-table-column label="成功率" width="90" align="right">
                <template #default="{ row }">
                  {{ row.calls > 0 ? Math.round(row.success_calls / row.calls * 100) : 0 }}%
                </template>
              </el-table-column>
              <el-table-column label="平均延遲" width="110" align="right">
                <template #default="{ row }">{{ row.avg_latency_ms.toLocaleString() }} ms</template>
              </el-table-column>
              <el-table-column label="Prompt Tokens" width="130" align="right">
                <template #default="{ row }">{{ row.prompt_tokens.toLocaleString() }}</template>
              </el-table-column>
              <el-table-column label="Completion Tokens" width="150" align="right">
                <template #default="{ row }">{{ row.completion_tokens.toLocaleString() }}</template>
              </el-table-column>
              <el-table-column label="總 Tokens" width="120" align="right">
                <template #default="{ row }">{{ row.total_tokens.toLocaleString() }}</template>
              </el-table-column>
              <el-table-column label="估算成本 (USD)" width="130" align="right">
                <template #default="{ row }">${{ Number(row.cost_usd || 0).toFixed(4) }}</template>
              </el-table-column>
            </el-table>
            <div class="usage-daily">
              <div class="section-subtitle">每日使用量（最近 {{ usageRangeDays }} 天）</div>
              <div v-if="usageDaily.length === 0" style="color:#94a3b8;font-size:13px;padding:16px;">尚無資料</div>
              <div v-else class="usage-bar-chart">
                <div v-for="d in usageDaily" :key="d.date" class="usage-bar-row" :title="`${d.date}\n呼叫: ${d.calls}\nTokens: ${d.total_tokens}\n成本: $${Number(d.cost_usd || 0).toFixed(4)}`">
                  <div class="usage-bar-date">{{ (d.date || '').slice(5) }}</div>
                  <div class="usage-bar-track">
                    <div class="usage-bar-fill" :style="{ width: usageBarWidth(d.total_tokens) + '%' }"></div>
                  </div>
                  <div class="usage-bar-value">{{ d.total_tokens.toLocaleString() }} tk</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>
      <template v-if="activeGroup === 'system'">
        <div class="settings-section">
          <div class="section-header">
            <Bot :size="16" :stroke-width="1.5" class="section-icon" />
            <span>AI Skill</span>
          </div>
          <div class="section-body">
        <div class="skill-grid">
          <el-card v-for="skill in skills" :key="skill.page_key" class="skill-card">
            <template #header>
              <div class="skill-card-header">
                <div class="skill-card-title">
                  <component :is="SKILL_ICONS[skill.page_key]" :size="18" :stroke-width="1.5" class="skill-icon" />
                  <span>{{ skill.name }}</span>
                </div>
                <el-switch v-model="skill.is_enabled" active-text="啟用" inactive-text="停用"
                  :loading="skill._saving" @change="saveSkill(skill)" />
              </div>
            </template>
            <div class="skill-body">
              <div class="skill-label">自訂指令（選填）：</div>
              <el-input
                v-model="skill.user_prompt"
                type="textarea"
                :autosize="{ minRows: 3, maxRows: 8 }"
                :placeholder="`補充說明給「${skill.name}」的額外指令，例如：回答時請用繁體中文，並引用文件章節。`"
              />
              <div class="skill-actions">
                <el-button type="primary" size="small" :loading="skill._saving" @click="saveSkill(skill)">儲存</el-button>
                <el-button type="danger" size="small" plain :loading="skill._saving" @click="uninstallSkill(skill)">解除安裝</el-button>
              </div>
            </div>
          </el-card>
          <el-card
            v-for="item in availableSkills"
            :key="'avail-' + item.page_key"
            class="skill-card skill-card--uninstalled"
          >
            <template #header>
              <div class="skill-card-header">
                <div class="skill-card-title">
                  <component :is="SKILL_ICONS[item.page_key] || Bot" :size="18" :stroke-width="1.5" class="skill-icon" />
                  <span>{{ item.name }}</span>
                </div>
                <el-tag size="small" type="info">未安裝</el-tag>
              </div>
            </template>
            <div class="skill-body">
              <div class="skill-label" style="color:#94a3b8;">{{ item.description }}</div>
              <div class="skill-actions">
                <el-button type="primary" size="small" :loading="item._installing" @click="installSkill(item)">安裝</el-button>
              </div>
            </div>
          </el-card>
        </div>
          </div>
        </div>
      </template>
    </div>

    <!-- Add / Edit Dialog -->
    <el-dialog v-model="showAddDialog" :title="editingId ? '編輯模型' : '新增模型'" width="600px" @closed="onDialogClosed">
      <el-form :model="modelForm" label-width="110px">
        <el-form-item label="Provider" required>
          <el-select v-model="modelForm.provider" style="width:220px;" @change="onProviderChange">
            <el-option v-for="p in PROVIDER_DEFS" :key="p.key" :label="p.name" :value="p.key" />
          </el-select>
        </el-form-item>
        <el-form-item label="模型類型">
          <el-select v-model="modelForm.model_type" style="width:220px;">
            <el-option value="chat"      label="Chat（對話）" />
            <el-option value="embedding" label="Embedding（嵌入）" />
            <el-option value="rerank"    label="Re-rank（重排）" />
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
            :placeholder="modelForm._hasApiKey ? '「已儲存」— 輸入新金鑰可覆寫' : '填入 API Key（加密儲存）'" />
          <div style="font-size:11px;margin-top:3px;" :style="{ color: modelForm._hasApiKey ? '#67c23a' : '#999' }">
            {{ modelForm._hasApiKey ? '✔ 已有儲存的 API Key，筆區空白表示不變更' : '加密儲存至資料庫' }}
          </div>
        </el-form-item>
        <el-form-item label="Max tokens">
          <el-input-number v-model="modelForm.max_tokens" :min="512" :step="1024" style="width:160px;" />
        </el-form-item>
        <el-form-item v-if="modelForm.model_type === 'chat'" label="支援 Vision？">
          <el-switch v-model="modelForm.vision_support" active-text="是" inactive-text="否" />
        </el-form-item>
        <el-form-item label="啟用">
          <el-switch v-model="modelForm.enabled" active-text="啟用" inactive-text="停用" />
        </el-form-item>
        <el-form-item label="設為預設">
          <el-switch v-model="modelForm.is_default" active-text="是" inactive-text="否" />
          <span style="font-size:11px;color:#999;margin-left:8px;">每個模型類型只能有一個預設</span>
        </el-form-item>
        <el-form-item label="月度上限 (USD)">
          <el-input-number v-model="modelForm.monthly_quota_usd" :min="0" :precision="2" :step="10" :placeholder="'不限制'" style="width:160px;" />
          <span style="font-size:11px;color:#999;margin-left:8px;">留空表示不限制</span>
        </el-form-item>
        <el-form-item label="">
          <el-button :loading="verifying" @click="verifyModel">
            <Link :size="14" :stroke-width="1.5" style="margin-right:4px;vertical-align:middle" />驗證連線
          </el-button>
          <el-tag v-if="verifyStatus === 'ok'"   type="success" style="margin-left:8px;">{{ verifyMsg }}</el-tag>
          <el-tag v-if="verifyStatus === 'fail'" type="danger"  style="margin-left:8px;">{{ verifyMsg }}</el-tag>
        </el-form-item>
        <div class="advanced-toggle" @click="showAdvanced = !showAdvanced">
          <span class="advanced-line"></span>
          <span class="advanced-label">進階資訊（選填）{{ showAdvanced ? ' ▴' : ' ▾' }}</span>
          <span class="advanced-line"></span>
        </div>
        <div v-show="showAdvanced">
          <el-form-item label="開發者"><el-input v-model="modelForm.developer" /></el-form-item>
          <el-form-item label="參數(B)"><el-input-number v-model="modelForm.params_b" :precision="1" :step="0.5" /></el-form-item>
          <el-form-item label="Context 長度"><el-input-number v-model="modelForm.context_length" :step="1024" /></el-form-item>
          <el-form-item label="License"><el-input v-model="modelForm.license" /></el-form-item>
          <el-form-item label="Tags">
            <el-input v-model="modelForm.tags_str" placeholder="逗號分隔，如: llm,chat,code" />
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveModel">儲存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onActivated, reactive, defineComponent, computed } from 'vue'
import { useRoute } from 'vue-router'
import { Refresh, Check } from '@element-plus/icons-vue'
import { Layers, FolderOpen, MessageSquare, Network, Puzzle, Settings, Dna, Cpu, Key, Sliders, HardDrive, Database, Bot, User, Link, BookOpen } from 'lucide-vue-next'
import { wikiApi, systemSettingsApi, agentSkillsApi, monitoringApi } from '../api/index.js'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '../stores/auth.js'

const authStore = useAuthStore()
const route = useRoute()
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

// ── 群組切換 ──────────────────────────────────────────────────────────────────
const GROUP_DEFS = [
  { key: 'user',   label: '使用者設定' },
  { key: 'model',  label: '模型設定' },
  { key: 'chat',   label: '對話設定' },
  { key: 'usage',  label: '使用量' },
  { key: 'data',   label: '資料管理' },
  { key: 'system', label: '系統' },
]
const activeGroup = ref('user')
function onGroupChange(group) {
  activeGroup.value = group
  if (group === 'chat')   { loadRagSettings(); loadChatSettings() }
  if (group === 'usage')  { loadUsage() }
  if (group === 'data')   { loadSchema(); loadBackupList() }
  if (group === 'system') { loadSkills() }
}
function _applyRouteGroup() {
  const g = route.query.group
  if (g && GROUP_DEFS.some(d => d.key === g)) onGroupChange(g)
}

// ── Model List ────────────────────────────────────────────────────────────────
const models = ref([])
const loading = ref(false)
const searchQ = ref('')
const PROVIDER_DEFS = [
  { key: 'ollama',     name: 'Ollama',     logo: 'https://ollama.com/public/ollama.png',                                                                                     types: ['chat', 'embedding'] },
  { key: 'openai',     name: 'OpenAI',     logo: 'https://upload.wikimedia.org/wikipedia/commons/0/04/ChatGPT_logo.svg',                                                       types: ['chat', 'embedding'] },
  { key: 'groq',       name: 'Groq',       logo: 'https://groq.com/wp-content/uploads/2024/03/groq-logo.png',                                                                  types: ['chat'] },
  { key: 'gemini',     name: 'Gemini',     logo: 'https://www.gstatic.com/lamda/images/gemini_sparkle_v002_d4735304ff6292a690345.svg',                                          types: ['chat'] },
  { key: 'openrouter', name: 'OpenRouter', logo: 'https://openrouter.ai/favicon.ico',                                                                                           types: ['chat'] },
  { key: 'anthropic',  name: 'Anthropic Claude', logo: 'https://www.anthropic.com/favicon.ico',                                                                                  types: ['chat'] },
]
const failedLogos = ref(new Set())
function onLogoError(key) { failedLogos.value = new Set([...failedLogos.value, key]) }
const selectedProvider = ref(null)
const filteredModels = computed(() => {
  if (!selectedProvider.value) return models.value
  return models.value.filter(m => m.provider === selectedProvider.value)
})
const providerCount = (key) => models.value.filter(m => m.provider === key).length
const showAddDialog = ref(false)
const showAdvanced = ref(false)
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
  _hasApiKey: false,   // 表示 DB 已有儲存的 API Key
  // 治理欄位（Phase A2/A5）
  enabled: true,
  is_default: false,
  monthly_quota_usd: null,
})

let _settingsMounting = false
onMounted(async () => {
  _settingsMounting = true
  try {
    await loadModels()
    await loadApiSettings()
    loadChatSettings()
    _applyRouteGroup()
  } finally {
    _settingsMounting = false
  }
})

// ── AI Skill ──────────────────────────────────────────────────────────────────
const SKILL_ICONS = {
  docs:     FolderOpen,
  chat:     MessageSquare,
  kb:       BookOpen,
  ontology: Network,
  plugins:  Puzzle,
  settings: Settings,
  protein:  Dna,
}

const skills = ref([])
const availableSkills = ref([])

// ── 使用量 (Phase B7) ─────────────────────────────────────────────
const usageRangeDays = ref(30)
const usageLoading = ref(false)
const usageItems = ref([])
const usageDaily = ref([])
const usageTotals = ref({ calls: 0, total_tokens: 0, cost_usd: 0 })

function usageBarWidth(tokens) {
  const max = Math.max(1, ...usageDaily.value.map(d => d.total_tokens || 0))
  return Math.max(2, Math.round((tokens / max) * 100))
}

async function loadUsage() {
  usageLoading.value = true
  try {
    const days = usageRangeDays.value
    const start = new Date(Date.now() - days * 86400 * 1000).toISOString()
    const [summary, daily] = await Promise.all([
      monitoringApi.getUsageSummary({ start }),
      monitoringApi.getUsageDaily(days),
    ])
    usageItems.value = summary.items || []
    usageTotals.value = summary.totals || { calls: 0, total_tokens: 0, cost_usd: 0 }
    usageDaily.value = daily.items || []
  } catch (e) {
    ElMessage.error('載入使用量失敗：' + e.message)
  } finally {
    usageLoading.value = false
  }
}

async function loadSkills() {
  try {
    const [installed, available] = await Promise.all([
      agentSkillsApi.list(),
      agentSkillsApi.available(),
    ])
    skills.value = installed.map(s => ({ ...s, _saving: false }))
    const installedKeys = new Set(installed.map(s => s.page_key))
    availableSkills.value = available.filter(s => !installedKeys.has(s.page_key))
                                     .map(s => ({ ...s, _installing: false }))
  } catch (e) {
    ElMessage.error('載入 AI Skill 失敗：' + e.message)
  }
}

async function saveSkill(skill) {
  skill._saving = true
  try {
    await agentSkillsApi.update(skill.page_key, {
      user_prompt: skill.user_prompt,
      is_enabled: skill.is_enabled,
    })
    ElMessage.success(`「${skill.name}」已儲存`)
  } catch (e) {
    ElMessage.error('儲存失敗：' + e.message)
  } finally {
    skill._saving = false
  }
}

async function installSkill(item) {
  item._installing = true
  try {
    await agentSkillsApi.install(item.page_key)
    ElMessage.success(`已安裝「${item.name}」`)
    await loadSkills()
  } catch (e) {
    ElMessage.error('安裝失敗：' + e.message)
  } finally {
    item._installing = false
  }
}

async function uninstallSkill(skill) {
  try {
    await ElMessageBox.confirm(`確定要解除安裝「${skill.name}」？`, '確認', { type: 'warning' })
  } catch { return }
  skill._saving = true
  try {
    await agentSkillsApi.uninstall(skill.page_key)
    ElMessage.success(`已解除安裝「${skill.name}」`)
    await loadSkills()
  } catch (e) {
    ElMessage.error('解除安裝失敗：' + e.message)
    skill._saving = false
  }
}

onActivated(async () => {
  if (_settingsMounting) return
  await loadModels()
  await loadApiSettings()
  _applyRouteGroup()
})

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
    tags_str: '', _api_key: '', _hasApiKey: false,
    model_type: 'chat', max_tokens: null, vision_support: false,
    provider: prov, base_url: prov === 'ollama' ? 'http://ollama:11434' : '',
    enabled: true, is_default: false, monthly_quota_usd: null,
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
    _hasApiKey: row.has_api_key || false,
    model_type: row.model_type || 'chat',
    max_tokens: row.max_tokens || null,
    vision_support: row.vision_support || false,
    provider: row.provider || 'ollama',
    base_url: row.base_url || '',
    enabled: row.enabled !== false,
    is_default: row.is_default === true,
    monthly_quota_usd: row.monthly_quota_usd != null ? Number(row.monthly_quota_usd) : null,
  })
  verifyStatus.value = ''
  verifyMsg.value = ''
  showAddDialog.value = true
}

function onDialogClosed() {
  modelForm._api_key = ''
  modelForm._hasApiKey = false
  editingId.value = null
  verifyStatus.value = ''
  verifyMsg.value = ''
  showAdvanced.value = false
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
      model_id:   editingId.value || null,   // 當 api_key 為空時從 DB 讀取已儲存的
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
      api_key: modelForm._api_key || null,   // null = 不變更；'' = 清除；其他 = 更新
    }
    delete body.tags_str
    delete body._api_key
    delete body._hasApiKey
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

async function toggleEnabled(row, val) {
  try {
    await wikiApi.updateGovernance(row.id, { enabled: val })
    row.enabled = val
    ElMessage.success(val ? '已啟用' : '已停用')
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function setDefault(row) {
  try {
    await wikiApi.updateGovernance(row.id, { is_default: true })
    // 同 model_type 的其他模型 is_default 由後端自動清除；前端重新載入確保一致
    await loadModels()
    ElMessage.success(`已將「${row.name}」設為 ${row.model_type || 'chat'} 預設`)
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
  anthropic:  'claude-sonnet-4-6',
}

const apiLoading = ref(false)
const apiSaving  = ref(false)
const apiTesting = ref(false)
const testResult = ref(null)   // true | false | null
const testError  = ref('')

const maskedKeys = reactive({ openai: '', groq: '', gemini: '', openrouter: '', anthropic: '' })

const apiForm = reactive({
  llm_provider:      'ollama',
  cloud_llm_model:   '',
  openai_api_key:    null,
  groq_api_key:      null,
  gemini_api_key:    null,
  openrouter_api_key: null,
  anthropic_api_key: null,
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
    maskedKeys.anthropic    = data.anthropic_api_key_masked
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
      anthropic_api_key: apiForm.anthropic_api_key,
    })
    ElMessage.success('設定已儲存，對話頁立即生效')
    // 重新載入遮罩
    await loadApiSettings()
    // 清空明文輸入（已儲存）
    apiForm.openai_api_key = null
    apiForm.groq_api_key = null
    apiForm.gemini_api_key = null
    apiForm.openrouter_api_key = null
    apiForm.anthropic_api_key = null

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
  doc_chunk_size:        400,
})

async function loadRagSettings() {
  ragLoading.value = true
  try {
    const data = await systemSettingsApi.getRag()
    ragForm.rag_top_k             = data.rag_top_k
    ragForm.rag_rerank_top_k      = data.rag_rerank_top_k
    ragForm.rag_max_context_chars = data.rag_max_context_chars
    ragForm.rag_rerank_enabled    = data.rag_rerank_enabled
    ragForm.doc_chunk_size        = data.doc_chunk_size ?? 400
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

// ── 知識庫 Schema ──────────────────────────────────────────────────────────────────────────
const schemaText    = ref('')
const schemaLoading = ref(false)
const schemaSaving  = ref(false)

async function loadSchema() {
  schemaLoading.value = true
  try {
    const data = await systemSettingsApi.getSchema()
    schemaText.value = data.schema_text || ''
  } catch (e) {
    console.error(e)
  } finally {
    schemaLoading.value = false
  }
}

async function saveSchema() {
  schemaSaving.value = true
  try {
    await systemSettingsApi.saveSchema(schemaText.value)
    ElMessage.success('Schema 已儲存，下次問答即生效')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    schemaSaving.value = false
  }
}

// ── 對話行為設定 ──────────────────────────────────────────────────────────────
const chatLoading = ref(false)
const chatSaving  = ref(false)
const chatModels  = ref([])
const chatForm = reactive({
  chat_temperature:    0.7,
  chat_max_tokens:     2048,
  chat_history_rounds: 10,
  chat_system_prompt:  '',
  doc_analysis_model:  '',
})

async function loadChatSettings() {
  chatLoading.value = true
  try {
    const [data, modelsData] = await Promise.all([
      systemSettingsApi.getChatBehavior(),
      wikiApi.listModels(),
    ])
    chatForm.chat_temperature    = data.chat_temperature
    chatForm.chat_max_tokens     = data.chat_max_tokens
    chatForm.chat_history_rounds = data.chat_history_rounds
    chatForm.chat_system_prompt  = data.chat_system_prompt
    chatForm.doc_analysis_model  = data.doc_analysis_model || ''
    chatModels.value = (Array.isArray(modelsData) ? modelsData : (modelsData?.items || []))
      .filter(m => m.model_type === 'chat' || !m.model_type)
  } catch (e) {
    console.error(e)
  } finally {
    chatLoading.value = false
  }
}

async function saveChatSettings() {
  chatSaving.value = true
  try {
    await systemSettingsApi.saveChatBehavior({ ...chatForm })
    ElMessage.success('對話設定已儲存，下次問答即生效')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    chatSaving.value = false
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
.settings-root {
  min-height: 100%;
  background: #f4f6f9;
  padding: 24px;
}
.settings-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}
.settings-title { font-size: 20px; margin: 0; font-weight: 600; color: #1e293b; }

/* ── Group Tabs (capsule) ───────────────────────────────── */
.group-tabs {
  display: inline-flex;
  background: #e8edf2;
  border-radius: 10px;
  padding: 4px;
  gap: 2px;
  margin-bottom: 24px;
}
.group-tab {
  padding: 7px 20px;
  border-radius: 7px;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  color: #64748b;
  transition: background 0.15s, color 0.15s, box-shadow 0.15s;
}
.group-tab:hover { color: #334155; }
.group-tab.active {
  background: #fff;
  color: #1e293b;
  box-shadow: 0 1px 4px rgba(0,0,0,0.12);
}

/* ── Settings Body ─────────────────────────────────────── */
.settings-body {
  max-width: 860px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ── Section Card ──────────────────────────────────────── */
.settings-section {
  background: #fff;
  border-radius: 10px;
  border: 1px solid #e8eaed;
}
.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 24px;
  font-size: 16px;
  font-weight: 600;
  color: #1e293b;
  border-bottom: 1px solid #f0f0f0;
}
.section-icon { color: #64748b; flex-shrink: 0; }
.section-body { padding: 24px; }

.model-group-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-secondary);
  margin: 16px 0 8px;
}
.model-group-title:first-of-type {
  margin-top: 0;
}

.advanced-toggle {
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  margin: 16px 0;
  user-select: none;
}
.advanced-toggle .advanced-line {
  flex: 1;
  height: 1px;
  background: var(--el-border-color-lighter);
}
.advanced-toggle .advanced-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}
.advanced-toggle:hover .advanced-label {
  color: var(--el-color-primary);
}

/* ── Provider Cards ─────────────────────────────────────── */
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
.pcard-icon { width: 40px; height: 40px; margin: 0 auto 8px; display: flex; align-items: center; justify-content: center; }
.provider-logo { width: 40px; height: 40px; object-fit: contain; border-radius: 8px; }
.provider-logo-fallback {
  width: 40px; height: 40px;
  border-radius: 8px;
  background: #e2e8f0;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; font-weight: 700; color: #475569;
}
.pcard-name { font-size: 14px; font-weight: 600; margin-bottom: 6px; }
.pcard-types { min-height: 24px; margin-bottom: 4px; }
.pcard-count { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; }

/* ── LLM Provider 下拉選項 logo ────────────────────────────── */
.llm-provider-opt { display: flex; align-items: center; gap: 6px; }
.llm-opt-logo { width: 16px; height: 16px; object-fit: contain; flex-shrink: 0; }
.llm-opt-logo-fallback {
  width: 16px; height: 16px; font-size: 10px; font-weight: 700;
  color: #fff; background: #d97706; border-radius: 3px;
  display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0;
}

/* ── 使用量 (Phase B7) ───────────────────────────────────── */
.usage-totals {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
  margin-bottom: 4px;
}
.usage-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 12px 16px;
}
.usage-card-label { font-size: 12px; color: #64748b; }
.usage-card-value { font-size: 22px; font-weight: 600; color: #0f172a; margin-top: 4px; }
.usage-daily { margin-top: 20px; }
.section-subtitle { font-size: 13px; color: #475569; font-weight: 600; margin-bottom: 10px; }
.usage-bar-chart {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 360px;
  overflow-y: auto;
  padding: 4px 8px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #fff;
}
.usage-bar-row {
  display: grid;
  grid-template-columns: 60px 1fr 100px;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.usage-bar-date { color: #64748b; }
.usage-bar-track {
  height: 12px;
  background: #f1f5f9;
  border-radius: 3px;
  overflow: hidden;
}
.usage-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #60a5fa, #2563eb);
  border-radius: 3px;
}
.usage-bar-value { color: #0f172a; text-align: right; }

/* ── AI Skill ────────────────────────────────────────────── */
.skill-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 16px;
  margin-top: 4px;
}
.skill-card { }
.skill-card--uninstalled { background: #f8fafc; opacity: 0.85; }
.skill-card--uninstalled:hover { opacity: 1; }
.skill-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.skill-card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 14px;
}
.skill-icon { color: #64748b; flex-shrink: 0; }
.skill-body { display: flex; flex-direction: column; gap: 8px; }
.skill-label { font-size: 12px; color: #64748b; }
.skill-actions { display: flex; justify-content: flex-end; margin-top: 4px; }
</style>

