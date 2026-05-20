<template>
  <div class="task-history-detail">
    <!-- 任务详情 -->
    <el-descriptions :column="2" border>
      <el-descriptions-item label="操作类型">
        <el-tag v-if="task.delete_type === 'trash'" type="warning">移至回收站</el-tag>
        <el-tag v-else type="danger">永久删除 ⚠️不可恢复</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="状态">
        <el-tag v-if="task.status === 'completed'" type="success">已完成</el-tag>
        <el-tag v-else-if="task.status === 'running'" type="primary">进行中</el-tag>
        <el-tag v-else type="danger">失败</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="开始时间">
        {{ formatTime(task.started_at) }}
      </el-descriptions-item>
      <el-descriptions-item label="完成时间">
        {{ task.completed_at ? formatTime(task.completed_at) : '—' }}
      </el-descriptions-item>
      <el-descriptions-item label="成功数">
        <span class="count-success">{{ task.success_count }}</span>
      </el-descriptions-item>
      <el-descriptions-item label="失败数">
        <span class="count-failed">{{ task.failed_count }}</span>
      </el-descriptions-item>
      <el-descriptions-item label="释放空间" :span="2">
        {{ formatBytes(task.freed_bytes) }}
      </el-descriptions-item>
    </el-descriptions>

    <!-- 文件列表 -->
    <div class="files-section">
      <div class="files-header">
        <span class="files-title">文件列表（共 {{ files.length }} 个）</span>
        <div class="files-pagination-top">
          <el-pagination
            v-if="files.length > pageSize"
            v-model:current-page="currentPage"
            :page-size="pageSize"
            :total="files.length"
            layout="prev, pager, next"
            small
            background
          />
        </div>
      </div>
      <el-table :data="pagedFiles" border stripe max-height="500" style="width: 100%">
        <el-table-column prop="file_name" label="文件名" min-width="160" show-overflow-tooltip />
        <el-table-column prop="file_path" label="路径" min-width="200" show-overflow-tooltip />
        <el-table-column label="大小" width="100" align="right">
          <template #default="{ row }">
            {{ formatBytes(row.file_size) }}
          </template>
        </el-table-column>
        <el-table-column label="操作结果" width="100" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.result === 'success'" type="success" size="small">成功</el-tag>
            <el-tag v-else-if="row.result === 'failed'" type="danger" size="small">失败</el-tag>
            <el-tag v-else type="info" size="small">跳过</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="error_msg" label="错误信息" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.error_msg" class="error-msg">{{ row.error_msg }}</span>
            <span v-else class="no-error">—</span>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="files.length > pageSize" class="files-pagination-bottom">
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="pageSize"
          :total="files.length"
          layout="prev, pager, next, total"
          background
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

const props = defineProps<{
  task: {
    task_id: string
    delete_type: 'trash' | 'permanent'
    status: string
    total_count: number
    success_count: number
    failed_count: number
    freed_bytes: number
    started_at: number
    completed_at: number | null
  }
  files: Array<{
    file_id: string
    file_name: string
    file_path: string
    file_size: number
    result: 'success' | 'failed' | 'skipped'
    error_msg: string | null
  }>
}>()

const pageSize = 100
const currentPage = ref(1)

const pagedFiles = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return props.files.slice(start, start + pageSize)
})

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(2)} ${units[i]}`
}

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}
</script>

<style scoped>
.task-history-detail {
  padding: 4px 0;
}

.files-section {
  margin-top: 20px;
}

.files-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.files-title {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}

.files-pagination-top {
  flex-shrink: 0;
}

.files-pagination-bottom {
  display: flex;
  justify-content: center;
  margin-top: 12px;
}

.count-success {
  color: #67c23a;
  font-weight: 600;
}

.count-failed {
  color: #f56c6c;
  font-weight: 600;
}

.error-msg {
  color: #f56c6c;
  font-size: 12px;
}

.no-error {
  color: #c0c4cc;
}
</style>
