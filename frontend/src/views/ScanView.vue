<template>
  <div class="scan-view">
    <!-- 顶部导航 -->
    <el-header class="app-header">
      <div class="header-left">
        <el-icon size="20"><Files /></el-icon>
        <span class="app-title">阿里云盘重复文件清理</span>
      </div>
      <div class="header-right">
        <el-button text @click="router.push('/history')">历史记录</el-button>
        <el-button text @click="handleLogout">退出登录</el-button>
      </div>
    </el-header>

    <el-main class="main-content">
      <!-- 扫描按钮 -->
      <div class="scan-controls">
        <el-button type="primary" :loading="scanStore.isScanning && !scanStore.isPaused" @click="() => handleScan()" :disabled="scanStore.isScanning">
          {{ scanStore.isScanning ? '扫描中...' : '扫描重复文件' }}
        </el-button>
        <el-button :icon="Folder" @click="showFolderDialog = true" :disabled="scanStore.isScanning">
          选择目录
        </el-button>
        <el-button
          :icon="Refresh"
          @click="() => handleScan(true)"
          :disabled="scanStore.isScanning"
          title="跳过未变更目录，只扫描新增或变更的部分"
        >
          增量扫描
        </el-button>
        <el-button
          :icon="Delete"
          @click="handleClearScanCache"
          :disabled="scanStore.isScanning"
          title="清除增量扫描缓存，下次扫描将重新全量遍历所有目录"
        >
          清除扫描缓存
        </el-button>
        <template v-if="scanStore.isScanning && scanStore.taskId">
          <el-button v-if="!scanStore.isPaused" @click="handlePause">
            <el-icon><VideoPause /></el-icon> 暂停
          </el-button>
          <el-button v-else type="success" @click="handleResume">
            <el-icon><VideoPlay /></el-icon> 继续
          </el-button>
          <el-button type="danger" plain @click="handleStop">
            停止并使用当前结果
          </el-button>
        </template>
        <span v-if="scanStore.groups.length > 0 && !scanStore.isScanning" class="scan-hint">
          上次扫描发现 {{ scanStore.groups.length }} 组重复文件
        </span>
      </div>

      <!-- 当前扫描目录提示 -->
      <div v-if="selectedFolderNames.length > 0" class="scan-scope-hint">
        <el-icon><FolderOpened /></el-icon>
        <span>当前扫描目录：</span>
        <template v-if="selectedFolderNames.length <= 3">
          <el-tag
            v-for="name in selectedFolderNames"
            :key="name"
            size="small"
            type="info"
            style="margin-right: 4px"
          >{{ name }}</el-tag>
        </template>
        <template v-else>
          <el-tag
            v-for="name in selectedFolderNames.slice(0, 3)"
            :key="name"
            size="small"
            type="info"
            style="margin-right: 4px"
          >{{ name }}</el-tag>
          <span class="scope-more">等 {{ selectedFolderNames.length }} 个目录</span>
        </template>
        <el-button link size="small" @click="scanStore.setSelectedFolders([], [])" style="margin-left: 4px">清除</el-button>
      </div>

      <!-- 扫描/删除进度 -->
      <ProgressPanel
        v-if="showProgress"
        :is-active="showProgress"
        :mode="progressMode"
        :progress="currentProgress"
        :result="operationResult"
        :error="progressError"
        :elapsed-seconds="elapsedSeconds"
        :completed="scanCompleted"
        :completed-fetched-count="completedFetchedCount"
        style="margin-bottom: 12px"
      />

      <!-- 统计汇总 -->
      <StatsSummary
        v-if="filteredGroups.length > 0 || scanStore.groups.length > 0"
        :total-groups="stats.totalGroups.value"
        :total-files="stats.totalFiles.value"
        :deletable-files="stats.deletableFiles.value"
        :total-size-bytes="stats.totalSizeBytes.value"
        :scanned-file-count="scanStore.scannedFileCount || undefined"
        :selected-count="stats.selectedCount.value"
        :selected-size-bytes="stats.selectedSizeBytes.value"
        style="margin-bottom: 12px"
      />

      <!-- 筛选工具栏 + 每页条数 -->
      <div v-if="scanStore.groups.length > 0" class="toolbar-row" style="margin-bottom: 12px">
        <FilterBar
          v-model:keyword="keyword"
          v-model:selected-file-type="selectedFileType"
          v-model:sort-field="sortField"
          v-model:sort-order="sortOrder"
          style="flex: 1"
        />
        <div class="page-size-selector">
          <span class="page-size-label">每页显示：</span>
          <el-select v-model="pageSize" style="width: 90px" size="small" @change="currentPage = 1">
            <el-option :value="20" label="20 条" />
            <el-option :value="50" label="50 条" />
            <el-option :value="100" label="100 条" />
          </el-select>
        </div>
      </div>

      <!-- 文件列表 -->
      <DuplicateGroupList :groups="pagedGroups" />

      <!-- 分页 -->
      <div v-if="filteredGroups.length > pageSize" class="pagination-row">
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="pageSize"
          :total="filteredGroups.length"
          layout="prev, pager, next, total"
          background
          @current-change="currentPage = $event"
        />
      </div>

      <!-- 底部操作栏 -->
      <SelectionToolbar
        v-if="scanStore.groups.length > 0"
        :selected-count="stats.selectedCount.value"
        :selected-size-bytes="stats.selectedSizeBytes.value"
        :is-deleting="isDeleting"
        :is-scanning="scanStore.isScanning"
        style="margin-top: 12px"
        @select-all="handleSelectAll"
        @clear-all="selection.clearAll()"
        @trash="showTrashDialog = true"
        @permanent-delete="showPermanentDialog = true"
      />
    </el-main>

    <!-- 目录选择弹窗 -->
    <FolderTreeDialog
      v-model:visible="showFolderDialog"
      :session-id="authStore.sessionId ?? undefined"
      @confirm="handleFolderConfirm"
    />

    <!-- 确认弹窗 -->
    <DeleteConfirmDialog
      v-model:visible="showTrashDialog"
      :file-count="stats.selectedCount.value"
      :size-bytes="stats.selectedSizeBytes.value"
      :is-deleting="isDeleting"
      @confirm="handleDelete('trash')"
      @cancel="showTrashDialog = false"
    />
    <PermanentDeleteDialog
      v-model:visible="showPermanentDialog"
      :file-count="stats.selectedCount.value"
      :size-bytes="stats.selectedSizeBytes.value"
      :is-deleting="isDeleting"
      @confirm="handleDelete('permanent')"
      @cancel="showPermanentDialog = false"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { Files, VideoPause, VideoPlay, Folder, FolderOpened, Refresh, Delete } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { useAuthStore } from '@/stores/auth'
