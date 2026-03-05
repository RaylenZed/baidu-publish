<script setup lang="ts">
import { NConfigProvider, NMessageProvider, NDialogProvider, NNotificationProvider, NLayout, NLayoutSider, NLayoutContent, NMenu, NAvatar, NDropdown, NSpace, NButton, NBadge } from 'naive-ui'
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/store/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const menuOptions: any = [
  { label: '仪表盘', key: 'dashboard', icon: '📊' },
  { label: '账号管理', key: 'accounts', icon: '👤' },
  { label: '任务管理', key: 'tasks', icon: '📝' },
  { label: '文章管理', key: 'articles', icon: '📄' },
  { label: '定时任务', key: 'schedules', icon: '⏰' },
  { label: '变量池', key: 'pools', icon: '🎯' },
  { label: '系统日志', key: 'system-logs', icon: '📋' },
  { label: '系统设置', key: 'settings', icon: '⚙️' },
]

const activeKey = computed(() => route.name as string)

const userOptions = [
  { label: '退出登录', key: 'logout' },
]

function handleMenuSelect(key: string) {
  router.push({ name: key })
}

function handleUserAction(key: string) {
  if (key === 'logout') {
    authStore.logout()
    router.push({ name: 'login' })
  }
}

const isLoggedIn = computed(() => authStore.isLoggedIn)
</script>

<template>
  <NConfigProvider>
    <NMessageProvider>
      <NDialogProvider>
        <NNotificationProvider>
          <div v-if="!isLoggedIn" class="app-container">
            <router-view />
          </div>
          <div v-else class="app-container">
            <NLayout has-sider>
              <NLayoutSider bordered collapse-mode="width" :collapsed-width="64" :width="220" show-trigger="bar" :native-scrollbar="false">
                <div class="sider-header">
                  <h2>百家号发布</h2>
                </div>
                <NMenu
                  :collapsed-width="64"
                  :collapsed-icon-size="22"
                  :options="menuOptions"
                  :value="activeKey"
                  @update:value="handleMenuSelect"
                />
              </NLayoutSider>
              <NLayout>
                <NLayoutHeader bordered class="header">
                  <div class="header-right">
                    <NBadge :value="3" :max="99">
                      <NButton quaternary circle>🔔</NButton>
                    </NBadge>
                    <NDropdown :options="userOptions" @select="handleUserAction">
                      <NSpace align="center" :size="8" class="user-info">
                        <NAvatar round size="small">管</NAvatar>
                        <span>管理员</span>
                      </NSpace>
                    </NDropdown>
                  </div>
                </NLayoutHeader>
                <NLayoutContent content-style="padding: 16px;" :native-scrollbar="false">
                  <router-view />
                </NLayoutContent>
              </NLayout>
            </NLayout>
          </div>
        </NNotificationProvider>
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>

<style scoped>
.app-container {
  height: 100vh;
  width: 100vw;
}
.sider-header {
  padding: 16px;
  text-align: center;
}
.sider-header h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}
.header {
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 0 16px;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}
.user-info {
  cursor: pointer;
}
</style>