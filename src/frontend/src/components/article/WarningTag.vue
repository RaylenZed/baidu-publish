<script setup lang="ts">
import { NTag, NTooltip } from 'naive-ui'

defineProps<{
  warning: string | null
}>()

const warningLabels: Record<string, string> = {
  partial_content: 'SSE截断，内容不完整，需人工确认',
}
</script>

<template>
  <NTooltip v-if="warning" :delay="300">
    <template #trigger>
      <NTag type="warning" size="small">⚠️ {{ warning }}</NTag>
    </template>
    {{ warningLabels[warning] ?? warning }}
  </NTooltip>
</template>
