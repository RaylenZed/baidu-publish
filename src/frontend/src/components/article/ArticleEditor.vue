<script setup lang="ts">
/**
 * 文章 Markdown 编辑器（PRD §文章管理）。
 * 使用 md-editor-v3 提供实时预览和工具栏。
 */
import { ref, watch } from 'vue'
import { NSpace, NButton, NInput, useMessage } from 'naive-ui'
import { MdEditor } from 'md-editor-v3'
import 'md-editor-v3/lib/style.css'
import { articlesApi } from '@/api'
import type { Article } from '@/types'

const props = defineProps<{
  article: Article
}>()

const emit = defineEmits<{
  saved: [article: Article]
  cancel: []
}>()

const message = useMessage()
const saving = ref(false)
const title = ref(props.article.title)
const bodyMd = ref(props.article.body_md)

// 当父组件传入新 article 时同步
watch(
  () => props.article,
  (a) => {
    title.value = a.title
    bodyMd.value = a.body_md
  },
)

async function save() {
  if (!title.value.trim()) {
    message.warning('标题不能为空')
    return
  }
  saving.value = true
  try {
    const res: any = await articlesApi.update(props.article.id, {
      title: title.value,
      body_md: bodyMd.value,
    })
    message.success('已保存')
    emit('saved', res.data)
  } catch (e: any) {
    message.error(e.response?.data?.message || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="article-editor">
    <div style="margin-bottom: 12px">
      <NInput v-model:value="title" placeholder="文章标题" size="large" />
    </div>
    <MdEditor
      v-model="bodyMd"
      style="height: calc(100vh - 260px); min-height: 400px"
      language="zh-CN"
      :show-code-row-number="true"
    />
    <div style="margin-top: 16px">
      <NSpace justify="end">
        <NButton @click="emit('cancel')">取消</NButton>
        <NButton type="primary" :loading="saving" @click="save">保存</NButton>
      </NSpace>
    </div>
  </div>
</template>
