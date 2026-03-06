// 账号类型
export interface Account {
  id: number
  name: string
  categories: string[]
  cookie_status: 'active' | 'expired' | 'unchecked'
  cookie_checked_at: string | null
  created_at: string
  updated_at: string
}

// 任务类型
export interface Task {
  id: number
  account_id: number
  account_name?: string
  schedule_id: number | null
  retry_of_task_id: number | null
  category: string
  mode: 'draft' | 'publish'
  status: 'pending' | 'running' | 'success' | 'failed' | 'canceled' | 'timeout'
  error_type: string | null
  warning: string | null
  combo_id: string | null
  topic_keyword: string | null
  product_name: string | null
  error_message: string | null
  started_at: string | null
  finished_at: string | null
  timeout_at: string | null
  last_step_at: string | null
  created_at: string
}

// 文章类型
export interface Article {
  id: number
  task_id: number
  title: string
  body_md: string
  body_html: string
  raw_draft: string | null
  bjh_article_id: string | null
  cover_url: string | null
  publish_status: 'draft' | 'publishing' | 'published' | 'publish_failed'
  content_warning: string | null
  published_at: string | null
  created_at: string
  updated_at: string
}

// 任务日志
export interface TaskLog {
  id: number
  task_id: number
  step: string
  level: 'INFO' | 'WARN' | 'ERROR'
  message: string
  created_at: string
}

// 定时任务
export interface Schedule {
  id: number
  name: string
  cron_expr: string
  mode: 'draft' | 'publish'
  timezone: string
  enabled: boolean
  last_fired_at: string | null
  next_fire_at: string | null
  created_at: string
  updated_at: string
  accounts?: { account_id: number; account_name: string }[]
}

// 变量池
export interface PoolItem {
  value: string
  weight: number
  enabled: boolean
}

export interface VariablePool {
  pool_type: string
  category: string | null
  items: PoolItem[]
  updated_at: string
}

export interface Category {
  id: number
  name: string
  enabled: boolean
  sort_order: number
  created_at: string
  updated_at: string
}

// 仪表盘统计
export interface DashboardStats {
  success_count: number
  failed_count: number
  running_count: number
  pending_count: number
  total_duration_seconds: number
}

// 分页响应
export interface PageData<T> {
  items: T[]
  total: number
  page: number
  size: number
}

// 统一响应
export interface ApiResponse<T> {
  success: boolean
  data: T
  errorCode?: string
  message?: string
}
