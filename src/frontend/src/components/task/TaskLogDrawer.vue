<script setup lang="ts">
import { ref, watch, nextTick, computed } from 'vue'
import { NDrawer, NDrawerContent, NSpace, NTag, NSpin, NEmpty, NScrollbar } from 'naive-ui'
import { useTaskLogStream } from '@/composables/useTaskLogStream'

const props = defineProps<{
  show: boolean
  taskId: number | null
  taskStatus?: string
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
}>()

const taskIdRef = computed(() => (props.show ? props.taskId : null))
const { logs, connected, connecting, error } = useTaskLogStream(taskIdRef)

const scrollbarRef = ref<InstanceType<typeof NScrollbar> | null>(null)

// 新日志到来时自动滚到底部
watch(
  () => logs.value.length,
  async () => {
    await nextTick()
    scrollbarRef.value?.scrollTo({ top: 999999, behavior: 'smooth' })
  },
)

const levelType: Record<string, 'default' | 'info' | 'warning' | 'error'> = {
  INFO: 'info',
  WARN: 'warning',
  ERROR: 'error',
}

function formatTime(ts: string) {
  return new Date(ts).toLocaleTimeString('zh-CN', { hour12: false })
}

function close() {
  emit('update:show', false)
}

</script>

<template>
  <NDrawer :show="show" :width="600" placement="right" @update:show="emit('update:show', $event)">
    <NDrawerContent :title="`任务 #${taskId ?? ''} 日志`" closable @close="close">
      <!-- 状态栏 -->
      <div style="margin-bottom: 12px">
        <NSpace size="small" align="center">
          <template v-if="connecting">
            <NSpin size="small" />
            <span style="color: #aaa; font-size: 13px">连接中…</span>
          </template>
          <template v-else-if="connected">
            <span style="width: 8px; height: 8px; border-radius: 50%; background: #18a058; display: inline-block" />
            <span style="color: #18a058; font-size: 13px">实时</span>
          </template>
          <template v-else>
            <span style="color: #aaa; font-size: 13px">{{ error ?? '已断开' }}</span>
          </template>
          <NTag v-if="logs.length" size="small">{{ logs.length }} 条</NTag>
        </NSpace>
      </div>

      <!-- 日志列表 -->
      <NScrollbar ref="scrollbarRef" style="height: calc(100vh - 180px)">
        <NEmpty v-if="!logs.length && !connecting" description="暂无日志" style="margin-top: 80px" />
        <div
          v-for="log in logs"
          :key="log.id"
          style="
            display: flex;
            gap: 8px;
            align-items: flex-start;
            padding: 4px 8px;
            font-family: monospace;
            font-size: 12px;
            line-height: 1.6;
            border-bottom: 1px solid #f0f0f0;
          "
        >
          <span style="color: #999; white-space: nowrap; flex-shrink: 0">
            {{ formatTime(log.created_at) }}
          </span>
          <NTag :type="levelType[log.level] ?? 'default'" size="small" style="flex-shrink: 0; font-size: 10px">
            {{ log.level }}
          </NTag>
          <span style="color: #888; flex-shrink: 0">{{ log.step }}</span>
          <span :style="{ color: log.level === 'ERROR' ? '#d03050' : log.level === 'WARN' ? '#e07c00' : '#333', flex: 1, wordBreak: 'break-word' }">
            {{ log.message }}
          </span>
        </div>
      </NScrollbar>
    </NDrawerContent>
  </NDrawer>
</template>
