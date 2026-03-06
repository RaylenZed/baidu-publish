<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  NCard,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NSelect,
  NButton,
  NDivider,
  NModal,
  NTag,
  NSpace,
  NSwitch,
  NPopconfirm,
  useMessage,
} from 'naive-ui'
import { categoriesApi, settingsApi } from '@/api'
import type { Category } from '@/types'

const message = useMessage()
const loading = ref(false)
const categoryLoading = ref(false)
const categorySaving = ref(false)
const showCategoryModal = ref(false)
const editingCategoryId = ref<number | null>(null)

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
const categories = ref<Category[]>([])
const categoryForm = ref({
  name: '',
  enabled: true,
  sort_order: null as number | null,
})

onMounted(async () => {
  await Promise.all([loadSettings(), loadCategories()])
})

async function loadSettings() {
  loading.value = true
  try {
    const res: any = await settingsApi.get()
    form.value = {
      ...form.value,
      ...res.data,
      wecom_webhook: res.data.wecom_webhook ?? '',
    }
  } finally {
    loading.value = false
  }
}

async function loadCategories() {
  categoryLoading.value = true
  try {
    const res: any = await categoriesApi.manageList()
    categories.value = res?.data ?? res ?? []
  } catch (e: any) {
    message.error(e.response?.data?.message || '加载品类失败')
  } finally {
    categoryLoading.value = false
  }
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
  } catch (e: any) {
    message.error(e.response?.data?.message || '保存失败')
  }
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
  } catch (e: any) {
    message.error(e.response?.data?.message || '修改失败')
  }
}

function openCreateCategory() {
  editingCategoryId.value = null
  categoryForm.value = {
    name: '',
    enabled: true,
    sort_order: null,
  }
  showCategoryModal.value = true
}

function openEditCategory(category: Category) {
  editingCategoryId.value = category.id
  categoryForm.value = {
    name: category.name,
    enabled: category.enabled,
    sort_order: category.sort_order,
  }
  showCategoryModal.value = true
}

async function saveCategory() {
  if (!categoryForm.value.name.trim()) {
    message.warning('请输入品类名称')
    return
  }

  categorySaving.value = true
  try {
    const payload = {
      name: categoryForm.value.name.trim(),
      enabled: categoryForm.value.enabled,
      sort_order: categoryForm.value.sort_order,
    }
    if (editingCategoryId.value) {
      await categoriesApi.update(editingCategoryId.value, payload)
      message.success('品类更新成功')
    } else {
      await categoriesApi.create(payload)
      message.success('品类创建成功，已自动补齐 starter 变量池')
    }
    showCategoryModal.value = false
    await loadCategories()
  } catch (e: any) {
    message.error(e.response?.data?.message || '保存品类失败')
  } finally {
    categorySaving.value = false
  }
}

async function deleteCategory(id: number) {
  try {
    await categoriesApi.delete(id)
    message.success('品类删除成功')
    await loadCategories()
  } catch (e: any) {
    message.error(e.response?.data?.message || '删除失败')
  }
}
</script>

<template>
  <div class="settings-page">
    <NCard title="⚙️ 系统设置">
      <NForm label-placement="left" label-width="140">
        <NFormItem label="默认运行模式">
          <NSelect
            v-model:value="form.run_mode"
            :options="[{ label: '草稿', value: 'draft' }, { label: '发布', value: 'publish' }]"
            style="width: 200px"
          />
        </NFormItem>
        <NFormItem label="AIGC 模型">
          <NSelect
            v-model:value="form.aigc_model"
            :options="[{ label: 'DeepSeek V3', value: 'ds_v3' }, { label: '文心一言', value: 'ernie' }]"
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
            :options="[{ label: '全部', value: 'all' }, { label: '仅失败', value: 'failure_only' }, { label: '关闭', value: 'off' }]"
            style="width: 200px"
          />
        </NFormItem>
        <NFormItem>
          <NButton type="primary" @click="saveSettings">保存设置</NButton>
        </NFormItem>
      </NForm>

      <NDivider />

      <h3>修改密码</h3>
      <NForm label-placement="left" label-width="100" style="margin-top: 16px">
        <NFormItem label="旧密码">
          <NInput v-model:value="oldPassword" type="password" style="width: 200px" />
        </NFormItem>
        <NFormItem label="新密码">
          <NInput v-model:value="newPassword" type="password" style="width: 200px" />
        </NFormItem>
        <NFormItem>
          <NButton @click="changePassword">修改密码</NButton>
        </NFormItem>
      </NForm>
    </NCard>

    <NCard title="品类管理" style="margin-top: 16px">
      <template #header-extra>
        <NButton type="primary" @click="openCreateCategory">
          + 新增品类
        </NButton>
      </template>

      <div class="category-hint">
        新增品类后，系统会自动创建一套 starter 角度池/人设池。精细化内容请到变量池页继续补充。
      </div>

      <div v-if="categoryLoading" class="category-empty">
        品类加载中...
      </div>
      <table v-else-if="categories.length > 0" class="category-table">
        <thead>
          <tr>
            <th>品类名称</th>
            <th>状态</th>
            <th>排序</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="category in categories" :key="category.id">
            <td>{{ category.name }}</td>
            <td>
              <NTag :type="category.enabled ? 'success' : 'default'">
                {{ category.enabled ? '启用' : '停用' }}
              </NTag>
            </td>
            <td>{{ category.sort_order }}</td>
            <td>
              <NSpace>
                <NButton size="small" @click="openEditCategory(category)">
                  编辑
                </NButton>
                <NPopconfirm @positive-click="deleteCategory(category.id)">
                  <template #trigger>
                    <NButton size="small" tertiary type="error">
                      删除
                    </NButton>
                  </template>
                  确认删除该品类？若已被账号或历史任务使用，会被后端拒绝。
                </NPopconfirm>
              </NSpace>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="category-empty">
        暂无品类数据
      </div>
    </NCard>

    <NModal
      v-model:show="showCategoryModal"
      preset="card"
      :title="editingCategoryId ? '编辑品类' : '新增品类'"
      style="width: 420px"
    >
      <NForm label-placement="left" label-width="90">
        <NFormItem label="品类名称">
          <NInput v-model:value="categoryForm.name" placeholder="例如：办公家具" />
        </NFormItem>
        <NFormItem label="是否启用">
          <NSwitch v-model:value="categoryForm.enabled" />
        </NFormItem>
        <NFormItem label="排序">
          <NInputNumber v-model:value="categoryForm.sort_order" :min="0" :max="999" />
        </NFormItem>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showCategoryModal = false">取消</NButton>
          <NButton type="primary" :loading="categorySaving" @click="saveCategory">
            保存
          </NButton>
        </NSpace>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
.settings-page {
  padding: 0;
}

.category-hint {
  margin-bottom: 16px;
  color: #666;
  line-height: 1.6;
}

.category-table {
  width: 100%;
  border-collapse: collapse;
}

.category-table th,
.category-table td {
  padding: 12px 10px;
  border-bottom: 1px solid #f0f0f0;
  text-align: left;
}

.category-empty {
  padding: 24px 0;
  color: #999;
}
</style>
