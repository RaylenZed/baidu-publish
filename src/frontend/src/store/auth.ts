import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('token'))
  const user = ref<string | null>('admin')

  const isLoggedIn = computed(() => !!token.value)

  async function login(password: string) {
    const resp: any = await authApi.login(password)
    token.value = resp.data.access_token
    localStorage.setItem('token', token.value!)
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('token')
  }

  async function refreshToken() {
    try {
      const resp: any = await authApi.refresh()
      token.value = resp.data.access_token
      localStorage.setItem('token', token.value!)
    } catch {
      logout()
    }
  }

  return { token, user, isLoggedIn, login, logout, refreshToken }
})
