<template>
  <el-dialog
    :model-value="visible"
    title="⚠️ 永久删除确认"
    width="500px"
    :close-on-click-modal="!isDeleting"
    :close-on-press-escape="!isDeleting"
    class="permanent-delete-dialog"
    @update:model-value="emit('update:visible', $event)"
    @close="handleClose"
  >
    <div class="dialog-content">
      <el-alert
        type="error"
        :closable="false"
        show-icon
        title="此操作不可撤销"
        description="文件将被永久删除，无法从回收站恢复"
        style="margin-bottom: 16px"
      />

      <el-descriptions :column="2" border size="small" style="margin-bottom: 20px">
        <el-descriptions-item label="将删除文件数">
          <strong>{{ fileCount }}</strong> 个文件
        </el-descriptions-item>
        <el-descriptions-item label="预计释放空间">
          <strong>{{ formatBytes(sizeBytes) }}</strong>
        </el-descriptions-item>
      </el-descriptions>

      <div class="confirm-input-section">
        <p class="confirm-hint">
          请输入 <strong class="confirm-text-hint">{{ CONFIRM_TEXT }}</strong> 以确认操作：
        </p>
        <el-input
          v-model="inputText"
          :placeholder="`请输入「${CONFIRM_TEXT}」`"
          :disabled="isDeleting"
          clearable
        />
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button :disabled="isDeleting" @click="handleClose">取消</el-button>
        <el-button
          type="danger"
          :disabled="!canConfirm"
          :loading="isDeleting"
          @click="emit('confirm')"
        >
          永久删除
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'

const CONFIRM_TEXT = '确认永久删除'

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

const inputText = ref('')
const canConfirm = computed(() => inputText.value === CONFIRM_TEXT && !props.isDeleting)

// 每次打开对话框时重置输入
watch(
  () => props.visible,
  (val) => {
    if (val) inputText.value = ''
  }
)

function handleClose() {
  inputText.value = ''
  emit('cancel')
}

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

.confirm-input-section {
  margin-top: 4px;
}

.confirm-hint {
  font-size: 14px;
  color: #606266;
  margin-bottom: 8px;
}

.confirm-text-hint {
  color: #f56c6c;
  font-family: monospace;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>

<style>
/* 全局样式：给永久删除对话框的标题加红色警告样式 */
.permanent-delete-dialog .el-dialog__header {
  background-color: #fef0f0;
  border-bottom: 1px solid #fde2e2;
}

.permanent-delete-dialog .el-dialog__title {
  color: #f56c6c;
  font-weight: 600;
}
</style>
