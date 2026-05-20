<template>
  <div class="stats-summary">
    <el-descriptions :column="hasSelection ? 5 : 3" border size="small">
      <el-descriptions-item label="重复文件组">
        <span class="stat-value">{{ totalGroups }}</span>
      </el-descriptions-item>
      <el-descriptions-item label="重复副本总数">
        <span class="stat-value">{{ totalFiles }}</span>
      </el-descriptions-item>
      <el-descriptions-item label="可释放空间">
        <span class="stat-value highlight">{{ formatBytes(totalSizeBytes) }}</span>
      </el-descriptions-item>

      <template v-if="hasSelection">
        <el-descriptions-item label="已选文件数">
          <span class="stat-value selected">{{ selectedCount }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="预计释放空间">
          <span class="stat-value selected">{{ formatBytes(selectedSizeBytes ?? 0) }}</span>
        </el-descriptions-item>
      </template>
    </el-descriptions>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  totalGroups: number
  totalFiles: number
  totalSizeBytes: number
  selectedCount?: number
  selectedSizeBytes?: number
}>()

const hasSelection = computed(() => (props.selectedCount ?? 0) > 0)

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
}

.stat-value {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.stat-value.highlight {
  color: #e6a23c;
}

.stat-value.selected {
  color: #409eff;
}
</style>
