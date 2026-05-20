import { defineStore } from 'pinia'
import { getAuthStatus } from '@/api'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    sessionId: localStorage.getItem('session_id') as string | null,
    userId: null as string | null,
    nickname: null as string | null,
    isAuthenticated: false,
  }),
  actions: {
    setSession(sessionId: string, userId?: string | null, nickname?: string | null) {
      this.sessionId = sessionId
      this.userId = userId ?? null
      this.nickname = nickname ?? null
      this.isAuthenticated = true
      localStorage.setItem('session_id', sessionId)
    },
    clearSession() {
      this.sessionId = null
      this.userId = null
      this.nickname = null
      this.isAuthenticated = false
      localStorage.removeItem('session_id')
    },
    async checkAuth() {
      if (!this.sessionId) {
        this.isAuthenticated = false
        return
      }
      try {
        const res = await getAuthStatus()
        this.isAuthenticated = res.data.authenticated
        this.userId = res.data.user_id
        this.nickname = res.data.nickname
      } catch {
        this.isAuthenticated = false
      }
    },
  },
})
