import axios from 'axios'
import router from '@/router'

const apiClient = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// 请求拦截器：注入 X-Session-ID header
apiClient.interceptors.request.use((config) => {
  const sessionId = localStorage.getItem('session_id')
  if (sessionId) {
    config.headers['X-Session-ID'] = sessionId
  }
  return config
})

// 响应拦截器：处理 401 跳转登录
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('session_id')
      router.push('/login')
    }
    return Promise.reject(error)
  },
)

export default apiClient
