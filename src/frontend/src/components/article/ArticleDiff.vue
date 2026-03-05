<script setup lang="ts">
/**
 * 初稿 vs 润色内容 Diff 对比视图（PRD §文章管理）。
 * 使用 diff2html side-by-side 格式展示差异。
 */
import { computed } from 'vue'
import { NEmpty } from 'naive-ui'
import { createTwoFilesPatch } from 'diff'
import { html as diff2htmlHtml } from 'diff2html'
import 'diff2html/bundles/css/diff2html.min.css'
import type { Article } from '@/types'

const props = defineProps<{
  article: Article
}>()

const diffHtml = computed(() => {
  const original = props.article.raw_draft ?? ''
  const modified = props.article.body_md ?? ''
  if (!original && !modified) return ''

  const patch = createTwoFilesPatch('初稿', '润色后', original, modified, '', '')
  return diff2htmlHtml(patch, {
    drawFileList: false,
    matching: 'lines',
    outputFormat: 'side-by-side',
  })
})

const hasDiff = computed(
  () => !!props.article.raw_draft && props.article.raw_draft !== props.article.body_md,
)
</script>

<template>
  <div class="article-diff">
    <NEmpty v-if="!article.raw_draft" description="无初稿数据（任务未启用 diff 保存）" style="margin: 40px 0" />
    <NEmpty v-else-if="!hasDiff" description="初稿与当前内容一致，无差异" style="margin: 40px 0" />
    <!-- eslint-disable-next-line vue/no-v-html -->
    <div v-else class="diff-container" v-html="diffHtml" />
  </div>
</template>

<style scoped>
.diff-container {
  overflow-x: auto;
  font-size: 12px;
  line-height: 1.5;
}
</style>
