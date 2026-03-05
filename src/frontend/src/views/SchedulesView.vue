<script setup lang="ts">
import { ref, onMounted, h } from 'vue'
import { NCard, NDataTable, NButton, NSpace, NTag, NModal, NForm, NFormItem, NInput, NSelect, NSwitch, useMessage } from 'naive-ui'
import { schedulesApi, accountsApi } from '@/api'

const message = useMessage()
const schedules = ref<any[]>([])
const accounts = ref<any[]>([])
const showModal = ref(false)
const isEdit = ref(false)
const editingId = ref<number | null>(null)
const form = ref({ name: '', cron_expr: '', mode: 'draft', account_ids: [] as number[], timezone: 'Asia/Shanghai' })

const columns = [
  { title: 'ID', key: 'id', width: 60 },
  { title: '名称', key: 'name' },
  { title: 'Cron', key: 'cron_expr', width: 120 },
  { title: '模式', key: 'mode', width: 80, render: (row: any) => h(NTag, { type: row.mode === 'publish' ? 'warning' : 'info', size: 'small' }, { default: () => row.mode }) },
  { title: '状态', key: 'enabled', width: 80, render: (row: any) => h(NTag, { type: row.enabled ? 'success' : 'default', size: 'small' }, { default: () => row.enabled ? '启用' : '禁用' }) },
  { title: '下次触发', key: 'next_fire_at', width: 160, render: (row: any) => row.next_fire_at ? new Date(row.next_fire_at).toLocaleString() : '-' },
  {
    title: '操作', key: 'actions', width: 280,
    render: (row: any) => h(NSpace, { size: 'small' }, {
      default: () => [
        h(NButton, { size: 'small', onClick: () => openEdit(row) }, { default: () => '编辑' }),
        h(NSwitch, { size: 'small', value: row.enabled, onUpdateValue: () => toggleSchedule(row.id) }),
        h(NButton, { size: 'small', onClick: () => fireSchedule(row.id) }, { default: () => '触发' }),
        h(NButton, { size: 'small', onClick: () => deleteSchedule(row.id) }, { default: () => '删除' }),
      ]
    })
  }
]

onMounted(async () => {
  const [sRes, aRes] = await Promise.all([schedulesApi.list(), accountsApi.list()])
  schedules.value = sRes.data
  accounts.value = aRes.data.items.map((a: any) => ({ label: a.name, value: a.id }))
})

async function loadSchedules() {
  const res = await schedulesApi.list()
  schedules.value = res.data
}

function openCreate() {
  form.value = { name: '', cron_expr: '', mode: 'draft', account_ids: [], timezone: 'Asia/Shanghai' }
  isEdit.value = false
  showModal.value = true
}

function openEdit(row: any) {
  editingId.value = row.id
  form.value = {
    name: row.name,
    cron_expr: row.cron_expr,
    mode: row.mode,
    account_ids: row.accounts?.map((a: any) => a.account_id) || [],
    timezone: row.timezone || 'Asia/Shanghai'
  }
  isEdit.value = true
  showModal.value = true
}

async function saveSchedule() {
  try {
    if (isEdit.value && editingId.value) {
      await schedulesApi.update(editingId.value, form.value)
      message.success('更新成功')
    } else {
      await schedulesApi.create(form.value)
      message.success('创建成功')
    }
    showModal.value = false
    loadSchedules()
  } catch (e: any) {
    message.error(e.response?.data?.message || '操作失败')
  }
}

async function toggleSchedule(id: number) {
  try {
    await schedulesApi.toggle(id)
    loadSchedules()
  } catch (e) { message.error('操作失败') }
}

async function fireSchedule(id: number) {
  try {
    await schedulesApi.fire(id)
    message.success('已触发')
  } catch (e) { message.error('触发失败') }
}

async function deleteSchedule(id: number) {
  try {
    await schedulesApi.delete(id)
    message.success('删除成功')
    loadSchedules()
  } catch (e) { message.error('删除失败') }
}
</script>

<template>
  <div class="schedules-page">
    <NCard>
      <template #header>
        <NSpace justify="space-between">
          <span>⏰ 定时任务</span>
          <NButton type="primary" @click="openCreate">+ 新建定时</NButton>
        </NSpace>
      </template>
      <NDataTable :columns="columns" :data="schedules" :bordered="false" />
    </NCard>

    <NModal v-model:show="showModal" :title="isEdit ? '编辑定时任务' : '新建定时任务'" preset="card" style="width: 500px">
      <NForm label-placement="top">
        <NFormItem label="任务名称"><NInput v-model:value="form.name" placeholder="如：每日9点发布" /></NFormItem>
        <NFormItem label="Cron 表达式"><NInput v-model:value="form.cron_expr" placeholder="0 9 * * *" /></NFormItem>
        <NFormItem label="运行模式"><NSelect v-model:value="form.mode" :options="[{label:'草稿',value:'draft'},{label:'发布',value:'publish'}]" /></NFormItem>
        <NFormItem label="时区"><NSelect v-model:value="form.timezone" :options="[{label:'上海',value:'Asia/Shanghai'},{label:'北京',value:'Asia/Shanghai'}]" /></NFormItem>
        <NFormItem label="选择账号"><NSelect v-model:value="form.account_ids" multiple :options="accounts" /></NFormItem>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showModal = false">取消</NButton>
          <NButton type="primary" @click="saveSchedule">{{ isEdit ? '保存' : '创建' }}</NButton>
        </NSpace>
      </template>
    </NModal>
  </div>
</template>

<style scoped>.schedules-page{padding:0}</style>