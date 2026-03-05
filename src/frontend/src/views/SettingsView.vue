<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { NCard, NForm, NFormItem, NInput, NInputNumber, NSelect, NButton, NDivider, useMessage } from 'naive-ui'
import { settingsApi } from '@/api'

const message = useMessage()
const loading = ref(false)
const form = ref({
  run_mode: 'draft',
  aigc_model: 'ds_v3',
  account_delay: 10,
  max_concurrent_accounts: 1,
  daily_limit: 3,
  task_timeout_minutes: 15,
  generate_timeout: 240,
  polish_timeout: 240,
  cover_timeout: 60,
  publish_timeout: 60,
  draft_timeout: 60,
  wecom_webhook: '',
  notify_level: 'failure_only',
})
const oldPassword = ref('')
const newPassword = ref('')

onMounted(loadSettings)

async function loadSettings() {
  loading.value = true
  try {
    const res = await settingsApi.get()
    form.value = {
      ...form.value,
      ...res.data,
      // 后端返回 null 时统一映射为输入框可编辑值
      wecom_webhook: res.data.wecom_webhook ?? '',
    }
  } finally { loading.value = false }
}

async function saveSettings() {
  try {
    const payload = {
      run_mode: form.value.run_mode,
      aigc_model: form.value.aigc_model,
      account_delay: form.value.account_delay,
      max_concurrent_accounts: form.value.max_concurrent_accounts,
      daily_limit: form.value.daily_limit,
      task_timeout_minutes: form.value.task_timeout_minutes,
      generate_timeout: form.value.generate_timeout,
      polish_timeout: form.value.polish_timeout,
      cover_timeout: form.value.cover_timeout,
      publish_timeout: form.value.publish_timeout,
      draft_timeout: form.value.draft_timeout,
      wecom_webhook: form.value.wecom_webhook,
      notify_level: form.value.notify_level,
    }
    await settingsApi.update(payload)
    message.success('保存成功')
  } catch (e: any) { message.error(e.response?.data?.message || '保存失败') }
}

async function changePassword() {
  if (!oldPassword.value || !newPassword.value) {
    message.warning('请填写新旧密码')
    return
  }
  try {
    await settingsApi.changePassword(oldPassword.value, newPassword.value)
    message.success('密码修改成功，请重新登录')
    oldPassword.value = ''
    newPassword.value = ''
  } catch (e: any) { message.error(e.response?.data?.message || '修改失败') }
}
</script>

<template>
  <div class="settings-page">
    <NCard title="⚙️ 系统设置">
      <NForm label-placement="left" label-width="140">
        <NFormItem label="默认运行模式">
          <NSelect
            v-model:value="form.run_mode"
            :options="[{label:'草稿',value:'draft'},{label:'发布',value:'publish'}]"
            style="width: 200px"
          />
        </NFormItem>
        <NFormItem label="AIGC 模型">
          <NSelect
            v-model:value="form.aigc_model"
            :options="[{label:'DeepSeek V3',value:'ds_v3'},{label:'文心一言',value:'ernie'}]"
            style="width: 200px"
          />
        </NFormItem>
        <NFormItem label="账号间延迟(秒)">
          <NInputNumber v-model:value="form.account_delay" :min="1" :max="300" />
        </NFormItem>
        <NFormItem label="跨账号并发数">
          <NInputNumber v-model:value="form.max_concurrent_accounts" :min="1" :max="3" />
        </NFormItem>
        <NFormItem label="每日发布上限">
          <NInputNumber v-model:value="form.daily_limit" :min="1" :max="100" />
        </NFormItem>
        <NFormItem label="任务超时(分钟)">
          <NInputNumber v-model:value="form.task_timeout_minutes" :min="10" :max="600" />
        </NFormItem>
        <NFormItem label="生成超时(秒)">
          <NInputNumber v-model:value="form.generate_timeout" :min="30" :max="600" />
        </NFormItem>
        <NFormItem label="润色超时(秒)">
          <NInputNumber v-model:value="form.polish_timeout" :min="30" :max="600" />
        </NFormItem>
        <NFormItem label="封面超时(秒)">
          <NInputNumber v-model:value="form.cover_timeout" :min="10" :max="300" />
        </NFormItem>
        <NFormItem label="发布超时(秒)">
          <NInputNumber v-model:value="form.publish_timeout" :min="10" :max="300" />
        </NFormItem>
        <NFormItem label="草稿超时(秒)">
          <NInputNumber v-model:value="form.draft_timeout" :min="10" :max="300" />
        </NFormItem>
        <NFormItem label="企微 Webhook">
          <NInput
            v-model:value="form.wecom_webhook"
            placeholder="企业微信机器人 webhook 地址（留空将清除）"
          />
        </NFormItem>
        <NFormItem label="通知级别">
          <NSelect
            v-model:value="form.notify_level"
            :options="[{label:'全部',value:'all'},{label:'仅失败',value:'failure_only'},{label:'关闭',value:'off'}]"
            style="width: 200px"
          />
        </NFormItem>
        <NFormItem>
          <NButton type="primary" @click="saveSettings">保存设置</NButton>
        </NFormItem>
      </NForm>

      <NDivider />

      <h3>修改密码</h3>
      <NForm label-placement="left" label-width="100" style="margin-top:16px">
        <NFormItem label="旧密码"><NInput type="password" v-model:value="oldPassword" style="width:200px" /></NFormItem>
        <NFormItem label="新密码"><NInput type="password" v-model:value="newPassword" style="width:200px" /></NFormItem>
        <NFormItem><NButton @click="changePassword">修改密码</NButton></NFormItem>
      </NForm>
    </NCard>
  </div>
</template>

<style scoped>
.settings-page { padding: 0; }
</style>
