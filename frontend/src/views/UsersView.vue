<template>
  <div class="users-root">
    <!-- Header -->
    <div class="users-header">
      <div>
        <h2 class="page-title">使用者管理</h2>
        <p class="page-subtitle">建立與管理系統帳號，指派角色與存取權限</p>
      </div>
      <el-button type="primary" @click="openCreate">
        <el-icon style="margin-right:4px"><Plus /></el-icon>新增使用者
      </el-button>
    </div>

    <!-- Table -->
    <div class="users-table-wrap">
      <el-table
        :data="users"
        v-loading="loading"
        stripe
        style="width:100%"
      >
        <el-table-column prop="email" label="Email" min-width="200" />
        <el-table-column prop="display_name" label="名稱" width="140">
          <template #default="{ row }">{{ row.display_name || '—' }}</template>
        </el-table-column>
        <el-table-column prop="role" label="角色" width="120">
          <template #default="{ row }">
            <el-tag :type="roleTagType(row.role)" size="small">{{ ROLE_LABELS[row.role] || row.role }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="狀態" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
              {{ row.is_active ? '啟用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="首次改密" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.must_change_password" type="warning" size="small">待改密</el-tag>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="建立時間" width="170">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" plain @click="openEdit(row)">編輯</el-button>
            <el-button
              size="small"
              :type="row.is_active ? 'warning' : 'success'"
              plain
              :disabled="row.id === selfId"
              @click="toggleActive(row)"
            >{{ row.is_active ? '停用' : '啟用' }}</el-button>
            <el-button
              size="small"
              type="danger"
              plain
              :disabled="row.id === selfId"
              @click="confirmDelete(row)"
            >刪除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 新增對話框 -->
    <el-dialog v-model="createVisible" title="新增使用者" width="440px" :close-on-click-modal="false">
      <el-form :model="createForm" :rules="createRules" ref="createFormRef" label-width="90px">
        <el-form-item label="Email" prop="email">
          <el-input v-model="createForm.email" placeholder="user@example.com" />
        </el-form-item>
        <el-form-item label="初始密碼" prop="password">
          <el-input v-model="createForm.password" type="password" show-password placeholder="至少 8 字元" />
        </el-form-item>
        <el-form-item label="名稱">
          <el-input v-model="createForm.display_name" placeholder="（選填）" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="createForm.role" style="width:100%">
            <el-option v-for="r in ROLE_OPTIONS" :key="r.value" :label="r.label" :value="r.value" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitCreate">建立</el-button>
      </template>
    </el-dialog>

    <!-- 編輯對話框 -->
    <el-dialog v-model="editVisible" title="編輯使用者" width="440px" :close-on-click-modal="false">
      <el-form :model="editForm" label-width="90px">
        <el-form-item label="Email">
          <el-input :value="editForm.email" disabled />
        </el-form-item>
        <el-form-item label="名稱">
          <el-input v-model="editForm.display_name" placeholder="（選填）" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="editForm.role" style="width:100%" :disabled="editForm.id === selfId">
            <el-option v-for="r in ROLE_OPTIONS" :key="r.value" :label="r.label" :value="r.value" />
          </el-select>
          <div v-if="editForm.id === selfId" class="form-hint">不可降級自己的管理員角色</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitEdit">儲存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Plus } from 'lucide-vue-next'
import { ElMessage, ElMessageBox } from 'element-plus'
import { usersApi } from '../api/index.js'
import { useAuthStore } from '../stores/auth.js'

const authStore = useAuthStore()
const selfId = authStore.userId

const ROLE_LABELS = {
  admin: '管理員',
  editor: '編輯者',
  user: '一般使用者',
  readonly: '唯讀',
  auditor: '稽核員',
}

const ROLE_OPTIONS = [
  { value: 'admin',    label: '管理員' },
  { value: 'editor',   label: '編輯者' },
  { value: 'user',     label: '一般使用者' },
  { value: 'readonly', label: '唯讀' },
  { value: 'auditor',  label: '稽核員' },
]

function roleTagType(role) {
  return { admin: 'danger', editor: 'warning', user: '', readonly: 'info', auditor: 'success' }[role] ?? 'info'
}

function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-TW', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

// ── 列表 ──
const users = ref([])
const loading = ref(false)

async function loadUsers() {
  loading.value = true
  try {
    users.value = await usersApi.list()
  } catch (e) {
    ElMessage.error(e.message || '載入失敗')
  } finally {
    loading.value = false
  }
}

onMounted(loadUsers)

// ── 新增 ──
const createVisible = ref(false)
const saving = ref(false)
const createFormRef = ref(null)
const createForm = ref({ email: '', password: '', display_name: '', role: 'user' })
const createRules = {
  email: [{ required: true, message: '請填寫 Email', trigger: 'blur' }],
  password: [{ required: true, min: 8, message: '密碼至少 8 字元', trigger: 'blur' }],
  role: [{ required: true, message: '請選擇角色', trigger: 'change' }],
}

function openCreate() {
  createForm.value = { email: '', password: '', display_name: '', role: 'user' }
  createVisible.value = true
}

async function submitCreate() {
  await createFormRef.value?.validate()
  saving.value = true
  try {
    await usersApi.create(createForm.value)
    ElMessage.success('使用者已建立')
    createVisible.value = false
    await loadUsers()
  } catch (e) {
    ElMessage.error(e.message || '建立失敗')
  } finally {
    saving.value = false
  }
}

// ── 編輯 ──
const editVisible = ref(false)
const editForm = ref({})

function openEdit(row) {
  editForm.value = { id: row.id, email: row.email, display_name: row.display_name || '', role: row.role }
  editVisible.value = true
}

async function submitEdit() {
  saving.value = true
  try {
    await usersApi.update(editForm.value.id, {
      display_name: editForm.value.display_name,
      role: editForm.value.role,
    })
    ElMessage.success('已更新')
    editVisible.value = false
    await loadUsers()
  } catch (e) {
    ElMessage.error(e.message || '更新失敗')
  } finally {
    saving.value = false
  }
}

// ── 停用 / 啟用 ──
async function toggleActive(row) {
  try {
    await usersApi.update(row.id, { is_active: !row.is_active })
    ElMessage.success(row.is_active ? '帳號已停用' : '帳號已啟用')
    await loadUsers()
  } catch (e) {
    ElMessage.error(e.message || '操作失敗')
  }
}

// ── 刪除 ──
async function confirmDelete(row) {
  try {
    await ElMessageBox.confirm(
      `確定要刪除使用者「${row.email}」？此操作無法復原。`,
      '刪除確認',
      { type: 'warning', confirmButtonText: '刪除', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger' }
    )
    await usersApi.remove(row.id)
    ElMessage.success('已刪除')
    await loadUsers()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e.message || '刪除失敗')
  }
}
</script>

<style scoped>
.users-root {
  padding: 24px;
  max-width: 1100px;
  margin: 0 auto;
}

.users-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 24px;
}

.page-title {
  font-size: 1.4rem;
  font-weight: 600;
  margin: 0 0 4px;
}

.page-subtitle {
  color: #64748b;
  font-size: 0.875rem;
  margin: 0;
}

.users-table-wrap {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 1px 4px rgba(0,0,0,.06);
  overflow: hidden;
}

.text-muted {
  color: #94a3b8;
}

.form-hint {
  font-size: 0.78rem;
  color: #94a3b8;
  margin-top: 4px;
}
</style>
