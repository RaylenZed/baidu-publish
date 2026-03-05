<script setup lang="ts">
import { ref, onMounted, h } from 'vue'
import { NCard, NDataTable, NButton, NSpace, NTag, NSelect, NInput, NModal, NForm, NFormItem, useMessage } from 'naive-ui'
import { tasksApi, accountsApi } from '@/api'
import TaskLogDrawer from '@/components/task/TaskLogDrawer.vue'
import type { Task } from '@/types'

const message = useMessage()
const loading = ref(false)
const tasks = ref<Task[]>([])
const total = ref(0)
const page = ref(1)
const statusFilter = ref<string | null>(null)

const accounts = ref<any[]>([])
const showModal = ref(false)
const form = ref({
  account_ids: [] as number[],
  category: '',
  mode: 'draft',
  topic_keyword: '',
  product_name: '',
})

// 日志抽屉
const showLogDrawer = ref(false)
const logTaskId = ref<number | null>(null)
const logTaskStatus = ref<string | undefined>(undefined)

const statusColors: Record<string, any> = {
  success: 'success', failed: 'error', running: 'warning',
  pending: 'info', canceled: 'default', timeout: 'error'
}
const modeColors: Record<string, any> = { draft: 'info', publish: 'warning' }

const columns = [
  { title: 'ID', key: 'id', width: 60 },
  { title: '账号', key: 'account_name', width: 100 },
  { title: '品类', key: 'category', width: 80 },
  { title: '模式', key: 'mode', width: 70, render: (row: Task) => h(NTag, { type: modeColors[row.mode], size: 'small' }, { default: () => row.mode }) },
  { title: '状态', key: 'status', width: 80, render: (row: Task) => h(NTag, { type: statusColors[row.status], size: 'small' }, { default: () => row.status }) },
  { title: 'combo', key: 'combo_id', width: 100 },
  { title: '创建时间', key: 'created_at', width: 160, render: (row: Task) => new Date(row.created_at).toLocaleString() },
  {
    title: '操作', key: 'actions', width: 200,
    render: (row: Task) => h(NSpace, { size: 'small' }, {
      default: () => [
        h(NButton, { size: 'small', onClick: () => viewLogs(row) }, { default: () => '日志' }),
        row.status === 'failed' && h(NButton, { size: 'small', onClick: () => retryTask(row.id) }, { default: () => '重试' }),
        row.status === 'pending' && h(NButton, { size: 'small', onClick: () => cancelTask(row.id) }, { default: () => '取消' }),
        row.status === 'failed' && h(NButton, { size: 'small', onClick: () => forceDraft(row.id) }, { default: () => '草稿' }),
      ].filter(Boolean)
    })
  }
]

onMounted(async () => {
  const [tasksRes, accountsRes] = await Promise.all([
    tasksApi.list({ page: 1, size: 20 }),
    accountsApi.list({ page: 1, size: 100 })
  ])
  tasks.value = (tasksRes as any).data.items
  total.value = (tasksRes as any).data.total
  accounts.value = (accountsRes as any).data.items.map((a: any) => ({ label: a.name, value: a.id }))
})

async function loadTasks() {
  loading.value = true
  try {
    const res: any = await tasksApi.list({ page: page.value, size: 20, status: statusFilter.value || undefined })
    tasks.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

async function createTask() {
  if (!form.value.account_ids.length) return message.warning('请选择账号')
  try {
    await tasksApi.create(form.value)
    message.success('任务创建成功')
    showModal.value = false
    loadTasks()
  } catch (e: any) {
    message.error(e.response?.data?.message || '创建失败')
  }
}

async function retryTask(id: number) {
  try {
    await tasksApi.retry(id)
    message.success('已创建重试任务')
    loadTasks()
  } catch (e) { message.error('重试失败') }
}

async function cancelTask(id: number) {
  try {
    await tasksApi.cancel(id)
    message.success('已取消')
    loadTasks()
  } catch (e) { message.error('取消失败') }
}

async function forceDraft(id: number) {
  try {
    await tasksApi.forceDraft(id)
    message.success('已创建草稿模式任务')
    loadTasks()
  } catch (e) { message.error('操作失败') }
}

function viewLogs(task: Task) {
  logTaskId.value = task.id
  logTaskStatus.value = task.status
  showLogDrawer.value = true
}
</script>

<template>
  <div class="tasks-page">
    <NCard>
      <template #header>
        <NSpace justify="space-between">
          <span>📝 任务管理</span>
          <NSpace>
            <NSelect v-model:value="statusFilter" placeholder="筛选状态" clearable style="width: 120"
              :options="[{label:'全部',value:''},...['pending','running','success','failed','canceled','timeout'].map(s=>({label:s,value:s}))]"
              @update:value="loadTasks" />
            <NButton type="primary" @click="showModal = true">+ 创建任务</NButton>
          </NSpace>
        </NSpace>
      </template>

      <NDataTable :columns="columns" :data="tasks" :loading="loading" :bordered="false" />
    </NCard>

    <!-- 创建任务弹窗 -->
    <NModal v-model:show="showModal" title="创建任务" preset="card" style="width: 500px">
      <NForm label-placement="top">
        <NFormItem label="选择账号">
          <NSelect v-model:value="form.account_ids" multiple :options="accounts" placeholder="选择账号" />
        </NFormItem>
        <NFormItem label="品类">
          <NInput v-model:value="form.category" placeholder="留空则随机" />
        </NFormItem>
        <NFormItem label="运行模式">
          <NSelect v-model:value="form.mode" :options="[{label:'仅保存草稿',value:'draft'},{label:'发布',value:'publish'}]" />
        </NFormItem>
        <NFormItem label="主题关键词">
          <NInput v-model:value="form.topic_keyword" placeholder="可选" />
        </NFormItem>
        <NFormItem label="指定产品">
          <NInput v-model:value="form.product_name" placeholder="可选" />
        </NFormItem>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showModal = false">取消</NButton>
          <NButton type="primary" @click="createTask">创建</NButton>
        </NSpace>
      </template>
    </NModal>

    <!-- 实时日志抽屉 -->
    <TaskLogDrawer
      v-model:show="showLogDrawer"
      :task-id="logTaskId"
      :task-status="logTaskStatus"
    />
  </div>
</template>

<style scoped>
.tasks-page { padding: 0; }
</style>