import { useScanStore } from '@/stores/scan'
import { useSelectionStore } from '@/stores/selection'
import { useSSE } from '@/composables/useSSE'
import { useFileFilter } from '@/composables/useFileFilter'
import { useSelection } from '@/composables/useSelection'
import { useStats } from '@/composables/useStats'
import { startScan, startDelete, logout, pauseScan, resumeScan, stopScan, clearScanCache } from '@/api'

import ProgressPanel from '@/components/ProgressPanel.vue'
import StatsSummary from '@/components/StatsSummary.vue'
import FilterBar from '@/components/FilterBar.vue'
import DuplicateGroupList from '@/components/DuplicateGroupList.vue'
import SelectionToolbar from '@/components/SelectionToolbar.vue'
import DeleteConfirmDialog from '@/components/DeleteConfirmDialog.vue'
import PermanentDeleteDialog from '@/components/PermanentDeleteDialog.vue'
import FolderTreeDialog from '@/components/FolderTreeDialog.vue'

const router = useRouter()
const authStore = useAuthStore()
const scanStore = useScanStore()
const selectionStore = useSelectionStore()

// ── SSE ──────────────────────────────────────────────────────────────────────
const { connect: connectSSE, disconnect: disconnectSSE } = useSSE()

// ── Progress state ────────────────────────────────────────────────────────────
const progressMode = ref<'scan' | 'delete'>('scan')
const showProgress = ref(false)
const currentProgress = ref<{
  percentage: number
  fetched_count?: number
  total_count?: number | null
  processed_count?: number
  success_count?: number
  failed_count?: number
} | null>(null)
const operationResult = ref<{
  success_count: number
  failed_count: number
  freed_bytes: number
  failed_files?: Array<{ file_id: string; error_msg: string }>
} | null>(null)
const progressError = ref<string | null>(null)

// ── Delete state ──────────────────────────────────────────────────────────────
const isDeleting = ref(false)
const showTrashDialog = ref(false)
const showPermanentDialog = ref(false)

