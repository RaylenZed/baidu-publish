<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  NCard, NStatistic, NGrid, NGi, NSpace, NSpin, NEmpty, NTag
} from 'naive-ui'
import { dashboardApi } from '@/api'
import type { DashboardStats } from '@/types'

interface AccountHealthItem {
  account_id: number
  account_name: string
  cookie_status: 'active' | 'expired' | 'unchecked'
  cookie_checked_at: string | null
}

const loading = ref(false)
const stats = ref<DashboardStats | null>(null)
const recentTasks = ref<any[]>([])
const accountHealth = ref<AccountHealthItem[]>([])

const statusColors: Record<string, 'success' | 'error' | 'warning' | 'info' | 'default'> = {
  success: 'success',
  failed: 'error',
  running: 'warning',
  pending: 'info',
  canceled: 'default',
  timeout: 'error',
}

onMounted(async () => {
  loading.value = true
  try {
    const [statsRes, tasksRes, healthRes] = await Promise.all([
      dashboardApi.stats(),
      dashboardApi.recentTasks(),
      dashboardApi.accountHealth(),
    ])
    stats.value = statsRes.data
    recentTasks.value = tasksRes.data
    accountHealth.value = healthRes.data
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
})

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}秒`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}分`
  return `${Math.floor(seconds / 3600)}小时${Math.floor((seconds % 3600) / 60)}分`
}
</script>

<template>
  <div class="dashboard">
    <NSpin :show="loading">
      <!-- 统计卡片 -->
      <NGrid :x-gap="16" :y-gap="16" cols="4" responsive="screen">
        <NGi>
          <NCard>
            <NStatistic label="今日成功" :value="stats?.success_count || 0">
              <template #prefix>✅</template>
            </NStatistic>
          </NCard>
        </NGi>
        <NGi>
          <NCard>
            <NStatistic label="今日失败" :value="stats?.failed_count || 0">
              <template #prefix>❌</template>
            </NStatistic>
          </NCard>
        </NGi>
        <NGi>
          <NCard>
            <NStatistic label="待执行" :value="stats?.pending_count || 0">
              <template #prefix>⏳</template>
            </NStatistic>
          </NCard>
        </NGi>
        <NGi>
          <NCard>
            <NStatistic label="总耗时" :value="formatDuration(stats?.total_duration_seconds || 0)">
              <template #prefix>⏱️</template>
            </NStatistic>
          </NCard>
        </NGi>
      </NGrid>

      <NSpace style="margin-top: 24px" :size="16">
        <!-- 账号健康度 -->
        <NCard title="👤 账号健康度" style="flex: 1">
          <NEmpty v-if="!accountHealth.length" description="暂无账号" />
          <div v-else class="health-list">
            <div v-for="acc in accountHealth" :key="acc.account_id" class="health-item">
              <span class="name">{{ acc.account_name }}</span>
              <NTag :type="acc.cookie_status === 'active' ? 'success' : acc.cookie_status === 'expired' ? 'error' : 'warning'">
                {{ acc.cookie_status === 'active' ? '🟢 正常' : acc.cookie_status === 'expired' ? '🔴 过期' : '⚪ 未检测' }}
              </NTag>
            </div>
          </div>
        </NCard>

        <!-- 最近任务 -->
        <NCard title="📝 最近任务" style="flex: 1">
          <NEmpty v-if="!recentTasks.length" description="暂无任务" />
          <div v-else class="task-list">
            <div v-for="task in recentTasks.slice(0, 10)" :key="task.id" class="task-item">
              <NTag :type="statusColors[task.status]" size="small">
                {{ task.status }}
              </NTag>
              <span class="account">{{ task.account_name }}</span>
              <span class="category">{{ task.category }}</span>
            </div>
          </div>
        </NCard>
      </NSpace>
    </NSpin>
  </div>
</template>

<style scoped>
.dashboard {
  padding: 0;
}
.health-list, .task-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.health-item, .task-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}
.health-item .name, .task-item .account {
  flex: 1;
  font-weight: 500;
}
.task-item .category {
  color: #666;
  font-size: 12px;
}
</style>