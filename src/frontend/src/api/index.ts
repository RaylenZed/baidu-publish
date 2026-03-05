import axios, { type AxiosResponse } from 'axios'

const apiBaseUrl =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || '/api/v1'

const client = axios.create({
  baseURL: apiBaseUrl,
  timeout: 30000,
})

// 请求拦截器 - 自动添加 token
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器 - 统一错误处理
client.interceptors.response.use(
  (response: AxiosResponse) => response.data,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default client

// === 认证 API ===
export const authApi = {
  login: (password: string) => client.post('/auth/login', { password }),
  refresh: () => client.post('/auth/refresh'),
  wsTicket: () => client.post('/auth/ws-ticket'),
}

// === 仪表盘 API ===
export const dashboardApi = {
  stats: () => client.get('/dashboard/stats'),
  recentTasks: (limit = 20) => client.get(`/dashboard/recent-tasks?limit=${limit}`),
  accountHealth: () => client.get('/dashboard/account-health'),
}

// === 账号 API ===
export const accountsApi = {
  list: (params?: { page?: number; size?: number; keyword?: string }) =>
    client.get('/accounts', { params }),
  get: (id: number) => client.get(`/accounts/${id}`),
  create: (data: { name: string; cookie: string; categories: string[] }) =>
    client.post('/accounts', data),
  update: (id: number, data: { name?: string; cookie?: string; categories?: string[] }) =>
    client.put(`/accounts/${id}`, data),
  delete: (id: number) => client.delete(`/accounts/${id}`),
  checkCookie: (id: number) => client.post(`/accounts/${id}/check-cookie`),
  checkAll: () => client.post('/accounts/check-all'),
  export: (passphrase: string) => client.post('/accounts/export', { passphrase }),
  import: (data: string, passphrase: string) =>
    client.post('/accounts/import', { data, passphrase }),
}

// === 任务 API ===
export const tasksApi = {
  list: (params?: {
    page?: number
    size?: number
    status?: string
    account_id?: number
    category?: string
    mode?: string
    date_from?: string
    date_to?: string
  }) => client.get('/tasks', { params }),
  get: (id: number) => client.get(`/tasks/${id}`),
  getLogs: (id: number) => client.get(`/tasks/${id}/logs`),
  create: (data: {
    account_ids: number[]
    category?: string
    mode: string
    topic_keyword?: string
    product_name?: string
    idempotency_key?: string
  }) => client.post('/tasks', data),
  retry: (id: number) => client.post(`/tasks/${id}/retry`),
  cancel: (id: number) => client.post(`/tasks/${id}/cancel`),
  forceDraft: (id: number) => client.post(`/tasks/${id}/force-draft`),
  retryFailed: () => client.post('/tasks/retry-failed'),
  publishDrafts: () => client.post('/tasks/publish-drafts'),
}

// === 文章 API ===
export const articlesApi = {
  list: (params?: {
    page?: number
    size?: number
    account_id?: number
    publish_status?: string
    content_warning?: string
  }) => client.get('/articles', { params }),
  get: (id: number) => client.get(`/articles/${id}`),
  update: (id: number, data: { title: string; body_md: string }) =>
    client.put(`/articles/${id}`, data),
  confirm: (id: number) => client.post(`/articles/${id}/confirm`),
  publish: (id: number) => client.post(`/articles/${id}/publish`),
}

// === 定时任务 API ===
export const schedulesApi = {
  list: (enabled?: boolean) => client.get('/schedules', { params: { enabled } }),
  get: (id: number) => client.get(`/schedules/${id}`),
  create: (data: {
    name: string
    cron_expr: string
    mode: string
    timezone?: string
    account_ids: number[]
    topic_keyword?: string
    product_name?: string
  }) => client.post('/schedules', data),
  update: (id: number, data: Partial<{
    name: string
    cron_expr: string
    mode: string
    timezone: string
    account_ids: number[]
    topic_keyword: string
    product_name: string
  }>) => client.put(`/schedules/${id}`, data),
  delete: (id: number) => client.delete(`/schedules/${id}`),
  toggle: (id: number) => client.post(`/schedules/${id}/toggle`),
  fire: (id: number) => client.post(`/schedules/${id}/fire`),
}

// === 变量池 API ===
export const poolsApi = {
  list: () => client.get('/pools'),
  get: (poolType: string, category?: string) =>
    client.get(`/pools/${poolType}`, { params: { category } }),
  update: (poolType: string, data: { category?: string; items: any[] }) =>
    client.put(`/pools/${poolType}`, data),
  comboHistory: (params?: { account_id?: number; category?: string; days?: number }) =>
    client.get('/pools/combo-history', { params }),
}

// === 品类 API ===
export const categoriesApi = {
  list: () => client.get<string[]>('/settings/categories'),
}

// === 系统设置 API ===
export const settingsApi = {
  get: () => client.get('/settings'),
  update: (data: any) => client.put('/settings', data),
  changePassword: (oldPassword: string, newPassword: string) =>
    client.put('/settings/password', { old_password: oldPassword, new_password: newPassword }),
  logs: (params?: {
    page?: number
    size?: number
    level?: string
    step?: string
    task_id?: number
    date_from?: string
    date_to?: string
    keyword?: string
  }) => client.get('/settings/logs', { params }),
}