// ── Elapsed timer ─────────────────────────────────────────────────────────────
const elapsedSeconds = ref(0)
const scanCompleted = ref(false)
const completedFetchedCount = ref(0)
let elapsedTimer: ReturnType<typeof setInterval> | null = null
// Unix timestamp (seconds) when the current scan started, persisted across refreshes
let scanStartTime = 0

function startElapsedTimer(resumeFromSeconds = 0) {
  stopElapsedTimer()
  elapsedSeconds.value = resumeFromSeconds
  scanCompleted.value = false
  scanStartTime = Math.floor(Date.now() / 1000) - resumeFromSeconds
  sessionStorage.setItem('scan_start_time', String(scanStartTime))
  elapsedTimer = setInterval(() => {
    elapsedSeconds.value = Math.floor(Date.now() / 1000) - scanStartTime
  }, 1000)
}

function stopElapsedTimer() {
  if (elapsedTimer !== null) {
    clearInterval(elapsedTimer)
    elapsedTimer = null
  }
}

function markScanComplete() {
  stopElapsedTimer()
  scanCompleted.value = true
  sessionStorage.removeItem('scan_start_time')
  // Keep the progress panel visible — user can see elapsed time until next scan
}

// ── Folder selection ──────────────────────────────────────────────────────────
const showFolderDialog = ref(false)
const selectedFolderIds = computed({
  get: () => scanStore.selectedFolderIds,
  set: (v: string[]) => scanStore.setSelectedFolders(v, scanStore.selectedFolderNames),
})
const selectedFolderNames = computed({
  get: () => scanStore.selectedFolderNames,
  set: (v: string[]) => scanStore.setSelectedFolders(scanStore.selectedFolderIds, v),
})

// ── Pagination ────────────────────────────────────────────────────────────────
const pageSize = ref(20)
const currentPage = ref(1)

// ── Filter / sort ─────────────────────────────────────────────────────────────
const { keyword, selectedFileType, sortField, sortOrder, filteredGroups } = useFileFilter(
  () => scanStore.groups,
)

// Paged slice of filtered groups
const pagedGroups = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredGroups.value.slice(start, start + pageSize.value)
})

// ── Selection ─────────────────────────────────────────────────────────────────
const selection = useSelection(() => filteredGroups.value)

// ── Stats ─────────────────────────────────────────────────────────────────────
const stats = useStats(() => filteredGroups.value)

// ── Default-select duplicates (keep newest per group) ────────────────────────
function autoSelectDuplicates(groups: typeof filteredGroups.value) {
  selectionStore.clear()
  for (const group of groups) {
    if (group.files.length <= 1) continue
    const sorted = [...group.files].sort(
      (a, b) => new Date(b.modified_at).getTime() - new Date(a.modified_at).getTime(),
    )
    // Keep the newest (index 0), select all others for deletion
    sorted.slice(1).forEach(f => selectionStore.select(f.file_id))
  }
}

function handleSelectAll() {
  selection.selectAllKeepOne()
}

