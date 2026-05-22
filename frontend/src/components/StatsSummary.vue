<template>
  <div class="stats-summary">
    <!-- 扫描结果统计 -->
    <div class="stats-row">
      <!-- 共扫描文件（仅扫描完成后有值） -->
      <div v-if="scannedFileCount && scannedFileCount > 0" class="stat-item">
        <span class="stat-label">共扫描文件</span>
        <span class="stat-value">{{ scannedFileCount.toLocaleString() }}</span>
      </div>

      <div class="stat-item">
        <span class="stat-label">重复文件组</span>
        <span class="stat-value">{{ totalGroups.toLocaleString() }}</span>
      </div>

      <div class="stat-item">
        <span class="stat-label">重复副本总数</span>
        <span class="stat-value">{{ totalFiles.toLocaleString() }}</span>
      </div>

      <div class="stat-item">
        <span class="stat-label">可删除副本</span>
        <span class="stat-value warning">{{ deletableFiles.toLocaleString() }}</span>
      </div>

      <div class="stat-item">
        <span class="stat-label">可释放空间</span>
        <span class="stat-value highlight">{{ formatBytes(totalSizeBytes) }}</span>
      </div>

      <!-- 重复率：仅在有扫描总数时显示 -->
      <div v-if="scannedFileCount && scannedFileCount > 0" class="stat-item">
        <span class="stat-label">重复率</span>
        <span class="stat-value" :class="duplicationRate > 20 ? 'danger' : duplicationRate > 5 ? 'warning' : ''">
          {{ duplicationRate.toFixed(1) }}%
        </span>
      </div>
    </div>

    <!-- 已选统计（有选中时才显示） -->
    <div v-if="hasSelection" class="stats-row selected-row">
      <div class="stat-item">
        <span class="stat-label">已选文件</span>
        <span class="stat-value selected">{{ selectedCount?.toLocaleString() }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">预计释放</span>
        <span class="stat-value selected">{{ formatBytes(selectedSizeBytes ?? 0) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  totalGroups: number
  totalFiles: number
  deletableFiles?: number
  totalSizeBytes: number
  scannedFileCount?: number
  selectedCount?: number
  selectedSizeBytes?: number
}>()

const hasSelection = computed(() => (props.selectedCount ?? 0) > 0)

// 重复率 = 可删除副本 / 扫描总文件数
const duplicationRate = computed(() => {
  if (!props.scannedFileCount || props.scannedFileCount === 0) return 0
  return ((props.deletableFiles ?? 0) / props.scannedFileCount) * 100
})

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(2)} ${units[i]}`
}
</script>

<style scoped>
.stats-summary {
  padding: 12px 16px;
  background: #fff;
  border-radius: 6px;
  border: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stats-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  overflow: hidden;
}

.selected-row {
  border-color: #d9ecff;
  background: #f0f7ff;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 20px;
  border-right: 1px solid #ebeef5;
  min-width: 100px;
  flex: 1;
}

.stat-item:last-child {
  border-right: none;
}

.selected-row .stat-item {
  border-right-color: #d9ecff;
}

.stat-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
  white-space: nowrap;
}

.stat-value {
  font-size: 18px;
  font-weight: 700;
  color: #303133;
  white-space: nowrap;
}

.stat-value.highlight {
  color: #e6a23c;
}

.stat-value.warning {
  color: #e6a23c;
}

.stat-value.danger {
  color: #f56c6c;
}

.stat-value.selected {
  color: #409eff;
}
</style>
