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

export const startScan = (sessionId?: string, folderIds?: string[], incremental?: boolean, folderNames?: string[]) =>
  apiClient.post<{ task_id: string }>('/scan/start', {
    session_id: sessionId,
    folder_ids: folderIds && folderIds.length > 0 ? folderIds : null,
    folder_names: folderNames && folderNames.length > 0 ? folderNames : null,
    incremental: incremental ?? false,
  })
export const listFolders = (parentId: string, sessionId?: string, parentPath?: string) =>
  apiClient.get<{ folders: Array<{ file_id: string; name: string; has_children: boolean }> }>(
    '/scan/folders',
    { params: { parent_id: parentId, session_id: sessionId, parent_path: parentPath ?? '' } },
  )
export const getFolderIndexStatus = (sessionId?: string) =>
  apiClient.get<{ status: 'idle' | 'building' | 'ready'; total_folders: number; built_at: number | null }>(
    '/scan/folder-index/status',
    { params: { session_id: sessionId } },
  )
export const buildFolderIndex = (sessionId?: string) =>
  apiClient.post<{ status: string; total_folders: number; built_at: number | null }>(
    '/scan/folder-index/build',
    null,
    { params: { session_id: sessionId } },
  )
export const searchFolders = (keyword: string, sessionId?: string, limit = 50) =>
  apiClient.get<{ folders: Array<{ file_id: string; name: string; full_path: string; parent_id: string; has_children: boolean }> }>(
    '/scan/folder-index/search',
    { params: { q: keyword, session_id: sessionId, limit } },
  )
export const pauseScan = (taskId: string) =>
  apiClient.post<{ status: string }>(`/scan/pause/${taskId}`)
export const resumeScan = (taskId: string) =>
  apiClient.post<{ status: string }>(`/scan/resume/${taskId}`)
export const stopScan = (taskId: string) =>
  apiClient.post<{ status: string }>(`/scan/stop/${taskId}`)
export const clearScanCache = (sessionId?: string) =>
  apiClient.delete<{ deleted_count: number }>('/scan/scan-cache', { params: { session_id: sessionId } })
export const startDelete = (data: {
  file_ids: string[]
  delete_type: 'trash' | 'permanent'
  file_meta?: any[]
}) => apiClient.post<{ task_id: string }>('/delete/start', data)
export const listTasks = () => apiClient.get<{ tasks: any[] }>('/tasks')
export const getTask = (taskId: string) =>
  apiClient.get<{ task: any; files: any[] }>(`/tasks/${taskId}`)