// ── SSE handlers (shared between initial scan and reconnect) ─────────────────
function makeScanHandlers() {
  return {
    progress(data: any) {
      currentProgress.value = {
        percentage: data.percentage ?? 0,
        fetched_count: data.fetched_count ?? 0,
        total_count: data.total_count ?? null,
      }
      scanStore.setProgress({
        fetched_count: data.fetched_count ?? 0,
        total_count: data.total_count ?? null,
        percentage: data.percentage ?? 0,
      })
      // Show partial results while scanning — only update if there are actual groups
      if (data.partial_groups && Array.isArray(data.partial_groups) && data.partial_groups.length > 0) {
        scanStore.persistPartial(data.partial_groups)
        autoSelectDuplicates(data.partial_groups)
      }
    },
    complete(data: any) {
      disconnectSSE()
      completedFetchedCount.value = data.scanned_file_count ?? data.total_count ?? (currentProgress.value?.fetched_count ?? 0)
      markScanComplete()
      const groups = data.groups ?? []
      scanStore.persistResult(groups)
      scanStore.setScannedFileCount(data.scanned_file_count ?? data.total_count ?? 0)
      sessionStorage.removeItem('scan_partial')
      scanStore.setTaskId(null)
      scanStore.setScanning(false)
      currentProgress.value = {
        percentage: 100,
        fetched_count: data.scanned_file_count ?? data.total_count ?? 0,
        total_count: data.scanned_file_count ?? data.total_count ?? null,
      }
      // showProgress stays true — markScanComplete will hide it after 4s
      autoSelectDuplicates(groups)
    },
    error(data: any) {
      disconnectSSE()
      stopElapsedTimer()
      const msg = data.message ?? '扫描失败'
      progressError.value = msg
      scanStore.setError(msg)
      scanStore.setScanning(false)
      scanStore.setTaskId(null)
    },
    stopped(data: any) {
      // User stopped the scan early — treat partial result as final
      disconnectSSE()
      completedFetchedCount.value = data.scanned_file_count ?? data.fetched_count ?? (currentProgress.value?.fetched_count ?? 0)
      markScanComplete()
      const groups = data.groups ?? []
      scanStore.persistResult(groups)
      scanStore.setScannedFileCount(data.scanned_file_count ?? data.fetched_count ?? 0)
      sessionStorage.removeItem('scan_partial')
      scanStore.setTaskId(null)
      scanStore.setScanning(false)
      currentProgress.value = {
        percentage: 100,
        fetched_count: data.scanned_file_count ?? data.fetched_count ?? 0,
        total_count: data.scanned_file_count ?? data.fetched_count ?? null,
      }
      // showProgress stays true — markScanComplete will hide it after 4s
      autoSelectDuplicates(groups)
    },
  }
}

// ── Auth check + restore state on mount ──────────────────────────────────────
onMounted(async () => {
  console.log('[ScanView] onMounted start')
  console.log('[ScanView] sessionStorage scan_task_id:', sessionStorage.getItem('scan_task_id'))
  console.log('[ScanView] sessionStorage scan_result length:', sessionStorage.getItem('scan_result')?.length ?? 0)

  await authStore.checkAuth()
  console.log('[ScanView] checkAuth done, isAuthenticated:', authStore.isAuthenticated)

  if (!authStore.isAuthenticated) {
    router.push('/login')
    return
  }

  // 1. Try to reconnect an in-progress scan task
  const persistedTaskId = scanStore.getPersistedTaskId()
  console.log('[ScanView] persistedTaskId:', persistedTaskId)

  if (persistedTaskId) {
    console.log('[ScanView] reconnecting SSE for task:', persistedTaskId)
    // Restore taskId to store so pause/stop buttons are visible
    scanStore.setTaskId(persistedTaskId)
    scanStore.setScanning(true)
    // Restore selected folders
    scanStore.restoreSelectedFolders()
    // Restore persisted progress so fetched_count shows correctly after refresh
    scanStore.restoreProgress()
    progressMode.value = 'scan'
    showProgress.value = true
    currentProgress.value = {
      percentage: scanStore.progress.percentage,
      fetched_count: scanStore.progress.fetched_count,
      total_count: scanStore.progress.total_count,
    }
    operationResult.value = null
    progressError.value = null
    scanCompleted.value = false
    // Restore elapsed time from persisted start timestamp so timer doesn't reset on refresh
    const persistedStartTime = sessionStorage.getItem('scan_start_time')
    const resumeSeconds = persistedStartTime
      ? Math.max(0, Math.floor(Date.now() / 1000) - parseInt(persistedStartTime, 10))
      : 0
    startElapsedTimer(resumeSeconds)

    // Immediately restore any partial results from the previous session
    // so the list isn't empty while waiting for the next SSE progress event.
    if (scanStore.groups.length === 0) {
      const hadPartial = scanStore.restorePartial()
      if (hadPartial) {
        autoSelectDuplicates(scanStore.groups)
      }
    }

    connectSSE(
      `/api/scan/progress/${persistedTaskId}`,
      makeScanHandlers(),
      // Connection error (e.g. 404 — task gone after server restart).
      () => {
        console.log('[ScanView] SSE connection error for task:', persistedTaskId)
        // Wait briefly then re-check if the task still exists on the server.
        // This avoids false negatives from transient errors (Vite HMR, etc.).
        setTimeout(async () => {
          try {
            const res = await fetch(`/api/scan/progress/${persistedTaskId}`, {
              headers: { Accept: 'text/event-stream' },
            })
            if (res.status !== 404) {
              // Task still alive — reconnect SSE
              console.log('[ScanView] task still alive, reconnecting...')
              connectSSE(`/api/scan/progress/${persistedTaskId}`, makeScanHandlers())
              return
            }
          } catch {
            // Network error — assume task is gone
          }
          console.log('[ScanView] task confirmed gone, clearing state')
          scanStore.setScanning(false)
          scanStore.setTaskId(null)
          showProgress.value = false
          if (scanStore.groups.length === 0) {
            scanStore.restoreResult()
            if (scanStore.groups.length > 0) {
              autoSelectDuplicates(scanStore.groups)
            }
          }
        }, 2000)
      },
    )
    return
  }

  // 2. No in-progress task — restore last completed scan result if available
  console.log('[ScanView] no persisted task, trying restoreResult')
  // Restore selected folders regardless of scan state
  scanStore.restoreSelectedFolders()
  if (scanStore.groups.length === 0) {
    const restored = scanStore.restoreResult()
    console.log('[ScanView] restoreResult:', restored, 'groups:', scanStore.groups.length)
    if (restored && scanStore.groups.length > 0) {
      autoSelectDuplicates(scanStore.groups)
    }
  }
})

