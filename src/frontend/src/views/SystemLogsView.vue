<script setup lang="ts">
import { h, ref, onMounted } from 'vue'
import {
  NCard,
  NDataTable,
  NSpace,
  NSelect,
  NInput,
  NButton,
  NPagination,
  NTag,
  NDatePicker,
} from 'naive-ui'
import { settingsApi } from '@/api'
import type { DataTableColumns, SelectOption } from 'naive-ui'

interface LogItem {
  id: number
  task_id: number | null
  account_name: string | null
  step: string
  level: string
  message: string
  created_at: string
}

const loading = ref(false)
const logs = ref<LogItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)

const filterLevel = ref<string | undefined>(undefined)
const filterKeyword = ref('')
const filterDateRange = ref<[number, number] | null>(null)

const levelOptions: SelectOption[] = [
  { label: 'INFO', value: 'INFO' },
  { label: 'WARN', value: 'WARN' },
  { label: 'ERROR', value: 'ERROR' },
]

const levelTagType = (level: string): 'error' | 'warning' | 'default' => {
  if (level === 'ERROR') return 'error'
  if (level === 'WARN') return 'warning'
  return 'default'
}

const columns: DataTableColumns<LogItem> = [
  {
    title: '时间',
    key: 'created_at',
    width: 160,
    render: (row) => row.created_at?.slice(0, 19).replace('T', ' ') ?? '-',
  },
  {
    title: '级别',
    key: 'level',
    width: 80,
    render: (row) => h(NTag, { type: levelTagType(row.level), size: 'small' }, { default: () => row.level }),
  },
  { title: '步骤', key: 'step', width: 90 },
  { title: '任务ID', key: 'task_id', width: 80, render: (row) => String(row.task_id ?? '-') },
  { title: '账号', key: 'account_name', width: 120, render: (row) => row.account_name ?? '-' },
  { title: '日志内容', key: 'message', ellipsis: { tooltip: true } },
]

async function load() {
  loading.value = true
  try {
    const params: Record<string, unknown> = {
      page: page.value,
      size: pageSize.value,
    }
    if (filterLevel.value) params.level = filterLevel.value
    if (filterKeyword.value) params.keyword = filterKeyword.value
    if (filterDateRange.value) {
      params.date_from = new Date(filterDateRange.value[0]).toISOString()
      params.date_to = new Date(filterDateRange.value[1]).toISOString()
    }
    const res = await settingsApi.logs(params as Parameters<typeof settingsApi.logs>[0]) as any
    const data = res?.data ?? res
    logs.value = data.items ?? []
    total.value = data.total ?? 0
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  page.value = 1
  load()
}

function handleReset() {
  filterLevel.value = undefined
  filterKeyword.value = ''
  filterDateRange.value = null
  handleSearch()
}

function handlePageChange(p: number) {
  page.value = p
  load()
}

onMounted(load)
</script>

<template>
  <div class="system-logs-page">
    <NCard title="📋 系统日志">
      <NSpace vertical>
        <!-- 筛选栏 -->
        <NSpace align="center">
          <NSelect
            v-model:value="filterLevel"
            :options="levelOptions"
            placeholder="日志级别"
            style="width: 120px"
            clearable
          />
          <NInput
            v-model:value="filterKeyword"
            placeholder="关键词搜索"
            style="width: 200px"
            clearable
          />
          <NDatePicker
            v-model:value="filterDateRange"
            type="datetimerange"
            clearable
            placeholder="时间范围"
            style="width: 340px"
          />
          <NButton type="primary" @click="handleSearch">查询</NButton>
          <NButton @click="handleReset">重置</NButton>
        </NSpace>

        <!-- 日志表格 -->
        <NDataTable
          :columns="columns"
          :data="logs"
          :loading="loading"
          :row-key="(row: LogItem) => row.id"
          size="small"
          striped
          :max-height="600"
        />

        <!-- 分页 -->
        <NSpace justify="end">
          <NPagination
            v-model:page="page"
            :item-count="total"
            :page-size="pageSize"
            show-quick-jumper
            @update:page="handlePageChange"
          />
        </NSpace>
      </NSpace>
    </NCard>
  </div>
</template>

<style scoped>
.system-logs-page {
  padding: 0;
}
</style>
