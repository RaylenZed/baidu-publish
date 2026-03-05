import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'

const API_BASE = '/api/v1'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('token'))
  const user = ref<string | null>('admin')

  const isLoggedIn = computed(() => !!token.value)

  // 设置 axios 默认 token
  if (token.value) {
    axios.defaults.headers.common['Authorization'] = `Bearer ${token.value}`
  }

  async function login(password: string) {
    const resp = await axios.post(`${API_BASE}/auth/login`, { password })
    token.value = resp.data.data.access_token  // 匹配后端返回字段
    localStorage.setItem('token', token.value!)
    axios.defaults.headers.common['Authorization'] = `Bearer ${token.value}`
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('token')
    delete axios.defaults.headers.common['Authorization']
  }

  async function refreshToken() {
    try {
      const resp = await axios.post(`${API_BASE}/auth/refresh`)
      token.value = resp.data.data.access_token
      localStorage.setItem('token', token.value!)
      axios.defaults.headers.common['Authorization'] = `Bearer ${token.value}`
    } catch {
      logout()
    }
  }

  return { token, user, isLoggedIn, login, logout, refreshToken }
})