// ── Cleanup ───────────────────────────────────────────────────────────────────
onUnmounted(() => {
  stopElapsedTimer()
})

// ── Logout ────────────────────────────────────────────────────────────────────
async function handleLogout() {
  try {
    await logout()
  } catch {
    // ignore errors
  }
  authStore.clearSession()
  router.push('/login')
}

// ── Scan controls ─────────────────────────────────────────────────────────────
async function handlePause() {
  const taskId = scanStore.taskId
  if (!taskId) return
  // Optimistically mark as paused so the UI switches to "继续" immediately.
  scanStore.setPaused(true)
  try {
    await pauseScan(taskId)
  } catch {
    // Revert if the request failed
    scanStore.setPaused(false)
  }
}

async function handleResume() {
  const taskId = scanStore.taskId
  if (!taskId) return
  scanStore.setPaused(false)
  try {
    await resumeScan(taskId)
  } catch {
    // Revert if the request failed
    scanStore.setPaused(true)
  }
}

async function handleStop() {
  const taskId = scanStore.taskId
  if (!taskId) return
  // Optimistically update UI immediately so the button disappears and
  // repeated clicks are prevented, even if the SSE 'stopped' event is delayed.
  scanStore.setScanning(false)
  scanStore.setPaused(false)
  scanStore.setTaskId(null)
  showProgress.value = false
  stopElapsedTimer()
  try {
    await stopScan(taskId)
    // The 'stopped' SSE event will arrive shortly and update groups/results.
    // If it doesn't (e.g. connection already closed), partial results already
    // in the store from the last 'progress' event are still shown.
  } catch {
    // 404 means the task already finished — that's fine, ignore.
  }
}

// ── Scan ──────────────────────────────────────────────────────────────────────
async function handleScan(incremental = false) {
  if (scanStore.isScanning) return

  // Preserve selected folders before reset clears them
  const folderIds = [...scanStore.selectedFolderIds]
  const folderNames = [...scanStore.selectedFolderNames]

  // Clear previous results
  scanStore.reset()
  selectionStore.clear()
  currentPage.value = 1

  // Restore folder selection after reset
  if (folderIds.length > 0) {
    scanStore.setSelectedFolders(folderIds, folderNames)
  }

  scanStore.setScanning(true)
  scanStore.setError(null)
  progressMode.value = 'scan'
  showProgress.value = true
  currentProgress.value = { percentage: 0, fetched_count: 0, total_count: null }
  operationResult.value = null
  progressError.value = null
  scanCompleted.value = false
  completedFetchedCount.value = 0

  // Start elapsed timer
  startElapsedTimer()

  try {
    const res = await startScan(
      authStore.sessionId ?? undefined,
      folderIds.length > 0 ? folderIds : undefined,
      incremental,
      folderNames.length > 0 ? folderNames : undefined,
    )
    const taskId = res.data.task_id
    scanStore.setTaskId(taskId)

    connectSSE(`/api/scan/progress/${taskId}`, makeScanHandlers())
  } catch (err: any) {
    stopElapsedTimer()
    const msg = err?.response?.data?.detail ?? '启动扫描失败'
    progressError.value = msg
    scanStore.setError(msg)
    scanStore.setScanning(false)
  }
}

// ── Folder selection handler ──────────────────────────────────────────────────
function handleFolderConfirm(ids: string[], names: string[]) {
  scanStore.setSelectedFolders(ids, names)
}

