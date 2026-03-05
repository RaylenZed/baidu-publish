/**
 * WebSocket 实时日志流 composable（PRD §WS）。
 *
 * 使用流程：
 *  1. 先从 REST API 拉取历史日志（回放）
 *  2. 再通过 ws_ticket 建立 WebSocket，订阅增量日志
 *  3. 组件销毁时自动断开连接
 */
import { ref, onUnmounted, watch, type Ref } from 'vue'
import { tasksApi, authApi } from '@/api'
import type { TaskLog } from '@/types'

function resolveWsBase(): string {
  const customWsBase = (import.meta.env.VITE_WS_BASE_URL as string | undefined)?.trim()
  if (customWsBase) {
    return customWsBase.replace(/\/$/, '')
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}`
}

export function useTaskLogStream(taskId: Ref<number | null>) {
  const logs = ref<TaskLog[]>([])
  const connected = ref(false)
  const connecting = ref(false)
  const error = ref<string | null>(null)

  let ws: WebSocket | null = null

  async function connect(id: number) {
    disconnect()
    connecting.value = true
    error.value = null
    logs.value = []

    // 1. 拉取历史日志
    try {
      const res: any = await tasksApi.getLogs(id)
      logs.value = res.data ?? []
    } catch {
      // 历史日志拉取失败不阻塞 WebSocket 连接
    }

    // 2. 获取一次性 ws_ticket
    let ticket: string
    try {
      const res: any = await authApi.wsTicket()
      ticket = res.data?.ticket
      if (!ticket) throw new Error('ticket 为空')
    } catch (e: any) {
      error.value = '获取 ws_ticket 失败'
      connecting.value = false
      return
    }

    // 3. 建立 WebSocket 连接
    const wsBase = resolveWsBase()
    const wsUrl = `${wsBase}/ws/tasks/${id}/logs?ticket=${ticket}`

    ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      connected.value = true
      connecting.value = false
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)

        // 仅处理 type=log 的日志消息，忽略 history_end/done/error 等控制消息
        if (data.type !== 'log') {
          return
        }

        // 将后端 ts 字段映射为前端期望的 created_at
        const log: TaskLog = {
          id: data.id,
          task_id: id,  // 使用当前连接的 taskId
          step: data.step,
          level: data.level,
          message: data.message,
          created_at: data.ts,
        }

        // 按 created_at + step 去重（避免实时推送的日志因 id=0 被过滤）
        // 后端实时日志的 id 在写入 DB 前为 0，去重键改用时间戳+步骤
        const logKey = `${log.created_at}-${log.step}`
        const alreadyExists = logs.value.some((l) => `${l.created_at}-${l.step}` === logKey)
        if (!alreadyExists) {
          logs.value.push(log)
        }
      } catch {
        // 忽略格式异常的消息
      }
    }

    ws.onclose = () => {
      connected.value = false
      connecting.value = false
    }

    ws.onerror = () => {
      error.value = 'WebSocket 连接错误'
      connected.value = false
      connecting.value = false
    }
  }

  function disconnect() {
    if (ws) {
      ws.close()
      ws = null
    }
    connected.value = false
    connecting.value = false
  }

  watch(
    taskId,
    (id) => {
      if (id != null) {
        connect(id)
      } else {
        disconnect()
        logs.value = []
      }
    },
    { immediate: false },
  )

  onUnmounted(disconnect)

  return { logs, connected, connecting, error, connect, disconnect }
}
