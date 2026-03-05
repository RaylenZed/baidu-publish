<script setup lang="ts">
import { ref, onMounted, h } from 'vue'
import { NCard, NDataTable, NButton, NSpace, NTag, NInput, NModal, NForm, NFormItem, NSelect, NPopconfirm, useMessage } from 'naive-ui'
import { accountsApi, categoriesApi } from '@/api'
import type { Account } from '@/types'

const message = useMessage()
const loading = ref(false)
const accounts = ref<Account[]>([])
const total = ref(0)
const page = ref(1)
const showModal = ref(false)
const editingAccount = ref<Partial<Account> & { cookie?: string }>({})
const isEdit = ref(false)

// 导入导出相关
const showImportModal = ref(false)
const importData = ref('')
const importPassphrase = ref('')
const exportPassphrase = ref('')
const exporting = ref(false)
const checkingAll = ref(false)

const columns = [
  { title: 'ID', key: 'id', width: 60 },
  { title: '账号名称', key: 'name' },
  { title: '绑定品类', key: 'categories', render: (row: Account) => row.categories?.join(', ') || '-' },
  {
    title: 'Cookie 状态',
    key: 'cookie_status',
    width: 120,
    render: (row: Account) => {
      const map = { active: { text: '🟢 正常', type: 'success' }, expired: { text: '🔴 过期', type: 'error' }, unchecked: { text: '⚪ 未检测', type: 'warning' } }
      const s = map[row.cookie_status] || map.unchecked
      return h(NTag, { type: s.type as any, size: 'small' }, { default: () => s.text })
    }
  },
  {
    title: '操作',
    key: 'actions',
    width: 200,
    render: (row: Account) => h(NSpace, { size: 'small' }, {
      default: () => [
        h(NButton, { size: 'small', onClick: () => editAccount(row) }, { default: () => '编辑' }),
        h(NButton, { size: 'small', onClick: () => checkCookie(row.id) }, { default: () => '检测' }),
        h(NPopconfirm, { onPositiveClick: () => deleteAccount(row.id) }, {
          trigger: () => h(NButton, { size: 'small', tertiary: true, type: 'error' }, { default: () => '删除' }),
          default: () => '确定删除此账号？'
        })
      ]
    })
  }
]

const categoryOptions = ref<string[]>([])

onMounted(async () => {
  try {
    const res = await categoriesApi.list() as any
    categoryOptions.value = res?.data ?? res ?? []
  } catch {
    categoryOptions.value = []
  }
  loadAccounts()
})

