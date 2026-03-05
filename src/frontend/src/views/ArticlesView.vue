<script setup lang="ts">
import { ref, onMounted, h } from 'vue'
import { NCard, NDataTable, NButton, NSpace, NTag, NModal, NTabs, NTabPane, useMessage } from 'naive-ui'
import { articlesApi } from '@/api'
import ArticleEditor from '@/components/article/ArticleEditor.vue'
import ArticleDiff from '@/components/article/ArticleDiff.vue'
import WarningTag from '@/components/article/WarningTag.vue'
import type { Article } from '@/types'

const message = useMessage()
const loading = ref(false)
const articles = ref<Article[]>([])
const total = ref(0)

// 查看/编辑弹窗
const showModal = ref(false)
const activeTab = ref<'edit' | 'diff'>('edit')
const selectedArticle = ref<Article | null>(null)

const statusColors: Record<string, any> = {
  draft: 'info', publishing: 'warning', published: 'success', publish_failed: 'error'
}

const columns = [
  { title: 'ID', key: 'id', width: 60 },
  { title: '标题', key: 'title', ellipsis: { tooltip: true } },
  {
    title: '发布状态', key: 'publish_status', width: 110,
    render: (row: Article) => h(NTag, { type: statusColors[row.publish_status], size: 'small' }, { default: () => row.publish_status })
  },
  {
    title: '内容警告', key: 'content_warning', width: 150,
    render: (row: Article) => h(WarningTag, { warning: row.content_warning })
  },
  { title: '百家号ID', key: 'bjh_article_id', width: 100 },
  {
    title: '创建时间', key: 'created_at', width: 160,
    render: (row: Article) => new Date(row.created_at).toLocaleString()
  },
  {
    title: '操作', key: 'actions', width: 200,
    render: (row: Article) => h(NSpace, { size: 'small' }, {
      default: () => [
        h(NButton, { size: 'small', onClick: () => openArticle(row, 'edit') }, { default: () => '查看/编辑' }),
        row.raw_draft && h(NButton, { size: 'small', onClick: () => openArticle(row, 'diff') }, { default: () => 'Diff' }),
        row.publish_status === 'draft' && row.content_warning && h(NButton, { size: 'small', type: 'warning', onClick: () => confirmArticle(row.id) }, { default: () => '确认' }),
        row.publish_status === 'draft' && !row.content_warning && h(NButton, { size: 'small', type: 'primary', onClick: () => publishArticle(row.id) }, { default: () => '发布' }),
      ].filter(Boolean)
    })
  }
]

onMounted(loadArticles)

async function loadArticles() {
  loading.value = true
  try {
    const res: any = await articlesApi.list({ page: 1, size: 20 })
    articles.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

function openArticle(article: Article, tab: 'edit' | 'diff') {
  selectedArticle.value = article
  activeTab.value = tab
  showModal.value = true
}

function onArticleSaved(updated: Article) {
  // 更新列表中的对应条目
  const idx = articles.value.findIndex((a) => a.id === updated.id)
  if (idx >= 0) articles.value[idx] = updated
  selectedArticle.value = updated
}

async function confirmArticle(id: number) {
  try {
    await articlesApi.confirm(id)
    message.success('已确认，可进行发布')
    loadArticles()
  } catch (e) { message.error('确认失败') }
}

async function publishArticle(id: number) {
  try {
    await articlesApi.publish(id)
    message.success('发布成功')
    loadArticles()
  } catch (e: any) { message.error(e.response?.data?.message || '发布失败') }
}
</script>

<template>
  <div class="articles-page">
    <NCard title="📄 文章管理">
      <NDataTable :columns="columns" :data="articles" :loading="loading" :bordered="false" />
    </NCard>

    <!-- 查看/编辑弹窗 -->
    <NModal
      v-model:show="showModal"
      preset="card"
      :title="selectedArticle ? selectedArticle.title : '文章详情'"
      style="width: 900px; max-width: 95vw"
      :mask-closable="false"
    >
      <NTabs v-if="selectedArticle" v-model:value="activeTab">
        <NTabPane name="edit" tab="编辑">
          <ArticleEditor
            :article="selectedArticle"
            @saved="onArticleSaved"
            @cancel="showModal = false"
          />
        </NTabPane>
        <NTabPane name="diff" tab="初稿对比">
          <ArticleDiff :article="selectedArticle" />
        </NTabPane>
      </NTabs>
    </NModal>
  </div>
</template>

<style scoped>
.articles-page { padding: 0; }
</style>
