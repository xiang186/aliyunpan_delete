<template>
  <div v-if="isActive" class="progress-panel">
    <!-- 扫描进度 -->
    <template v-if="mode === 'scan'">
      <div v-if="completed" class="panel-title completed-title">
        <el-icon style="color: #67c23a; margin-right: 4px"><CircleCheck /></el-icon>
        扫描完成
        <span v-if="elapsedSeconds !== undefined" class="elapsed-final">
          用时 {{ formatElapsed(elapsedSeconds) }}，共获取 {{ completedFetchedCount }} 个文件
        </span>
      </div>
      <div v-else class="panel-title">正在扫描重复文件...</div>
      <el-progress
        :percentage="completed ? 100 : (progress?.percentage ?? 0)"
        :status="error ? 'exception' : (completed ? 'success' : undefined)"
        :striped="!error && !completed"
        :striped-flow="!error && !completed"
      />
      <div v-if="!completed" class="progress-info">
        已获取 {{ progress?.fetched_count ?? 0 }} 个文件
        <span v-if="progress?.total_count">/ {{ progress.total_count }}</span>
        <span v-if="elapsedSeconds !== undefined && elapsedSeconds > 0" class="elapsed-time">　已用时：{{ formatElapsed(elapsedSeconds) }}</span>
      </div>
    </template>

    <!-- 删除进度 -->
    <template v-else-if="mode === 'delete'">
      <div class="panel-title">正在删除文件...</div>
      <el-progress
        :percentage="progress?.percentage ?? 0"
        :status="error ? 'exception' : undefined"
      />
      <div class="progress-info">
        已处理 {{ progress?.processed_count ?? 0 }} / {{ progress?.total_count ?? 0 }}
        （成功 {{ progress?.success_count ?? 0 }}，失败 {{ progress?.failed_count ?? 0 }}）
      </div>
    </template>

    <!-- 错误 -->
    <el-alert v-if="error" type="error" :title="error" :closable="false" show-icon style="margin-top: 8px" />

    <!-- 完成结果摘要（删除操作） -->
    <div v-if="result" class="result-summary">
      <el-alert type="success" :closable="false" show-icon style="margin-bottom: 8px">
        操作完成：成功 {{ result.success_count }} 个，失败 {{ result.failed_count }} 个，
        释放空间 {{ formatBytes(result.freed_bytes) }}
      </el-alert>
      <div v-if="result.failed_files?.length" class="failed-files">
        <div class="failed-title">失败文件列表：</div>
        <el-scrollbar max-height="120px">
          <div v-for="f in result.failed_files" :key="f.file_id" class="failed-item">
            <span class="failed-id">{{ f.file_id }}</span>
            <span class="failed-msg">{{ f.error_msg }}</span>
          </div>
        </el-scrollbar>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { CircleCheck } from '@element-plus/icons-vue'

const props = defineProps<{
  isActive: boolean
  mode: 'scan' | 'delete'
  progress: {
    percentage: number
    fetched_count?: number
    total_count?: number | null
    processed_count?: number
    success_count?: number
    failed_count?: number
  } | null
  result: {
    success_count: number
    failed_count: number
    freed_bytes: number
    failed_files?: Array<{ file_id: string; error_msg: string }>
  } | null
  error: string | null
  elapsedSeconds?: number
  completed?: boolean
  completedFetchedCount?: number
}>()

function formatElapsed(seconds: number): string {
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  if (mins > 0) {
    return `${mins}分${String(secs).padStart(2, '0')}秒`
  }
  return `${secs}秒`
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(2)} ${units[i]}`
}
</script>

<style scoped>
.progress-panel { padding: 16px; background: #fff; border: 1px solid #e4e7ed; border-radius: 6px; }
.panel-title { font-size: 14px; font-weight: 500; margin-bottom: 10px; color: #303133; display: flex; align-items: center; }
.completed-title { color: #67c23a; }
.elapsed-final { font-size: 13px; color: #909399; font-weight: 400; margin-left: 8px; }
.progress-info { font-size: 13px; color: #606266; margin-top: 6px; }
.elapsed-time { color: #909399; }
.result-summary { margin-top: 12px; }
.failed-files { margin-top: 8px; }
.failed-title { font-size: 13px; color: #f56c6c; margin-bottom: 4px; }
.failed-item { display: flex; gap: 8px; font-size: 12px; padding: 2px 0; }
.failed-id { color: #909399; font-family: monospace; }
.failed-msg { color: #f56c6c; }
</style>
