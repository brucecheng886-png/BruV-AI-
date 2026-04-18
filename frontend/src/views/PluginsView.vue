<template>
  <div style="padding:24px;">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;">
      <h2 style="font-size:20px;">插件管理</h2>
      <el-button type="primary" @click="showCreateDialog = true">新增插件</el-button>
    </div>

    <el-table :data="plugins" v-loading="loading" stripe style="width:100%;">
      <el-table-column label="名稱" prop="name" min-width="140" />
      <el-table-column label="描述" prop="description" min-width="200" />
      <el-table-column label="端點" prop="endpoint" min-width="180" />
      <el-table-column label="啟用" width="80" align="center">
        <template #default="{ row }">
          <el-switch
            v-model="row.enabled"
            @change="(val) => togglePlugin(row.id, val)"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100" align="center">
        <template #default="{ row }">
          <el-popconfirm title="確定刪除此插件？" @confirm="deletePlugin(row.id)">
            <template #reference>
              <el-button size="small" type="danger" plain>刪除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- Create Dialog -->
    <el-dialog v-model="showCreateDialog" title="新增插件" width="500px">
      <el-form :model="createForm" label-width="80px">
        <el-form-item label="名稱" required>
          <el-input v-model="createForm.name" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="端點 URL" required>
          <el-input v-model="createForm.endpoint" placeholder="https://..." />
        </el-form-item>
        <el-form-item label="Auth Header">
          <el-input v-model="createForm.auth_header" placeholder="Bearer token 或留空" />
        </el-form-item>
        <el-form-item label="Input Schema">
          <el-input
            v-model="createForm.input_schema_str"
            type="textarea"
            :rows="3"
            placeholder='{"type":"object","properties":{"query":{"type":"string"}}}'
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="createPlugin">新增</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive } from 'vue'
import { pluginsApi } from '../api/index.js'
import { ElMessage } from 'element-plus'

const plugins = ref([])
const loading = ref(false)
const showCreateDialog = ref(false)
const creating = ref(false)

const createForm = reactive({
  name: '', description: '', endpoint: '', auth_header: '', input_schema_str: '{}'
})

onMounted(loadPlugins)

async function loadPlugins() {
  loading.value = true
  try {
    plugins.value = await pluginsApi.list()
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function createPlugin() {
  if (!createForm.name || !createForm.endpoint) {
    ElMessage.warning('名稱和端點為必填')
    return
  }
  creating.value = true
  try {
    let input_schema = {}
    try { input_schema = JSON.parse(createForm.input_schema_str) } catch {}
    await pluginsApi.create({
      name: createForm.name,
      description: createForm.description,
      endpoint: createForm.endpoint,
      auth_header: createForm.auth_header || null,
      input_schema,
    })
    showCreateDialog.value = false
    Object.assign(createForm, { name: '', description: '', endpoint: '', auth_header: '', input_schema_str: '{}' })
    await loadPlugins()
    ElMessage.success('插件已新增')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    creating.value = false
  }
}

async function togglePlugin(id, enabled) {
  try {
    await pluginsApi.toggle(id, enabled)
  } catch (e) {
    ElMessage.error(e.message)
    await loadPlugins()
  }
}

async function deletePlugin(id) {
  try {
    await pluginsApi.delete(id)
    await loadPlugins()
    ElMessage.success('已刪除')
  } catch (e) {
    ElMessage.error(e.message)
  }
}
</script>
