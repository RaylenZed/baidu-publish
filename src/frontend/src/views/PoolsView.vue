<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { NCard, NInput, NInputNumber, NTag, NSpace, NSelect, NButton, useMessage } from 'naive-ui'
import { poolsApi, categoriesApi } from '@/api'

type PoolItem = {
  value: string
  weight: number
  enabled: boolean
}

type PoolData = {
  pool_type: string
  category: string | null
  items: PoolItem[]
}

const message = useMessage()
const loading = ref(false)
const saving = ref(false)

// 原始数据存储
const allPools = ref<PoolData[]>([])

// 当前选择
const currentPoolType = ref('angle')
const currentCategory = ref<string | null>(null)

// 品类列表（从后端 API 动态加载）
const categoryOptions = ref<{ label: string; value: string }[]>([])

// 加载品类列表
async function loadCategories() {
  try {
    const res: any = await categoriesApi.list()
    const list: string[] = res?.data ?? res ?? []
    categoryOptions.value = list.map((c: string) => ({ label: c, value: c }))
  } catch (e) {
    // 降级：使用空列表
    categoryOptions.value = []
  }
}

// 池类型定义
const poolTypes = [
  { value: 'angle', label: '角度 (angle)', needCategory: true },
  { value: 'persona', label: '人设 (persona)', needCategory: true },
  { value: 'style', label: '风格 (style)', needCategory: false },
  { value: 'structure', label: '结构 (structure)', needCategory: false },
  { value: 'title_style', label: '标题风格 (title_style)', needCategory: false },
  { value: 'time_hook', label: '时间钩子 (time_hook)', needCategory: false },
]

// 品类专属池类型
const categoryPoolTypes = new Set(['angle', 'persona'])

// 当前池是否需要选择品类
const currentNeedCategory = computed(() => categoryPoolTypes.has(currentPoolType.value))

// 获取当前池的数据（按 pool_type + category）
const currentPoolData = computed(() => {
  const poolType = currentPoolType.value
  const category = currentNeedCategory.value ? currentCategory.value : null

  return allPools.value.find(p => p.pool_type === poolType && p.category === category)
})

// 获取当前池的 items
const currentItems = computed(() => {
  return currentPoolData.value?.items ?? []
})

onMounted(async () => {
  await loadCategories()
  await loadPools()
})

async function loadPools() {
  loading.value = true
  try {
    const res: any = await poolsApi.list()
    const list: PoolData[] = res?.data ?? res ?? []
    allPools.value = list

    // 设置默认值
    if (list.length > 0) {
      currentPoolType.value = list[0].pool_type
      const firstWithCategory = list.find(p => p.pool_type === currentPoolType.value && p.category)
      currentCategory.value = firstWithCategory?.category ?? categoryOptions.value[0]?.value ?? null
    }
  } finally {
    loading.value = false
  }
}

async function savePool() {
  const poolType = currentPoolType.value
  const pool = ensureCurrentPoolData()

  if (!pool) {
    message.warning('没有数据可保存')
    return
  }
  const category = currentNeedCategory.value ? (pool.category ?? currentCategory.value) : null
  if (currentNeedCategory.value && !category) {
    message.warning('该池类型必须选择品类后才能保存')
    return
  }

  const normalizedItems = pool.items.map((item) => ({
    value: item.value.trim(),
    weight: item.weight,
    enabled: item.enabled,
  }))
  if (normalizedItems.some((item) => !item.value)) {
    message.warning('变量内容不能为空')
    return
  }
  if (!normalizedItems.some((item) => item.enabled)) {
    message.warning('至少启用 1 条变量后才能保存')
    return
  }

  saving.value = true
  try {
    await poolsApi.update(poolType, {
      category: category ?? undefined,
      items: normalizedItems
    })
    message.success('保存成功')
    // 重新加载以确保数据一致
    await loadPools()
  } catch (e: any) {
    message.error('保存失败: ' + (e.message || e))
  } finally {
    saving.value = false
  }
}

