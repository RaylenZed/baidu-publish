<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { NCard, NForm, NFormItem, NInput, NButton, NSpace, NAlert } from 'naive-ui'
import { useAuthStore } from '@/store/auth'

const router = useRouter()
const authStore = useAuthStore()

const loading = ref(false)
const errorMsg = ref('')
const form = ref({
  password: '',
})

async function handleLogin() {
  if (!form.value.password) {
    errorMsg.value = '请输入密码'
    return
  }

  loading.value = true
  errorMsg.value = ''

  try {
    await authStore.login(form.value.password)
    router.push({ name: 'dashboard' })
  } catch (err: any) {
    errorMsg.value = err.response?.data?.message || '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-container">
    <NCard class="login-card" title="百家号自动化发布管理系统">
      <template #header-extra>
        <span>🚀</span>
      </template>

      <NAlert v-if="errorMsg" type="error" :show-icon="false" style="margin-bottom: 16px">
        {{ errorMsg }}
      </NAlert>

      <NForm>
        <NFormItem label="管理员密码">
          <NInput
            v-model:value="form.password"
            type="password"
            placeholder="请输入管理员密码"
            @keyup.enter="handleLogin"
          />
        </NFormItem>

        <NSpace vertical :size="16">
          <NButton
            type="primary"
            block
            :loading="loading"
            @click="handleLogin"
          >
            登录
          </NButton>
        </NSpace>
      </NForm>
    </NCard>
  </div>
</template>

<style scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}
.login-card {
  width: 400px;
}
</style>