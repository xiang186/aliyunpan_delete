import { defineStore } from 'pinia'
import type { DuplicateGroup } from '@/types'

export const useScanStore = defineStore('scan', {
  state: () => ({
    groups: [] as DuplicateGroup[],
    isScanning: false,
    isPaused: false,
    progress: { fetched_count: 0, total_count: null as number | null, percentage: 0 },
    taskId: null as string | null,
    error: null as string | null,
  }),
  getters: {
    totalGroups: (state) => state.groups.length,
    totalFiles: (state) => state.groups.reduce((sum, g) => sum + g.duplicate_count, 0),
    totalSizeBytes: (state) =>
      state.groups.reduce((sum, g) => sum + g.file_size * (g.duplicate_count - 1), 0),
  },
  actions: {
    setGroups(groups: DuplicateGroup[]) {
      this.groups = groups
    },
    setProgress(p: { fetched_count: number; total_count: number | null; percentage: number }) {
      this.progress = p
      try {
        sessionStorage.setItem('scan_progress', JSON.stringify(p))
      } catch {
        // ignore
      }
    },
    setScanning(v: boolean) {
      this.isScanning = v
      if (!v) this.isPaused = false
    },
    setPaused(v: boolean) {
      this.isPaused = v
    },
    setTaskId(id: string | null) {
      this.taskId = id
      if (id) {
        sessionStorage.setItem('scan_task_id', id)
        console.log('[scan store] setTaskId saved:', id)
      } else {
        sessionStorage.removeItem('scan_task_id')
        console.log('[scan store] setTaskId cleared')
      }
    },
    setError(e: string | null) {
      this.error = e
    },
    /** Persist completed scan result so it survives multiple page refreshes. */
    persistResult(groups: DuplicateGroup[]) {
      this.groups = groups
      try {
        sessionStorage.setItem('scan_result', JSON.stringify(groups))
        console.log('[scan store] persistResult saved groups:', groups.length)
      } catch {
        console.warn('[scan store] persistResult failed (quota?)')
      }
    },
    /** Persist partial groups found during an in-progress scan. */
    persistPartial(groups: DuplicateGroup[]) {
      this.groups = groups
      try {
        sessionStorage.setItem('scan_partial', JSON.stringify(groups))
      } catch {
        // quota exceeded — ignore, partial data is best-effort
      }
    },
    /** Restore partial groups from a previous in-progress scan. */
    restorePartial(): boolean {
      try {
        const raw = sessionStorage.getItem('scan_partial')
        if (raw) {
          this.groups = JSON.parse(raw) as DuplicateGroup[]
          return this.groups.length > 0
        }
      } catch {
        sessionStorage.removeItem('scan_partial')
      }
      return false
    },
    /** Restore persisted result from sessionStorage (if any). */
    restoreResult(): boolean {
      try {
        const raw = sessionStorage.getItem('scan_result')
        console.log('[scan store] restoreResult raw length:', raw?.length ?? 0)
        if (raw) {
          this.groups = JSON.parse(raw) as DuplicateGroup[]
          console.log('[scan store] restoreResult loaded groups:', this.groups.length)
          return true
        }
      } catch {
        console.warn('[scan store] restoreResult parse failed')
        sessionStorage.removeItem('scan_result')
      }
      return false
    },
    /** Restore persisted progress from sessionStorage. */
    restoreProgress(): boolean {
      try {
        const raw = sessionStorage.getItem('scan_progress')
        if (raw) {
          this.progress = JSON.parse(raw)
          return true
        }
      } catch {
        sessionStorage.removeItem('scan_progress')
      }
      return false
    },
    getPersistedTaskId(): string | null {
      return sessionStorage.getItem('scan_task_id')
    },
    reset() {
      this.groups = []
      this.isScanning = false
      this.isPaused = false
      this.progress = { fetched_count: 0, total_count: null, percentage: 0 }
      this.taskId = null
      this.error = null
      sessionStorage.removeItem('scan_task_id')
      sessionStorage.removeItem('scan_result')
      sessionStorage.removeItem('scan_partial')
      sessionStorage.removeItem('scan_progress')
    },
  },
})
