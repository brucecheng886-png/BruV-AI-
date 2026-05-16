<template>
  <el-dialog
    v-model="visible"
    :title="`分享「${folder?.name || ''}」`"
    width="500px"
    destroy-on-close
    @closed="resetAdd"
  >
    <div v-if="loading" class="fsd-loading">
      <Loader2 :size="22" class="lucide-spin" />
    </div>

    <template v-else>
      <!-- 現有成員清單 -->
      <div class="fsd-section-title">目前白名單（共 {{ perms.length }} 人）</div>
      <el-empty v-if="perms.length === 0" description="尚未授予任何成員存取權" :image-size="40" />
      <div v-else class="fsd-perm-list">
        <div v-for="p in perms" :key="p.id" class="fsd-perm-row">
          <div class="fsd-perm-user">
            <div class="fsd-avatar">{{ (p.user_display_name || p.user_email || '?')[0].toUpperCase() }}</div>
            <div class="fsd-perm-info">
              <div class="fsd-perm-name">{{ p.user_display_name || p.user_email }}</div>
              <div class="fsd-perm-email">{{ p.user_email }}</div>
            </div>
          </div>
          <el-select
            :model-value="p.permission"
            size="small"
            style="width:100px;"
            @change="(v) => updatePerm(p, v)"
          >
            <el-option label="讀取" value="read" />
            <el-option label="編輯" value="write" />
            <el-option label="管理" value="manage" />
          </el-select>
          <el-button
            link
            type="danger"
            size="small"
            :loading="revokingId === p.user_id"
            @click="revoke(p)"
          >
            <X :size="14" :stroke-width="1.5" />
          </el-button>
        </div>
      </div>

      <!-- 新增成員 -->
      <div class="fsd-section-title" style="margin-top:16px;">新增成員</div>
      <div class="fsd-add-row">
        <el-select
          v-model="addForm.userId"
          filterable
          placeholder="搜尋使用者 email"
          size="small"
          style="flex:1;"
          :loading="searchingUsers"
          remote
          :remote-method="searchUsers"
          value-key="id"
        >
          <el-option
            v-for="u in userOptions"
            :key="u.id"
            :label="u.display_name ? `${u.display_name} (${u.email})` : u.email"
            :value="u.id"
          />
        </el-select>
        <el-select v-model="addForm.permission" size="small" style="width:100px;">
          <el-option label="讀取" value="read" />
          <el-option label="編輯" value="write" />
          <el-option label="管理" value="manage" />
        </el-select>
        <el-button
          type="primary"
          size="small"
          :disabled="!addForm.userId"
          :loading="adding"
          @click="addMember"
        >授權</el-button>
      </div>
    </template>

    <template #footer>
      <el-button @click="visible = false">關閉</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch, defineProps, defineEmits } from 'vue'
import { Loader2, X } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import { foldersApi, usersApi } from '../api/index.js'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  folder: { type: Object, default: null },
})
const emit = defineEmits(['update:modelValue'])

const visible = ref(false)
watch(() => props.modelValue, (v) => {
  visible.value = v
  if (v && props.folder) loadPerms()
})
watch(visible, (v) => emit('update:modelValue', v))

const loading = ref(false)
const perms = ref([])

async function loadPerms() {
  if (!props.folder) return
  loading.value = true
  try {
    perms.value = await foldersApi.listPerms(props.folder.id)
  } catch {
    perms.value = []
  } finally {
    loading.value = false
  }
}

// ── 更新權限 ───────────────────────────────
const updatingId = ref(null)
async function updatePerm(p, newPerm) {
  updatingId.value = p.user_id
  try {
    await foldersApi.addPerm(props.folder.id, { user_id: p.user_id, permission: newPerm })
    p.permission = newPerm
    ElMessage.success('已更新')
  } catch {
    ElMessage.error('更新失敗')
  } finally {
    updatingId.value = null
  }
}

// ── 撤銷權限 ───────────────────────────────
const revokingId = ref(null)
async function revoke(p) {
  revokingId.value = p.user_id
  try {
    await foldersApi.removePerm(props.folder.id, p.user_id)
    perms.value = perms.value.filter(x => x.user_id !== p.user_id)
    ElMessage.success('已移除')
  } catch {
    ElMessage.error('移除失敗')
  } finally {
    revokingId.value = null
  }
}

// ── 新增成員 ───────────────────────────────
const addForm = ref({ userId: null, permission: 'read' })
const adding = ref(false)
const searchingUsers = ref(false)
const userOptions = ref([])

async function searchUsers(query) {
  if (!query) { userOptions.value = []; return }
  searchingUsers.value = true
  try {
    const res = await usersApi.list()
    userOptions.value = (res.users || res || []).filter(u =>
      u.email?.toLowerCase().includes(query.toLowerCase()) ||
      u.display_name?.toLowerCase().includes(query.toLowerCase())
    )
  } catch {
    userOptions.value = []
  } finally {
    searchingUsers.value = false
  }
}

async function addMember() {
  if (!addForm.value.userId) return
  adding.value = true
  try {
    const newPerm = await foldersApi.addPerm(props.folder.id, {
      user_id: addForm.value.userId,
      permission: addForm.value.permission,
    })
    const idx = perms.value.findIndex(p => p.user_id === newPerm.user_id)
    if (idx >= 0) perms.value[idx] = newPerm
    else perms.value.unshift(newPerm)
    ElMessage.success('已授權')
    resetAdd()
  } catch {
    ElMessage.error('授權失敗')
  } finally {
    adding.value = false
  }
}

function resetAdd() {
  addForm.value = { userId: null, permission: 'read' }
  userOptions.value = []
}
</script>

<style scoped>
.fsd-loading { display:flex; justify-content:center; padding:24px 0; }
.fsd-section-title {
  font-size: 11px;
  font-weight: 600;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: .04em;
  margin-bottom: 8px;
}
.fsd-perm-list { display:flex; flex-direction:column; gap:6px; }
.fsd-perm-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 8px;
  background: #f8fafc;
}
.fsd-perm-user { display:flex; align-items:center; gap:8px; flex:1; min-width:0; }
.fsd-avatar {
  width: 28px; height: 28px;
  border-radius: 50%;
  background: #dbeafe;
  color: #3b82f6;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 600; flex-shrink: 0;
}
.fsd-perm-info { min-width: 0; }
.fsd-perm-name { font-size: 13px; font-weight: 500; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.fsd-perm-email { font-size: 11px; color: #94a3b8; }
.fsd-add-row { display:flex; gap:8px; align-items:center; }
</style>