// ── Clear scan cache ──────────────────────────────────────────────────────────
async function handleClearScanCache() {
  try {
    await ElMessageBox.confirm(
      '清除后，下次增量扫描将退化为全量扫描，重新遍历所有目录。确认清除？',
      '清除扫描缓存',
      {
        confirmButtonText: '确认清除',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch {
    return // user cancelled
  }
  try {
    const res = await clearScanCache(authStore.sessionId ?? undefined)
    ElMessage.success(`已清除扫描缓存（共 ${res.data.deleted_count} 条记录）`)
  } catch {
    ElMessage.error('清除失败，请重试')
  }
}
// ── Delete ────────────────────────────────────────────────────────────────────
async function handleDelete(type: 'trash' | 'permanent') {
  const fileIds = selectionStore.selectedIdsArray
  if (fileIds.length === 0) return

  // Build file_meta from current groups
  const fileMeta = scanStore.groups
    .flatMap(g => g.files)
    .filter(f => fileIds.includes(f.file_id))
    .map(f => ({
      file_id: f.file_id,
      file_name: f.file_name,
      file_path: f.file_path ?? '',
      file_size: f.file_size,
    }))

  isDeleting.value = true
  progressMode.value = 'delete'
  showProgress.value = true
  currentProgress.value = {
    percentage: 0,
    processed_count: 0,
    total_count: fileIds.length,
    success_count: 0,
    failed_count: 0,
  }
  operationResult.value = null
  progressError.value = null

  // Close dialogs
  showTrashDialog.value = false
  showPermanentDialog.value = false

  try {
    const res = await startDelete({ file_ids: fileIds, delete_type: type, file_meta: fileMeta })
    const taskId = res.data.task_id

    connectSSE(`/api/delete/progress/${taskId}`, {
      progress(data) {
        currentProgress.value = {
          percentage: data.percentage ?? 0,
          processed_count: data.processed_count ?? 0,
          total_count: data.total_count ?? fileIds.length,
          success_count: data.success_count ?? 0,
          failed_count: data.failed_count ?? 0,
        }
      },
      complete(data) {
        disconnectSSE()
        isDeleting.value = false
        operationResult.value = {
          success_count: data.success_count ?? 0,
          failed_count: data.failed_count ?? 0,
          freed_bytes: data.freed_bytes ?? 0,
          failed_files: data.failed_files ?? [],
        }
        currentProgress.value = {
          percentage: 100,
          processed_count: data.total_count ?? fileIds.length,
          total_count: data.total_count ?? fileIds.length,
          success_count: data.success_count ?? 0,
          failed_count: data.failed_count ?? 0,
        }
        // Remove successfully deleted files from store
        const failedIds = new Set((data.failed_files ?? []).map((f: any) => f.file_id))
        const deletedIds = new Set(fileIds.filter(id => !failedIds.has(id)))
        const updatedGroups = scanStore.groups
          .map(g => ({
            ...g,
            files: g.files.filter(f => !deletedIds.has(f.file_id)),
            duplicate_count: g.files.filter(f => !deletedIds.has(f.file_id)).length,
          }))
          .filter(g => g.files.length > 1)
        scanStore.persistResult(updatedGroups)
        selectionStore.clear()
        autoSelectDuplicates(updatedGroups)
      },
      error(data) {
        disconnectSSE()
        isDeleting.value = false
        const msg = data.message ?? '删除失败'
        progressError.value = msg
      },
    })
  } catch (err: any) {
    const msg = err?.response?.data?.detail ?? '启动删除失败'
    progressError.value = msg
    isDeleting.value = false
  }
}
</script>

<style scoped>
.scan-view {
  min-height: 100vh;
  background: #f5f7fa;
  display: flex;
  flex-direction: column;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  padding: 0 24px;
  height: 56px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.app-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 4px;
}

.main-content {
  padding: 24px;
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
}

.scan-controls {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}

.scan-hint {
  font-size: 13px;
  color: #909399;
}

.scan-scope-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #606266;
  margin-top: -8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.scan-scope-hint .el-icon {
  color: #e6a23c;
  flex-shrink: 0;
}

.scope-more {
  font-size: 13px;
  color: #909399;
}

.toolbar-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-size-selector {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.page-size-label {
  font-size: 13px;
  color: #606266;
  white-space: nowrap;
}

.pagination-row {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
</style>
