<template>
  <div class="selection-toolbar">
    <div class="toolbar-info">
      <span class="selected-count">
        已选 <strong>{{ selectedCount }}</strong> 个文件
      </span>
      <span v-if="selectedCount > 0" class="selected-size">
        预计释放 <strong>{{ formatBytes(selectedSizeBytes) }}</strong>
      </span>
    </div>

    <div class="toolbar-actions">
      <div class="select-actions">
        <el-button size="small" @click="emit('select-all')">全选（每组保留一个）</el-button>
        <el-button size="small" @click="emit('clear-all')">取消全选</el-button>
      </div>

      <div class="delete-actions">
        <el-tooltip
          :content="isScanning ? '扫描进行中，请等待扫描完成后再删除' : ''"
          :disabled="!isScanning"
          placement="top"
        >
          <span>
            <el-button
              type="warning"
              size="small"
              :disabled="selectedCount === 0 || isDeleting || isScanning"
              :loading="isDeleting"
              @click="emit('trash')"
            >
              移至回收站
            </el-button>
          </span>
        </el-tooltip>
        <el-tooltip
          :content="isScanning ? '扫描进行中，请等待扫描完成后再删除' : ''"
          :disabled="!isScanning"
          placement="top"
        >
          <span>
            <el-button
              type="danger"
              size="small"
              :disabled="selectedCount === 0 || isDeleting || isScanning"
              :loading="isDeleting"
              @click="emit('permanent-delete')"
            >
              永久删除
            </el-button>
          </span>
        </el-tooltip>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{
  selectedCount: number
  selectedSizeBytes: number
  isDeleting: boolean
  isScanning?: boolean
}>()

const emit = defineEmits<{
  trash: []
  'permanent-delete': []
  'select-all': []
  'clear-all': []
}>()

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(2)} ${units[i]}`
}
</script>

<style scoped>
.selection-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  padding: 10px 16px;
  background: #fff;
  border-radius: 6px;
  border: 1px solid #e4e7ed;
}

.toolbar-info {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 14px;
  color: #606266;
}

.selected-count strong {
  color: #409eff;
}

.selected-size strong {
  color: #e6a23c;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.select-actions {
  display: flex;
  gap: 8px;
}

.delete-actions {
  display: flex;
  gap: 8px;
}
</style>
