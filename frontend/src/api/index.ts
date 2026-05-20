import apiClient from './client'

export const getLoginUrl = () => apiClient.get<{ auth_url: string }>('/auth/login-url')
export const getAuthStatus = () =>
  apiClient.get<{ authenticated: boolean; user_id: string | null; nickname: string | null }>(
    '/auth/status',
  )
export const logout = () => apiClient.post('/auth/logout')

// QR code login
export const getQrcode = () =>
  apiClient.get<{ qr_link: string; qr_data: Record<string, unknown>; cookies: Record<string, string> }>('/auth/qrcode')
export const pollQrcode = (qr_data: Record<string, unknown>, cookies: Record<string, string>) =>
  apiClient.post<{
    status: 'NEW' | 'SCANED' | 'CONFIRMED' | 'EXPIRED' | 'CANCELED'
    session_id?: string
    user_id?: string
    nickname?: string
  }>('/auth/qrcode/poll', { qr_data, cookies })

export const startScan = (sessionId?: string) =>
  apiClient.post<{ task_id: string }>('/scan/start', { session_id: sessionId })
export const pauseScan = (taskId: string) =>
  apiClient.post<{ status: string }>(`/scan/pause/${taskId}`)
export const resumeScan = (taskId: string) =>
  apiClient.post<{ status: string }>(`/scan/resume/${taskId}`)
export const stopScan = (taskId: string) =>
  apiClient.post<{ status: string }>(`/scan/stop/${taskId}`)
export const startDelete = (data: {
  file_ids: string[]
  delete_type: 'trash' | 'permanent'
  file_meta?: any[]
}) => apiClient.post<{ task_id: string }>('/delete/start', data)
export const listTasks = () => apiClient.get<{ tasks: any[] }>('/tasks')
export const getTask = (taskId: string) =>
  apiClient.get<{ task: any; files: any[] }>(`/tasks/${taskId}`)