function handlePoolTypeChange(poolType: string) {
  currentPoolType.value = poolType
  // 自动选择该池类型已有的第一个品类
  const pools = allPools.value.filter(p => p.pool_type === poolType && p.category)
  if (pools.length > 0) {
    currentCategory.value = pools[0].category
  } else {
    currentCategory.value = categoryOptions.value[0]?.value ?? null
  }
}

function ensureCurrentPoolData() {
  if (currentNeedCategory.value && !currentCategory.value) {
    currentCategory.value = categoryOptions.value[0]?.value ?? null
  }
  if (currentNeedCategory.value && !currentCategory.value) {
    message.warning('请先选择品类')
    return null
  }

  const existing = currentPoolData.value
  if (existing) {
    if (currentNeedCategory.value) {
      existing.category = currentCategory.value
    }
    return existing
  }

  const category = currentNeedCategory.value ? currentCategory.value : null
  const newPool = {
    pool_type: currentPoolType.value,
    category,
    items: [{ value: '', weight: 1, enabled: true }],
  }
  allPools.value.push(newPool)
  return newPool
}

// 本地更新 item（用于 v-model）
function updateItemValue(idx: number, field: 'value' | 'weight', value: any) {
  const pool = ensureCurrentPoolData()
  if (pool && pool.items[idx]) {
    (pool.items[idx] as any)[field] = value
  }
}

function toggleItemEnabled(idx: number) {
  const pool = ensureCurrentPoolData()
  if (pool && pool.items[idx]) {
    (pool.items[idx] as any).enabled = !pool.items[idx].enabled
  }
}

function addItem() {
  const pool = ensureCurrentPoolData()
  if (!pool) return
  pool.items.push({ value: '', weight: 1, enabled: true })
}

function removeItem(idx: number) {
  const pool = ensureCurrentPoolData()
  if (!pool) return
  if (pool.items.length <= 1) {
    message.warning('至少保留 1 条变量')
    return
  }
  pool.items.splice(idx, 1)
}
</script>

<template>
  <div class="pools-page">
    <NCard title="变量池管理">
      <template #header-extra>
        <NSpace>
          <NSelect
            v-model:value="currentPoolType"
            :options="poolTypes"
            style="width: 180px"
            @update:value="handlePoolTypeChange"
          />
          <NSelect
            v-if="currentNeedCategory"
            v-model:value="currentCategory"
            :options="categoryOptions"
            style="width: 140px"
          />
          <NButton @click="addItem">
            + 新增条目
          </NButton>
          <NButton type="primary" :loading="saving" @click="savePool">
            保存
          </NButton>
        </NSpace>
      </template>

      <div v-if="currentPoolData" class="pool-items">
        <div class="pool-info">
          <NTag :type="currentNeedCategory ? 'info' : 'success'">
            {{ currentNeedCategory ? `品类专属池 - ${currentCategory}` : '通用池' }}
          </NTag>
        </div>

        <NSpace v-for="(item, idx) in currentItems" :key="idx" align="center" style="margin-bottom: 8px">
          <NInput
            :value="item.value"
            style="width: 300px"
            @update:value="(v) => updateItemValue(idx, 'value', v)"
          />
          <NInputNumber
            :value="item.weight"
            :min="1"
            :max="100"
            style="width: 80px"
            @update:value="(v) => updateItemValue(idx, 'weight', v)"
          />
          <NTag
            :type="item.enabled ? 'success' : 'default'"
            style="cursor: pointer"
            @click="toggleItemEnabled(idx)"
          >
            {{ item.enabled ? '启用' : '禁用' }}
          </NTag>
          <NButton size="small" type="error" tertiary @click="removeItem(idx)">
            删除
          </NButton>
        </NSpace>

        <div v-if="currentItems.length === 0" class="empty-tip">
          该池暂无数据，请添加后保存
        </div>
      </div>

      <div v-else class="empty-tip">
        该池尚无配置，请添加数据后保存
      </div>
    </NCard>
  </div>
</template>

<style scoped>
.pools-page {
  padding: 0;
}
.pool-items {
  padding: 12px 0;
}
.pool-info {
  margin-bottom: 16px;
}
.empty-tip {
  color: #999;
  text-align: center;
  padding: 24px;
}
</style>
