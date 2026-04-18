<template>
  <div style="min-height:100vh;display:flex;align-items:center;justify-content:center;background:#f0f2f5;">
    <el-card style="width:400px;">
      <template #header>
        <div style="text-align:center;font-size:20px;font-weight:bold;">🧠 AI 知識庫登入</div>
      </template>
      <el-form :model="form" label-width="60px" @submit.prevent="handleLogin">
        <el-form-item label="Email">
          <el-input v-model="form.email" placeholder="admin@local" />
        </el-form-item>
        <el-form-item label="密碼">
          <el-input v-model="form.password" type="password" placeholder="••••••••" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" native-type="submit" :loading="loading" style="width:100%;">
            登入
          </el-button>
        </el-form-item>
        <p v-if="error" style="color:red;text-align:center;font-size:13px;">{{ error }}</p>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'

const router = useRouter()
const authStore = useAuthStore()
const form = reactive({ email: '', password: '' })
const loading = ref(false)
const error = ref('')

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    await authStore.login(form.email, form.password)
    router.push('/chat')
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>
