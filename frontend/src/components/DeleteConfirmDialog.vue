<template>
  <el-dialog
    :model-value="visible"
    title="确认移至回收站"
    width="480px"
    :close-on-click-modal="!isDeleting"
    :close-on-press-escape="!isDeleting"
    @update:model-value="emit('update:visible', $event)"
    @close="emit('cancel')"
  >
    <div class="dialog-content">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        description="文件将被移至回收站，可从回收站恢复"
        style="margin-bottom: 16px"
      />

      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="将删除文件数">
          <strong>{{ fileCount }}</strong> 个文件
        </el-descriptions-item>
        <el-descriptions-item label="预计释放空间">
          <strong>{{ formatBytes(sizeBytes) }}</strong>
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button :disabled="isDeleting" @click="emit('cancel')">取消</el-button>
        <el-button
          type="warning"
          :disabled="isDeleting"
          :loading="isDeleting"
          @click="emit('confirm')"
        >
          确认移至回收站
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
const props = defineProps<{
  visible: boolean
  fileCount: number
  sizeBytes: number
  isDeleting: boolean
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  confirm: []
  cancel: []
}>()

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(2)} ${units[i]}`
}
</script>

<style scoped>
.dialog-content {
  padding: 4px 0;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