async function loadAccounts() {
  loading.value = true
  try {
    const res = await accountsApi.list({ page: page.value, size: 20 })
    accounts.value = res.data.items
    total.value = res.data.total
  } catch (e) {
    message.error('加载失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingAccount.value = {}
  isEdit.value = false
  showModal.value = true
}

function editAccount(acc: Account) {
  editingAccount.value = { ...acc }
  isEdit.value = true
  showModal.value = true
}

async function saveAccount() {
  try {
    if (isEdit.value && editingAccount.value.id) {
      await accountsApi.update(editingAccount.value.id, editingAccount.value as any)
      message.success('更新成功')
    } else {
      await accountsApi.create(editingAccount.value as any)
      message.success('创建成功')
    }
    showModal.value = false
    loadAccounts()
  } catch (e: any) {
    message.error(e.response?.data?.message || '操作失败')
  }
}

async function checkCookie(id: number) {
  try {
    await accountsApi.checkCookie(id)
    message.success('检测成功')
    loadAccounts()
  } catch (e) {
    message.error('检测失败')
  }
}

async function deleteAccount(id: number) {
  try {
    await accountsApi.delete(id)
    message.success('删除成功')
    loadAccounts()
  } catch (e: any) {
    message.error(e.response?.data?.message || '删除失败')
  }
}

// 批量检测
async function checkAllCookies() {
  checkingAll.value = true
  try {
    const res: any = await accountsApi.checkAll()
    const result = res.data
    message.info(`检测完成：成功 ${result.success_count}，失败 ${result.failed_count}`)
    loadAccounts()
  } catch (e) {
    message.error('批量检测失败')
  } finally {
    checkingAll.value = false
  }
}

// 导出
async function exportAccounts() {
  if (!exportPassphrase.value) {
    message.warning('请输入加密口令')
    return
  }
  exporting.value = true
  try {
    const res: any = await accountsApi.export(exportPassphrase.value)
    const data = res.data.data
    // 创建下载
    const blob = new Blob([data], { type: 'application/octet-stream' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `accounts_${new Date().toISOString().slice(0,10)}.bin`
    a.click()
    URL.revokeObjectURL(url)
    message.success('导出成功')
  } catch (e: any) {
    message.error(e.response?.data?.message || '导出失败')
  } finally {
    exporting.value = false
  }
}

// 导入
async function importAccounts() {
  if (!importData.value || !importPassphrase.value) {
    message.warning('请填写加密数据和解密口令')
    return
  }
  try {
    const res: any = await accountsApi.import(importData.value, importPassphrase.value)
    const result = res.data
    message.success(`导入成功：新增 ${result.added}，更新 ${result.updated}，跳过 ${result.skipped}`)
    showImportModal.value = false
    importData.value = ''
    importPassphrase.value = ''
    loadAccounts()
  } catch (e: any) {
    message.error(e.response?.data?.message || '导入失败')
  }
}
</script>

<template>
  <div class="accounts-page">
    <NCard>
      <template #header>
        <NSpace justify="space-between">
          <span>👤 账号管理</span>
          <NSpace>
            <NButton size="small" @click="checkAllCookies" :loading="checkingAll">批量检测</NButton>
            <NButton size="small" @click="showImportModal = true">导入</NButton>
            <NButton size="small" :disabled="accounts.length === 0" @click="exportAccounts" :loading="exporting">导出</NButton>
            <NButton type="primary" @click="openCreate">+ 新增账号</NButton>
          </NSpace>
        </NSpace>
      </template>

      <NDataTable
        :columns="columns"
        :data="accounts"
        :loading="loading"
        :pagination="{ pageSize: 20 }"
        :bordered="false"
      />
    </NCard>

    <NModal v-model:show="showModal" :title="isEdit ? '编辑账号' : '新增账号'" preset="card" style="width: 500px">
      <NForm label-placement="left" label-width="80">
        <NFormItem label="账号名称">
          <NInput v-model:value="editingAccount.name" placeholder="如：账号1-图书" />
        </NFormItem>
        <NFormItem label="Cookie">
          <NInput v-model:value="editingAccount.cookie" type="textarea" placeholder="请粘贴 BDUSS=xxx" :rows="3" />
        </NFormItem>
        <NFormItem label="绑定品类">
          <NSelect
            v-model:value="editingAccount.categories"
            multiple
            :options="categoryOptions.map(c => ({ label: c, value: c }))"
            placeholder="选择 1-2 个品类"
          />
        </NFormItem>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showModal = false">取消</NButton>
          <NButton type="primary" @click="saveAccount">保存</NButton>
        </NSpace>
      </template>
    </NModal>

    <NModal v-model:show="showImportModal" title="导入账号" preset="card" style="width: 500px">
      <NForm label-placement="top">
        <NFormItem label="解密口令">
          <NInput v-model:value="importPassphrase" type="password" placeholder="请输入导出时设置的口令" />
        </NFormItem>
        <NFormItem label="加密数据（Base64）">
          <NInput v-model:value="importData" type="textarea" placeholder="请粘贴导出文件的内容（Base64 字符串）" :rows="6" />
        </NFormItem>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showImportModal = false">取消</NButton>
          <NButton type="primary" @click="importAccounts">导入</NButton>
        </NSpace>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
.accounts-page {
  padding: 0;
}
</style>